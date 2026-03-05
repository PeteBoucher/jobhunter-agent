"""AWS Lambda handler for periodic job scraping and matching.

Scrapes jobs from configured sources, computes per-user match scores, and
publishes notifications for high-scoring matches. Writes directly to the
shared PostgreSQL database (configured via DATABASE_URL env var).

Triggered by EventBridge schedule.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3

logger = logging.getLogger("jobhunter.lambda")
logger.setLevel(logging.INFO)

# Lazy-initialized SNS client (cached for Lambda warm starts)
_sns_client = None


def _get_sns():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


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


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda entry point.

    1. Scrape jobs from all default sources
    2. Compute match scores for all users
    3. Notify on high-score matches
    """
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    min_score = float(os.environ.get("MIN_MATCH_SCORE_NOTIFY", "70"))

    # DATABASE_URL is injected from SSM via template.yaml; src.database reads it.
    from src.database import get_session, init_db
    from src.job_matcher import compute_match_for_user
    from src.job_scrapers.registry import DEFAULT_SOURCES, SCRAPER_MAP
    from src.models import Job, JobMatch, User

    # Ensure schema is up to date (idempotent)
    init_db()

    # Step 1: Scrape
    total_new_jobs = 0
    scrape_errors = []
    zero_result_scrapers = []

    for source_name in DEFAULT_SOURCES:
        session = get_session()
        try:
            cls = SCRAPER_MAP.get(source_name)
            if not cls:
                logger.warning("Unknown source: %s", source_name)
                continue
            scraper = cls(session)
            jobs = scraper.scrape(max_retries=3, backoff_factor=1.0)
            count = len(jobs)
            total_new_jobs += count
            logger.info(
                "Scraped %d new jobs from %s (raw fetched: %d)",
                count,
                source_name,
                scraper.last_raw_count,
            )
            if scraper.last_raw_count == 0:
                zero_result_scrapers.append(source_name)
                logger.warning("Scraper %s returned 0 raw results", source_name)
        except Exception as e:
            logger.exception("Error scraping %s: %s", source_name, e)
            scrape_errors.append(source_name)
        finally:
            session.close()

    # Alert on scraper health issues
    if scrape_errors or zero_result_scrapers:
        lines = []
        if scrape_errors:
            lines.append("Scrapers that raised exceptions:")
            lines.extend(f"  - {s}" for s in scrape_errors)
        if zero_result_scrapers:
            if lines:
                lines.append("")
            lines.append("Scrapers that returned 0 raw results (may be broken):")
            lines.extend(f"  - {s}" for s in zero_result_scrapers)
        lines.append("\nCheck CloudWatch logs for details.")
        _notify(
            sns_topic_arn,
            f"Jobhunter: scraper health alert ({len(scrape_errors)} errors, "
            f"{len(zero_result_scrapers)} empty)",
            "\n".join(lines),
        )

    # Step 2: Match
    total_matches = 0
    high_score_matches = []

    session = get_session()
    try:
        users = session.query(User).all()
        # Only match newly scraped jobs (no existing JobMatch)
        jobs = (
            session.query(Job).outerjoin(JobMatch).filter(JobMatch.id.is_(None)).all()
        )

        if users and jobs:
            for user in users:
                for job in jobs:
                    jm = compute_match_for_user(session, job, user)
                    total_matches += 1
                    if jm.match_score and jm.match_score >= min_score:
                        high_score_matches.append(
                            f"  - {job.company}: {job.title} ({jm.match_score:.0f}%)"
                        )
            logger.info("Computed %d job matches", total_matches)
        else:
            logger.info(
                "Skipping match: %d users, %d unmatched jobs",
                len(users),
                len(jobs),
            )
    except Exception:
        logger.exception("Error computing matches")
    finally:
        session.close()

    # Step 3: Notify
    if high_score_matches:
        _notify(
            sns_topic_arn,
            f"Jobhunter: {len(high_score_matches)} high-score matches",
            f"Found {len(high_score_matches)} matches scoring "
            f"{min_score:.0f}%+:\n" + "\n".join(high_score_matches),
        )

    # Step 4: Auto-apply to top matches (requires jobhunter-ai private package)
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
        "jobs_scraped": total_new_jobs,
        "matches_computed": total_matches,
        "high_score_matches": len(high_score_matches),
        "scrape_errors": scrape_errors,
        "zero_result_scrapers": zero_result_scrapers,
        "auto_apply_results": auto_apply_results,
    }
    logger.info("Summary: %s", json.dumps(summary))
    return summary
