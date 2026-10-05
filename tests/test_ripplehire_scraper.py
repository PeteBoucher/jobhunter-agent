"""Tests for the RippleHire scraper's XML parsing and detail-enrichment logic.

RippleHire's endpoints return XML (not JSON, despite what an AI-generated
first draft assumed) and the AI's guessed endpoint names (getjoblist/
getjobdetails) don't exist — the real ones (candidatejobsearch/
candidatejobdetail) were found via a headless-browser capture of an actual
click into a job. These tests cover the parsing logic against realistic
raw shapes captured from the live UST (usource) instance, not the API
itself (see the module docstring for endpoint details).
"""

from src.job_scrapers.ripplehire_scraper import (
    RippleHireInstance,
    RippleHireScraper,
    _parse_posted_date,
    _parse_remote,
    _split_skills,
    _strip_html,
)


class TestParseRemote:
    def test_hybrid_keyword(self):
        assert _parse_remote("Barcelona (Hybrid)") == "hybrid"

    def test_remote_keyword(self):
        assert _parse_remote("Remote - Spain") == "remote"

    def test_no_signal_returns_none(self):
        assert _parse_remote("Bangalore") is None

    def test_none_input_returns_none(self):
        assert _parse_remote(None) is None


class TestStripHtml:
    def test_strips_tags_and_normalizes_whitespace(self):
        assert _strip_html("<p>Hello   <b>world</b></p>") == "Hello world"

    def test_none_returns_none(self):
        assert _strip_html(None) is None

    def test_empty_string_returns_none(self):
        assert _strip_html("") is None


class TestSplitSkills:
    def test_splits_comma_separated_html(self):
        assert _split_skills("<p>Python, AWS, SQL</p>") == ["Python", "AWS", "SQL"]

    def test_none_returns_none(self):
        assert _split_skills(None) is None

    def test_blank_returns_none(self):
        assert _split_skills("<p></p>") is None


class TestParsePostedDate:
    def test_parses_dd_mon_yyyy(self):
        d = _parse_posted_date("17-Sep-2026")
        assert (d.year, d.month, d.day) == (2026, 9, 17)

    def test_none_returns_none(self):
        assert _parse_posted_date(None) is None

    def test_unparseable_returns_none(self):
        assert _parse_posted_date("not a date") is None


class TestParseJob:
    def _instance(self):
        return RippleHireInstance(
            subdomain="usource", token="tok123", company="UST", max_jobs=10
        )

    def _job(self, **overrides):
        job = {
            "jobSeq": "65194",
            "jobTitle": "Associate II - Engineering Design",
            "locations": "Bangalore",
            "_instance": self._instance(),
            "_source_job_id": "usource:65194",
            "_detail": None,
        }
        job.update(overrides)
        return job

    def _scraper(self):
        return RippleHireScraper.__new__(RippleHireScraper)

    def test_list_only_job_has_required_fields(self):
        p = self._scraper()._parse_job(self._job())
        assert p["source_job_id"] == "usource:65194"
        assert p["title"] == "Associate II - Engineering Design"
        assert p["company"] == "UST"
        assert p["apply_url"]

    def test_apply_url_uses_hash_route_to_job_detail(self):
        p = self._scraper()._parse_job(self._job())
        assert p["apply_url"] == (
            "https://usource.ripplehire.com/candidate/?token=tok123"
            "&source=CAREERSITE#detail/job/65194"
        )

    def test_missing_title_returns_empty_dict(self):
        assert self._scraper()._parse_job(self._job(jobTitle="")) == {}

    def test_missing_job_seq_returns_empty_dict(self):
        assert self._scraper()._parse_job(self._job(jobSeq="")) == {}

    def test_title_and_location_are_stripped(self):
        p = self._scraper()._parse_job(
            self._job(jobTitle="Developer III  ", locations=" Trivandrum")
        )
        assert p["title"] == "Developer III"
        assert p["location"] == "Trivandrum"

    def test_no_detail_means_no_description_or_requirements(self):
        p = self._scraper()._parse_job(self._job())
        assert p["description"] is None
        assert p["requirements"] is None
        assert p["posted_date"] is None

    def test_detail_enriches_description_requirements_and_date(self):
        detail = {
            "jobDesc": "<p>Build things.</p>",
            "jobSkills": "<p>Python, AWS</p>",
            "jobPostingDate": "17-Sep-2026",
            "jobLocation": "Bangalore",
        }
        p = self._scraper()._parse_job(self._job(_detail=detail))
        assert p["description"] == "Build things."
        assert p["requirements"] == ["Python", "AWS"]
        assert p["posted_date"].year == 2026

    def test_detail_location_overrides_list_location(self):
        detail = {"jobLocation": "Madrid, Spain"}
        p = self._scraper()._parse_job(self._job(_detail=detail))
        assert p["location"] == "Madrid, Spain"

    def test_source_type_is_company_portal(self):
        p = self._scraper()._parse_job(self._job())
        assert p["source_type"] == "company_portal"


class TestFetchJobsSkipsDetailForExistingIds:
    def test_existing_job_detail_is_none(self, monkeypatch):
        scraper = RippleHireScraper.__new__(RippleHireScraper)
        scraper.instances = [
            RippleHireInstance(
                subdomain="usource", token="tok", company="UST", max_jobs=5
            )
        ]
        scraper._load_existing_ids = lambda: {"usource:1"}
        scraper._load_db_config = lambda: []
        scraper._fetch_instance_listings = lambda instance: [
            {"jobSeq": "1", "jobTitle": "Existing Job"},
            {"jobSeq": "2", "jobTitle": "New Job"},
        ]
        fetch_calls = []
        scraper._fetch_detail = lambda instance, job_seq: fetch_calls.append(job_seq)

        raw_jobs = scraper._fetch_jobs()

        assert fetch_calls == ["2"]
        by_id = {j["_source_job_id"]: j for j in raw_jobs}
        assert by_id["usource:1"]["_detail"] is None
