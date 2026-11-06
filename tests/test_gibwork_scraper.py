"""Tests for the GibWork scraper's field mapping.

GibWork (https://www.gibwork.com/) is a Gibraltar-only job aggregator that
re-publishes postings originally hosted on many different ATS platforms
(SmartRecruiters, Ashby, Pinpoint, ...) across many different companies.
These tests cover the two data-quality fixes made after the initial AI-
generated draft: every listing is Gibraltar-based so `country` should be
hardcoded `"gi"` rather than left for base-class inference (which can't
detect Gibraltar), and `source_type` must be `"aggregator"` for every job
regardless of the API's `st` field, since that field describes the
*original employer's* type (private/government/recruiter), not whether
GibWork itself is a direct company portal or a secondary aggregator.
"""

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.job_scrapers.gibwork_scraper import GibWorkScraper, board_ref
from src.models import Base, ScraperConfig


class TestParseJob:
    def _scraper(self):
        return GibWorkScraper.__new__(GibWorkScraper)

    def _raw_job(self, **overrides):
        job = {
            "t": "Digital & Creative Designer",
            "u": (
                "https://peninsula360.pinpointhq.com/en/postings/"
                "af3556ed-4b29-4dec-a32d-816673b77f9e"
            ),
            "s": "Peninsula",
            "st": "pri",
            "c": "Marketing & Digital",
            "loc": "Gibraltar",
            "dom": "peninsula360.com",
            "ll": [36.12438, -5.34646],
            "ats": "pinpoint",
            "logo": None,
        }
        job.update(overrides)
        return job

    def test_required_fields_present(self):
        p = self._scraper()._parse_job(self._raw_job())
        assert p["source_job_id"] == "af3556ed-4b29-4dec-a32d-816673b77f9e"
        assert p["title"] == "Digital & Creative Designer"
        assert p["company"] == "Peninsula"
        assert p["apply_url"] == self._raw_job()["u"]

    def test_country_is_hardcoded_gibraltar(self):
        """Every GibWork listing is in Gibraltar, which isn't in base_scraper's
        residency-inference table — country must be set explicitly here rather
        than left None for inference to (fail to) pick up."""
        p = self._scraper()._parse_job(self._raw_job())
        assert p["country"] == "gi"

    def test_source_type_is_aggregator_regardless_of_st_field(self):
        """GibWork is the aggregator for every job it lists, no matter whether
        the API's "st" field marks the original poster as private, government,
        or recruiter — "st" is not scrape provenance."""
        for st_value in ("pri", "gov", "rec"):
            p = self._scraper()._parse_job(self._raw_job(st=st_value))
            assert p["source_type"] == "aggregator"

    def test_department_maps_from_category(self):
        p = self._scraper()._parse_job(self._raw_job(c="Other"))
        assert p["department"] == "Other"

    def test_location_is_stripped(self):
        p = self._scraper()._parse_job(self._raw_job(loc=" Gibraltar "))
        assert p["location"] == "Gibraltar"

    def test_remote_is_none(self):
        """GibWork's list API has no remote-status field."""
        p = self._scraper()._parse_job(self._raw_job())
        assert p["remote"] is None

    def test_source_job_id_derived_from_apply_url_trailing_segment(self):
        p = self._scraper()._parse_job(
            self._raw_job(u="https://jobs.smartrecruiters.com/Playtech/744000143296883")
        )
        assert p["source_job_id"] == "744000143296883"


class TestFetchJobs:
    def test_non_200_or_non_list_response_returns_empty_list(self, monkeypatch):
        scraper = GibWorkScraper.__new__(GibWorkScraper)

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"unexpected": "shape"}

        class FakeHttp:
            def get(self, *args, **kwargs):
                return FakeResponse()

        scraper._http = FakeHttp()
        assert scraper._fetch_jobs() == []


ASHBY_URL = "https://jobs.ashbyhq.com/patrianna/fd279991-b500-4d83-b466-8b32dba338a5"


