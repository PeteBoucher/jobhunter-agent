import os

from sqlalchemy import text

from src.database import get_session, init_db
from src.job_scrapers.base_scraper import BaseScraper


class DummyScraper(BaseScraper):
    def _get_source_name(self) -> str:
        return "dummy"

    def _fetch_jobs(self, **kwargs):
        return [{"id": "x1", "title": "Dev"}]

    def _parse_job(self, raw_job):
        return {
            "source_job_id": raw_job.get("id"),
            "title": raw_job.get("title"),
            "company": "Acme",
            "department": None,
            "location": "Remote",
            "remote": "remote",
            "salary_min": None,
            "salary_max": None,
            "description": "",
            "requirements": ["python"],
            "nice_to_haves": None,
            "apply_url": "https://acme/jobs/x1",
            "posted_date": None,
            "company_industry": None,
            "company_size": None,
            "source_type": "aggregator",
        }


def test_metrics_recorded(tmp_path):
    db_file = tmp_path / "metrics.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
    init_db()
    session = get_session()

    scraper = DummyScraper(session)
    jobs = scraper.scrape(max_retries=1, backoff_factor=0)

    # Check that job was added
    assert len(jobs) == 1

    # Query metrics
    metrics = session.execute(
        text("SELECT action, value FROM scraper_metrics WHERE source = 'dummy'")
    ).fetchall()
    assert any(row[0] == "jobs_added" for row in metrics)

    session.close()
