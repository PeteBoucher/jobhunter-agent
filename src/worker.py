"""Background worker for periodic scraping and job matching."""

import logging
import signal
import sys
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.database import get_session
from src.job_matcher import compute_match_for_user
from src.job_scrapers.github_scraper import GitHubJobsScraper
from src.job_scrapers.microsoft_scraper import MicrosoftScraper
from src.models import Job, User

logger = logging.getLogger("jobhunter.worker")

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def _scrape_job(source_name: str) -> None:
    """Run a single scraper job.

    Args:
        source_name: 'github' or 'microsoft'
    """
    session = get_session()
    try:
        scraper_map = {
            "github": GitHubJobsScraper,
            "microsoft": MicrosoftScraper,
        }

        cls = scraper_map.get(source_name)
        if not cls:
            logger.warning(f"Unknown source: {source_name}")
            return

        scraper = cls(session)
        jobs = scraper.scrape(max_retries=3, backoff_factor=1.0)
        logger.info(f"Scraped {len(jobs)} new jobs from {source_name}")

    except Exception as e:
        logger.exception(f"Error scraping {source_name}: {e}")
    finally:
        session.close()


def _match_job(user_id: Optional[int] = None) -> None:
    """Run job matching for users against all jobs.

    Args:
        user_id: Optional user ID to match for (defaults to all)
    """
    session = get_session()
    try:
        if user_id:
            users = session.query(User).filter(User.id == user_id).all()
        else:
            users = session.query(User).all()

        jobs = session.query(Job).all()

        if not users or not jobs:
            logger.info(f"Skipping match: users={len(users)}, jobs={len(jobs)}")
            return

        total = 0
        for user in users:
            for job in jobs:
                compute_match_for_user(session, job, user)
                total += 1

        logger.info(f"Computed {total} job matches")

    except Exception as e:
        logger.exception(f"Error computing matches: {e}")
    finally:
        session.close()


def start_worker(
    scrape_cron: str = "0 */6 * * *",
    match_cron: str = "0 */12 * * *",
    daemonize: bool = False,
) -> BackgroundScheduler:
    """Start the background worker with scheduled jobs.

    Args:
        scrape_cron: Cron expression for scraping (default every 6 hours)
        match_cron: Cron expression for matching (default every 12 hours)
        daemonize: If True, run as daemon thread and return scheduler

    Returns:
        BackgroundScheduler instance (for testing or manual management)

    Example:
        # Start worker with default schedule
        scheduler = start_worker()
        scheduler.start()

        # Custom schedules
        scheduler = start_worker(
            scrape_cron="*/15 * * * *",  # Every 15 mins
            match_cron="0 2 * * *",       # Daily at 2am
        )
        scheduler.start()
    """
    global _scheduler

    logger.info("Starting background worker...")

    scheduler = BackgroundScheduler()
    _scheduler = scheduler

    # Add scraping jobs
    scheduler.add_job(
        _scrape_job,
        CronTrigger.from_crontab(scrape_cron),
        args=("github",),
        id="scrape_github",
        name="Scrape GitHub Jobs",
    )
    scheduler.add_job(
        _scrape_job,
        CronTrigger.from_crontab(scrape_cron),
        args=("microsoft",),
        id="scrape_microsoft",
        name="Scrape Microsoft Careers",
    )

    # Add matching job
    scheduler.add_job(
        _match_job,
        CronTrigger.from_crontab(match_cron),
        id="compute_matches",
        name="Compute Job Matches",
    )

    logger.info("Scheduled jobs:")
    logger.info(f"  - Scrape: {scrape_cron}")
    logger.info(f"  - Match: {match_cron}")

    if daemonize:
        logger.info("Starting scheduler in background (daemon)...")
        scheduler.start()
        return scheduler

    # For manual usage
    return scheduler


def stop_worker() -> None:
    """Stop the background worker."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Worker stopped")


def setup_signal_handlers() -> None:
    """Setup SIGINT/SIGTERM handlers to gracefully shut down worker."""

    def handle_signal(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        stop_worker()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    # Start worker and block
    scheduler = start_worker(daemonize=True)
    setup_signal_handlers()

    logger.info("Worker running. Press Ctrl+C to stop.")
    try:
        # Block forever
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