def _ashby_posting(**overrides):
    posting = {
        "id": "fd279991-b500-4d83-b466-8b32dba338a5",
        "title": "AI IT and Integrations Lead",
        "department": "BI",
        "location": "Gibraltar",
        "isListed": True,
        "isRemote": True,
        "workplaceType": "Hybrid",
        "publishedAt": "2026-10-16T13:23:30.857+00:00",
        "descriptionPlain": "About Patrianna\n\nWe build things.",
    }
    posting.update(overrides)
    return posting


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status

    def raise_for_status(self):
        import requests

        if self._status != 200:
            raise requests.HTTPError(f"HTTP {self._status}")

    def json(self):
        return self._payload


class _FakeHttp:
    """Serves the GibWork feed and Ashby boards; records requested URLs."""

    def __init__(self, feed, boards, failing=()):
        self.feed = feed
        self.boards = boards
        self.failing = set(failing)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url.endswith("/jobs.json"):
            return _FakeResponse(self.feed)
        slug = url.rsplit("/", 1)[-1]
        if slug in self.failing:
            return _FakeResponse({}, status=500)
        return _FakeResponse({"jobs": self.boards.get(slug, [])})


def _gibwork_job(url=ASHBY_URL, **overrides):
    job = {
        "t": "AI IT and Integrations Lead",
        "u": url,
        "s": "Patrianna",
        "st": "pri",
        "c": "",
        "loc": "Gibraltar",
        "ats": "ashby",
    }
    job.update(overrides)
    return job


def _scraper_with(http, session=None):
    """GibWork scraper on a fake HTTP client; no scraper_config rows by default."""
    if session is None:
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
    scraper = GibWorkScraper.__new__(GibWorkScraper)
    scraper._http = http
    scraper.session = session
    return scraper


class TestAshbyEnrichment:
    def test_ashby_job_gets_remote_description_and_posted_date(self):
        from datetime import datetime, timezone

        http = _FakeHttp([_gibwork_job()], {"patrianna": [_ashby_posting()]})
        scraper = _scraper_with(http)
        p = scraper._parse_job(scraper._fetch_jobs()[0])
        assert p["remote"] == "hybrid"
        assert p["description"].startswith("About Patrianna")
        assert p["posted_date"] == datetime(
            2026, 10, 16, 13, 23, 30, 857000, tzinfo=timezone.utc
        )
        # GibWork's own fields are kept
        assert p["company"] == "Patrianna"
        assert p["country"] == "gi"
        assert p["source_type"] == "aggregator"
        assert p["source_job_id"] == "fd279991-b500-4d83-b466-8b32dba338a5"
        assert p["apply_url"] == ASHBY_URL

    def test_department_falls_back_to_ashby_only_when_gibwork_has_none(self):
        http = _FakeHttp([_gibwork_job(c="IT")], {"patrianna": [_ashby_posting()]})
        scraper = _scraper_with(http)
        assert scraper._parse_job(scraper._fetch_jobs()[0])["department"] == "IT"

        http = _FakeHttp([_gibwork_job(c="")], {"patrianna": [_ashby_posting()]})
        scraper = _scraper_with(http)
        assert scraper._parse_job(scraper._fetch_jobs()[0])["department"] == "BI"

    def test_each_board_fetched_once(self):
        other = ASHBY_URL.replace("fd279991", "aaaaaaaa")
        http = _FakeHttp(
            [_gibwork_job(), _gibwork_job(url=other)],
            {"patrianna": [_ashby_posting()]},
        )
        _scraper_with(http)._fetch_jobs()
        assert sum("ashbyhq.com" in c for c in http.calls) == 1

    def test_job_missing_from_board_is_left_unenriched(self):
        http = _FakeHttp([_gibwork_job()], {"patrianna": []})
        scraper = _scraper_with(http)
        p = scraper._parse_job(scraper._fetch_jobs()[0])
        assert p["remote"] is None
        assert p["description"] is None
        assert p["posted_date"] is None

    def test_board_fetch_failure_keeps_gibwork_jobs(self):
        http = _FakeHttp([_gibwork_job()], {}, failing={"patrianna"})
        scraper = _scraper_with(http)
        jobs = scraper._fetch_jobs()
        assert len(jobs) == 1
        assert scraper._parse_job(jobs[0])["remote"] is None

    def test_non_ashby_jobs_trigger_no_ashby_requests(self):
        url = "https://jobs.smartrecruiters.com/Gibtelecom/744000143296883"
        http = _FakeHttp([_gibwork_job(url=url, ats="smartrecruiters")], {})
        scraper = _scraper_with(http)
        p = scraper._parse_job(scraper._fetch_jobs()[0])
        assert http.calls == ["https://www.gibwork.com/jobs.json"]
        assert p["description"] is None


