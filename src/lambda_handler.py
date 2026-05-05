"""AWS Lambda handler for periodic job scraping and matching.

The function runs in two distinct phases, dispatched by the event payload:

  {"action": "scrape"}  (default, triggered by EventBridge every 6h)
      Scrapes all sources concurrently, expires stale listings, then invokes
      itself asynchronously with {"action": "match"} before returning.

  {"action": "match"}
      Computes per-user match scores and publishes SNS notifications for
      high-scoring matches.

Splitting the phases means each gets the full 600 s Lambda budget.
ReservedConcurrentExecutions=1 ensures the match invocation waits in queue
until the scrape execution exits, giving a clean hand-off with no overlap.
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import boto3

logger = logging.getLogger("jobhunter.lambda")
logger.setLevel(logging.INFO)

_EXPIRY_DAYS = 30  # Jobs not re-seen within this window are marked inactive

# Lazy-initialised clients (cached for Lambda warm starts)
_sns_client = None
_lambda_client = None


def _get_sns():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


def _get_lambda():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def _notify(topic_arn: str, subject: str, message: str) -> None:
    """Publish notification to SNS topic."""
    if not topic_arn:
        return
    try:
        _get_sns().publish(
            TopicArn=topic_arn,
            Subject=subject[:100],
            Message=message,
        )
    except Exception:
        logger.exception("Failed to publish SNS notification")


def _invoke_match(function_name: str) -> None:
    """Asynchronously invoke this function in match mode."""
    if not function_name:
        logger.warning("FUNCTION_NAME not set — skipping match invocation")
        return
    try:
        _get_lambda().invoke(
            FunctionName=function_name,
            InvocationType="Event",  # async — does not wait for completion
            Payload=json.dumps({"action": "match"}).encode(),
        )
        logger.info("Invoked %s for matching (async)", function_name)
    except Exception:
        logger.exception("Failed to invoke match Lambda")


def _do_scrape(sns_topic_arn: str, function_name: str) -> Dict[str, Any]:
    """Scrape all sources and expire stale listings.

    Invokes this function asynchronously with action=match on completion.
    """
    from src.database import get_session, init_db
    from src.job_scrapers.registry import DEFAULT_SOURCES, SCRAPER_MAP
    from src.models import Job

    init_db()

    def _scrape_one(
        source_name: str,
    ) -> Tuple[str, int, int, Optional[Exception], Optional[str]]:
        session = get_session()
        try:
            cls = SCRAPER_MAP.get(source_name)
            if not cls:
                logger.warning("Unknown source: %s", source_name)
                return source_name, 0, 0, None, None
            scraper = cls(session)
            jobs = scraper.scrape(max_retries=3, backoff_factor=1.0)
            count = len(jobs)
            raw_count = scraper.last_raw_count
            skip_reason = scraper.last_skip_reason
            logger.info(
                "Scraped %d new jobs from %s (raw fetched: %d)",
                count,
                source_name,
                raw_count,
            )
            if raw_count == 0 and not skip_reason:
                logger.warning("Scraper %s returned 0 raw results", source_name)
            return source_name, count, raw_count, None, skip_reason
        except Exception as e:
            logger.exception("Error scraping %s: %s", source_name, e)
            return source_name, 0, 0, e, None
        finally:
            session.close()

    total_new_jobs = 0
    scrape_errors = []
    zero_result_scrapers = []

    # Give scrapers 480 s — enough for Adzuna and LinkedIn on a good day —
    # and always leave ~120 s for DB writes, stale expiry, and the match
    # invocation before the 600 s Lambda budget expires.
    _SCRAPE_DEADLINE = 480

    executor = ThreadPoolExecutor(max_workers=len(DEFAULT_SOURCES))
    futures = {executor.submit(_scrape_one, src): src for src in DEFAULT_SOURCES}
    done, timed_out = futures_wait(futures, timeout=_SCRAPE_DEADLINE)

    for future in done:
        source_name, count, raw_count, error, skip_reason = future.result()
        if error is not None:
            scrape_errors.append(source_name)
        else:
            total_new_jobs += count
            if raw_count == 0 and not skip_reason:
                zero_result_scrapers.append(source_name)

    for future in timed_out:
        source_name = futures[future]
        logger.warning(
            "Scraper %s did not complete within %ds deadline — skipping this run",
            source_name,
            _SCRAPE_DEADLINE,
        )
        scrape_errors.append(source_name)

    # Don't block waiting for overdue scrapers; the Lambda will exit cleanly
    # after invoking match. Any in-flight scraper threads are killed on exit —
    # SQLAlchemy sessions are per-scraper so no partial writes persist.
    executor.shutdown(wait=False)

    if zero_result_scrapers:
        # Log to CloudWatch only — zero raw results is informational (quota
        # exhaustion, temporary outage) and not worth a paged notification.
        logger.warning(
            "Scrapers returned 0 raw results (check CloudWatch for cause): %s",
            ", ".join(zero_result_scrapers),
        )

    if scrape_errors:
        lines = ["Scrapers that raised exceptions:"]
        lines.extend(f"  - {s}" for s in scrape_errors)
        lines.append("\nCheck CloudWatch logs for details.")
        _notify(
            sns_topic_arn,
            f"Jobhunter: {len(scrape_errors)} scraper(s) raised exceptions",
            "\n".join(lines),
        )

    # Expire stale job listings
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=_EXPIRY_DAYS)
        deactivated = (
            session.query(Job)
            .filter(Job.is_active.is_(True), Job.scraped_at < cutoff)
            .update({"is_active": False}, synchronize_session=False)
        )
        session.commit()
        if deactivated:
            logger.info(
                "Deactivated %d stale job listings (not seen in >%d days)",
                deactivated,
                _EXPIRY_DAYS,
            )
    except Exception:
        logger.exception("Error deactivating stale jobs")
    finally:
        session.close()

    summary = {
        "action": "scrape",
        "jobs_scraped": total_new_jobs,
        "scrape_errors": scrape_errors,
        "zero_result_scrapers": zero_result_scrapers,
    }
    logger.info("Scrape summary: %s", json.dumps(summary))

    # Hand off to match phase — runs in its own fresh Lambda invocation so it
    # gets the full 600 s budget uncontested by scraping I/O.
    _invoke_match(function_name)

    return summary


def _do_match(sns_topic_arn: str) -> Dict[str, Any]:
    """Compute per-user match scores and notify on high-score matches."""
    from sqlalchemy import exists

    from src.database import get_session, init_db
    from src.job_matcher import compute_match_for_user
    from src.models import Job, JobMatch, Skill, User, UserPreferences

    init_db()

    min_score = float(os.environ.get("MIN_MATCH_SCORE_NOTIFY", "70"))
    max_match_per_run = int(os.environ.get("MAX_MATCH_PER_RUN", "5000"))

    total_matches = 0
    high_score_matches = []

    session = get_session()
    try:
        # Only match users who have set up their profile in some meaningful way
        # — CV text, at least one skill, or target titles configured. Without
        # any of these, scores are zero and matches are meaningless. This also
        # ensures the budget is not diluted by users who signed up but never
        # completed their profile.
        users = (
            session.query(User)
            .filter(
                User.cv_text.isnot(None)
                | exists().where(Skill.user_id == User.id)
                | exists().where(
                    UserPreferences.user_id == User.id,
                    UserPreferences.target_titles.isnot(None),
                )
            )
            .all()
        )
        per_user_limit = (
            max(1, max_match_per_run // len(users)) if users else max_match_per_run
        )
        for user in users:
            matched_job_ids = session.query(JobMatch.job_id).filter(
                JobMatch.user_id == user.id
            )
            jobs = (
                session.query(Job)
                .filter(
                    Job.id.notin_(matched_job_ids),
                    Job.is_active.is_(True),
                )
                .order_by(Job.scraped_at.desc())
                .limit(per_user_limit)
                .all()
            )
            if not jobs:
                continue
            for job in jobs:
                jm = compute_match_for_user(session, job, user)
                total_matches += 1
                if jm.match_score and jm.match_score >= min_score:
                    high_score_matches.append(
                        f"  - {job.company}: {job.title} ({jm.match_score:.0f}%)"
                    )
            logger.info("Computed %d matches for user %d", len(jobs), user.id)
            if len(jobs) == per_user_limit:
                logger.warning(
                    "User %d hit per-user limit (%d); unmatched jobs remain "
                    "and will be processed in subsequent runs",
                    user.id,
                    per_user_limit,
                )
        logger.info(
            "Computed %d job matches total across %d users",
            total_matches,
            len(users),
        )
    except Exception:
        logger.exception("Error computing matches")
    finally:
        session.close()

    if high_score_matches:
        _notify(
            sns_topic_arn,
            f"Jobhunter: {len(high_score_matches)} high-score matches",
            f"Found {len(high_score_matches)} matches scoring "
            f"{min_score:.0f}%+:\n" + "\n".join(high_score_matches),
        )

    # Auto-apply (requires jobhunter-ai private package)
    auto_apply_results: list = []
    if os.environ.get("AUTO_APPLY_ENABLED", "false").lower() == "true":
        try:
            from jobhunter_ai import auto_apply_jobs, init_db_extensions

            from src.database import create_engine_instance

            engine = create_engine_instance()
            init_db_extensions(engine)
            min_apply_score = int(os.environ.get("MIN_MATCH_SCORE_APPLY", "85"))
            session = get_session()
            try:
                auto_apply_results = auto_apply_jobs(
                    session, engine, min_score=min_apply_score
                )
            finally:
                session.close()

            applied = [r for r in auto_apply_results if r.get("status") == "submitted"]
            logger.info(
                "Auto-apply: %d/%d jobs submitted",
                len(applied),
                len(auto_apply_results),
            )
            if applied:
                _notify(
                    sns_topic_arn,
                    f"Jobhunter: auto-applied to {len(applied)} job(s)",
                    "\n".join(
                        f"  - job {r['job_id']}: {r['status']}"
                        for r in auto_apply_results
                    ),
                )
        except ImportError:
            logger.warning(
                "jobhunter-ai not installed — auto-apply skipped. "
                "Install the private package to enable."
            )

    summary = {
        "action": "match",
        "matches_computed": total_matches,
        "high_score_matches": len(high_score_matches),
        "auto_apply_results": auto_apply_results,
    }
    logger.info("Match summary: %s", json.dumps(summary))
    return summary


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda entry point — dispatches to scrape or match phase."""
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    function_name = os.environ.get("FUNCTION_NAME", "")

    action = event.get("action", "scrape")
    if action == "match":
        return _do_match(sns_topic_arn)
    return _do_scrape(sns_topic_arn, function_name)
