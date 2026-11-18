#!/usr/bin/env python3
"""Backfill `jobs.remote` for one source's existing rows after a parser fix.

`BaseScraper.scrape()` skips already-seen jobs, so rows scraped before a
scraper's `_parse_job()` learned to read its workplace field keep the old
`remote` value forever (Lever in issue #38; Ashby, SmartRecruiters and
Workable in issue #57). This re-fetches the source, re-parses each live
posting with the current `_parse_job()`, corrects `remote` on existing rows,
and re-scores the location/remote dimension of their existing `JobMatch` rows
(the only dimension `remote` feeds). Jobs no longer listed are left alone.

    DATABASE_URL=<neon-url> python scripts/backfill_remote.py --source ashby --dry-run
    DATABASE_URL=<neon-url> python scripts/backfill_remote.py --source ashby
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Optional

# Make src.* importable from the repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill")


def backfill(session: Session, source: str, dry_run: bool = False) -> Dict[str, int]:
    """Correct `remote` on `source` jobs and re-score affected matches.

    Returns counts: `jobs_updated`, `matches_updated`.
    """
    from src.job_matcher import _score_location_remote, _total_score
    from src.job_scrapers.registry import SCRAPER_MAP
    from src.models import Job, JobMatch, User

    scraper = SCRAPER_MAP[source](session)
    live_remote: Dict[str, Optional[str]] = {}
    for raw_job in scraper._fetch_jobs():
        parsed = scraper._parse_job(raw_job)
        if parsed.get("source_job_id"):
            live_remote[parsed["source_job_id"]] = parsed.get("remote")
    logger.info("Fetched %d live %s postings", len(live_remote), source)

    jobs = (
        session.query(Job)
        .filter(Job.source == source, Job.source_job_id.in_(live_remote))
        .all()
    )
    changed = [j for j in jobs if j.remote != live_remote[j.source_job_id]]
    transitions = Counter(
        f"{j.remote!r} -> {live_remote[j.source_job_id]!r}" for j in changed
    )
    logger.info(
        "%d of %d matching %s rows need updating", len(changed), len(jobs), source
    )
    for transition, count in transitions.most_common():
        logger.info("  %s: %d", transition, count)

    for job in changed:
        job.remote = live_remote[job.source_job_id]
    jobs_by_id = {j.id: j for j in changed}

    # One pass over job_matches for all users rather than a per-(job, user)
    # lookup per changed job.
    matches = (
        session.query(JobMatch).filter(JobMatch.job_id.in_(jobs_by_id)).all()
        if jobs_by_id
        else []
    )
    users = {
        u.id: u
        for u in session.query(User)
        .filter(User.id.in_({m.user_id for m in matches}))
        .all()
    }

    matches_updated = 0
    total_delta = 0.0
    for jm in matches:
        user = users.get(jm.user_id)
        if user is None:
            continue
        location_score = _score_location_remote(jobs_by_id[jm.job_id], user.preferences)
        if location_score == jm.location_or_remote_score:
            continue
        new_total = _total_score(
            jm.title_score or 0.0,
            jm.skill_score or 0.0,
            jm.experience_score or 0.0,
            location_score,
            jm.salary_score or 0.0,
            jm.rejection_penalty or 0.0,
        )
        total_delta += new_total - (jm.match_score or 0.0)
        jm.location_or_remote_score = location_score
        jm.match_score = new_total
        matches_updated += 1

    logger.info(
        "%d of %d existing match rows change (mean score delta %+.1f)",
        matches_updated,
        len(matches),
        total_delta / matches_updated if matches_updated else 0.0,
    )

    if dry_run:
        session.rollback()
        logger.info("[dry-run] nothing written")
    else:
        session.commit()
        logger.info("Committed")

    return {"jobs_updated": len(changed), "matches_updated": matches_updated}


def main(source: str, dry_run: bool = False) -> None:
    from src.database import get_session

    session = get_session()
    try:
        backfill(session, source, dry_run=dry_run)
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="registry source name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(args.source, dry_run=args.dry_run)
