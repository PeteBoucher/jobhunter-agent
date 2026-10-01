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

from src.job_scrapers.gibwork_scraper import GibWorkScraper


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
