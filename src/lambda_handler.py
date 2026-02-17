"""AWS Lambda handler for periodic job scraping and matching.

Downloads the SQLite DB from S3, runs scrapers and match computation,
then uploads the updated DB back to S3. Triggered by EventBridge schedule.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("jobhunter.lambda")
logger.setLevel(logging.INFO)

# Lazy-initialized clients (cached for Lambda warm starts)
_s3_client = None
_sns_client = None

LOCAL_DB_PATH = "/tmp/jobs.db"


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _get_sns():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


def _download_db(bucket: str, key: str) -> bool:
    """Download jobs.db from S3 to /tmp. Returns True if DB existed."""
    try:
        _get_s3().download_file(bucket, key, LOCAL_DB_PATH)
        logger.info("Downloaded existing DB from s3://%s/%s", bucket, key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            logger.info("No existing DB in S3 — starting fresh")
            return False
        raise


def _upload_db(bucket: str, key: str) -> None:
    """Upload /tmp/jobs.db back to S3."""
    _get_s3().upload_file(LOCAL_DB_PATH, bucket, key)
    logger.info("Uploaded DB to s3://%s/%s", bucket, key)


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

    1. Download DB from S3
    2. Scrape jobs from all default sources
    3. Compute match scores for all users
    4. Upload DB back to S3
    5. Notify on high-score matches
    """
    # Read config from environment
    s3_bucket = os.environ.get("S3_BUCKET", "")
    s3_db_key = os.environ.get("S3_DB_KEY", "jobhunter/jobs.db")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    min_score = float(os.environ.get("MIN_MATCH_SCORE_NOTIFY", "70"))

    # Point SQLAlchemy at /tmp
    os.environ["DATABASE_URL"] = f"sqlite:///{LOCAL_DB_PATH}"

    # Import after setting DATABASE_URL so database.py picks it up
    from src.database import get_session, init_db
    from src.job_matcher import compute_match_for_user
    from src.job_scrapers.registry import DEFAULT_SOURCES, SCRAPER_MAP
    from src.models import Job, JobMatch, User

    # Step 1: Download DB
    _download_db(s3_bucket, s3_db_key)
    init_db()

    # Step 2: Scrape
    total_new_jobs = 0
    scrape_errors = []

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
            logger.info("Scraped %d new jobs from %s", count, source_name)
        except Exception as e:
            logger.exception("Error scraping %s: %s", source_name, e)
            scrape_errors.append(source_name)
        finally:
            session.close()

    # Step 3: Match
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

    # Step 4: Upload DB (always, even if scraping partially failed)
    _upload_db(s3_bucket, s3_db_key)

    # Step 5: Notify
    if high_score_matches:
        _notify(
            sns_topic_arn,
            f"Jobhunter: {len(high_score_matches)} high-score matches",
            f"Found {len(high_score_matches)} matches scoring "
            f"{min_score:.0f}%+:\n" + "\n".join(high_score_matches),
        )

    summary = {
        "jobs_scraped": total_new_jobs,
        "matches_computed": total_matches,
        "high_score_matches": len(high_score_matches),
        "scrape_errors": scrape_errors,
    }
    logger.info("Summary: %s", json.dumps(summary))
    return summary
