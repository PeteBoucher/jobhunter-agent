#!/usr/bin/env python3
"""Backfill description/remote/posted_date on GibWork rows hosted on Ashby.

GibWork's feed has no description, workplace type or posted date. The GibWork
scraper now fills them from the linked Ashby posting, but `BaseScraper.scrape()`
never re-parses rows it has already stored, so existing GibWork rows keep
empty values. This re-fetches GibWork (with Ashby data attached), updates the
existing rows that changed, and recomputes every dimension of their existing
`JobMatch` rows. Jobs no longer listed are left alone.

    DATABASE_URL=<neon-url> python scripts/backfill_gibwork_ashby.py --dry-run
    DATABASE_URL=<neon-url> python scripts/backfill_gibwork_ashby.py
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict

# Make src.* importable from the repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill")

FIELDS = ("description", "remote", "posted_date")


def _same(a: Any, b: Any) -> bool:
    # Stored datetimes are naive; Ashby's are UTC-aware.
    if hasattr(a, "replace") and hasattr(b, "tzinfo"):
        try:
            return a.replace(tzinfo=None) == b.replace(tzinfo=None)
        except TypeError:
            pass
    return (a or None) == (b or None)


def backfill(session: Session, dry_run: bool = False) -> Dict[str, int]:
    """Update GibWork rows from attached Ashby data and re-score their matches.

    Returns counts: `jobs_updated`, `matches_updated`.
    """
    from src.job_matcher import compute_match_for_user
    from src.job_scrapers.gibwork_scraper import GibWorkScraper
    from src.models import Job, JobMatch, User

    scraper = GibWorkScraper(session)
    live: Dict[str, Dict[str, Any]] = {}
    for raw_job in scraper._fetch_jobs():
        if not raw_job.get("_ashby"):
            continue
        parsed = scraper._parse_job(raw_job)
        if parsed.get("source_job_id"):
            live[parsed["source_job_id"]] = parsed
    logger.info("Fetched %d live GibWork jobs with Ashby data", len(live))

    jobs = (
        session.query(Job)
        .filter(Job.source == "gibwork", Job.source_job_id.in_(live))
        .all()
        if live
        else []
    )
    changed = []
    for job in jobs:
        new = live[job.source_job_id]
        diffs = [f for f in FIELDS if not _same(getattr(job, f), new.get(f))]
        if not diffs:
            continue
        logger.info(
            "  job %d %r: %s (remote %r -> %r)",
            job.id,
            job.title,
            ", ".join(diffs),
            job.remote,
            new.get("remote"),
        )
        for f in diffs:
            value = new.get(f)
            if f == "posted_date" and value is not None:
                value = value.replace(tzinfo=None)
            setattr(job, f, value)
        changed.append(job)
    logger.info("%d of %d matching GibWork rows need updating", len(changed), len(jobs))
    session.flush()

    jobs_by_id = {j.id: j for j in changed}
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
        before = jm.match_score or 0.0
        compute_match_for_user(session, jobs_by_id[jm.job_id], user, commit=False)
        if abs((jm.match_score or 0.0) - before) > 1e-9:
            matches_updated += 1
            total_delta += (jm.match_score or 0.0) - before

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


def main(dry_run: bool = False) -> None:
    from src.database import get_session

    session = get_session()
    try:
        backfill(session, dry_run=dry_run)
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