PLAYTECH_URL = "https://jobs.smartrecruiters.com/Playtech/744000157139999"


@pytest.fixture
def db_session():
    db_fd, db_path = tempfile.mkstemp()
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    os.close(db_fd)
    os.unlink(db_path)


class TestBoardRef:
    def test_ashby_and_smartrecruiters_urls(self):
        assert board_ref(ASHBY_URL) == (
            "ashby",
            "patrianna",
            "fd279991-b500-4d83-b466-8b32dba338a5",
        )
        assert board_ref(PLAYTECH_URL) == (
            "smartrecruiters",
            "Playtech",
            "744000157139999",
        )

    def test_other_hosts_and_bare_boards_are_none(self):
        assert board_ref("https://peninsula360.pinpointhq.com/en/postings/x") is None
        assert board_ref("https://jobs.ashbyhq.com/patrianna") is None
        assert board_ref("") is None


class TestSkipsJobsScrapedDirectly:
    """GibWork re-lists jobs our own ATS scrapers already store in full; with
    no cross-source dedup they'd appear twice, the GibWork copy empty."""

    def _titles(self, scraper):
        return [j["t"] for j in scraper._fetch_jobs()]

    def test_skips_default_smartrecruiters_company(self):
        http = _FakeHttp(
            [
                _gibwork_job(url=PLAYTECH_URL, t="Bingo", ats="smartrecruiters"),
                _gibwork_job(url="https://jobs.smartrecruiters.com/Other/1", t="Keep"),
            ],
            {},
        )
        assert self._titles(_scraper_with(http)) == ["Keep"]

    def test_skips_default_ashby_board_and_does_not_fetch_it(self):
        url = "https://jobs.ashbyhq.com/OpenAI/abc"  # case-insensitive match
        http = _FakeHttp([_gibwork_job(url=url, t="Skip")], {})
        assert self._titles(_scraper_with(http)) == []
        assert not any("ashbyhq.com" in c for c in http.calls)

    def test_skips_companies_from_active_scraper_config(self, db_session):
        db_session.add_all(
            [
                ScraperConfig(
                    source_name="smartrecruiters",
                    config={"company_id": "sixt"},
                    is_active=True,
                ),
                ScraperConfig(
                    source_name="ashby",
                    config={"subdomain": "patrianna"},
                    is_active=True,
                ),
                ScraperConfig(
                    source_name="ashby",
                    config={"subdomain": "b2spin"},
                    is_active=False,
                ),
            ]
        )
        db_session.commit()
        http = _FakeHttp(
            [
                _gibwork_job(url="https://jobs.smartrecruiters.com/Sixt/1", t="Sixt"),
                _gibwork_job(url=ASHBY_URL, t="Patrianna"),
                _gibwork_job(url="https://jobs.ashbyhq.com/b2spin/2", t="B2Spin"),
            ],
            {},
        )
        assert self._titles(_scraper_with(http, db_session)) == ["B2Spin"]

    def test_config_load_failure_still_applies_defaults(self):
        session = MagicMock()
        session.query.side_effect = RuntimeError("db down")
        http = _FakeHttp(
            [
                _gibwork_job(url=PLAYTECH_URL, t="Bingo"),
                _gibwork_job(url=ASHBY_URL, t="Patrianna"),
            ],
            {"patrianna": [_ashby_posting()]},
        )
        assert self._titles(_scraper_with(http, session)) == ["Patrianna"]
