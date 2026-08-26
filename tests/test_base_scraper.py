"""Tests for BaseScraper's _parse_job() output schema validation."""

from datetime import datetime

from src.job_scrapers.base_scraper import validate_job_batch, validate_parsed_job


def _valid_job() -> dict:
    return {
        "source_job_id": "123",
        "title": "Senior Engineer",
        "company": "Acme",
        "apply_url": "https://acme.example/jobs/123",
        "location": "Madrid",
        "remote": "remote",
        "country": "es",
        "salary_min": 40000.0,
        "salary_max": 60000.0,
        "description": "...",
        "requirements": None,
        "posted_date": datetime.utcnow(),
        "company_industry": "Technology",
        "company_size": "Large (>1,000)",
        "source_type": "company_portal",
    }


def test_validate_parsed_job_accepts_a_well_formed_dict():
    """A dict that follows the documented schema has no problems."""
    assert validate_parsed_job(_valid_job()) == []


def test_validate_parsed_job_accepts_minimal_required_only():
    """Only the four required keys, everything else omitted, is still valid."""
    minimal = {
        "source_job_id": "1",
        "title": "Engineer",
        "company": "Acme",
        "apply_url": "https://acme.example/jobs/1",
    }
    assert validate_parsed_job(minimal) == []


def test_validate_parsed_job_flags_missing_required_keys():
    """Each of the four required keys is checked."""
    for key in ("source_job_id", "title", "company", "apply_url"):
        job = _valid_job()
        del job[key]
        problems = validate_parsed_job(job)
        assert any(key in p for p in problems), f"{key} missing key not flagged"


def test_validate_parsed_job_flags_empty_required_keys():
    """An empty string for a required key is treated the same as missing."""
    job = _valid_job()
    job["company"] = ""
    problems = validate_parsed_job(job)
    assert any("company" in p for p in problems)


def test_validate_parsed_job_flags_remote_as_bool():
    """remote=True/False (instead of the string enum) is the exact bug that
    shipped in the generated Experis scraper — silently stored as "1"/"0"
    text that the matcher never matches against "remote"."""
    job = _valid_job()
    job["remote"] = True
    problems = validate_parsed_job(job)
    assert any("remote" in p.lower() for p in problems)


def test_validate_parsed_job_accepts_remote_none():
    """remote=None is valid — unknown/unspecified, not a violation."""
    job = _valid_job()
    job["remote"] = None
    assert validate_parsed_job(job) == []


def test_validate_parsed_job_flags_invalid_remote_string():
    """A remote value outside the "remote"/"hybrid"/"onsite" enum is flagged."""
    job = _valid_job()
    job["remote"] = "fully-remote"
    problems = validate_parsed_job(job)
    assert any("remote" in p.lower() for p in problems)


def test_validate_parsed_job_flags_posted_date_as_iso_string():
    """posted_date as an ISO string (instead of a datetime object) is flagged
    — SQLAlchemy's DateTime column expects an actual datetime."""
    job = _valid_job()
    job["posted_date"] = "2026-08-26T10:00:00Z"
    problems = validate_parsed_job(job)
    assert any("posted_date" in p for p in problems)


def test_validate_parsed_job_accepts_posted_date_none():
    job = _valid_job()
    job["posted_date"] = None
    assert validate_parsed_job(job) == []


def test_validate_parsed_job_flags_employment_type():
    """employment_type isn't a Job model field anywhere — returning it is
    silently discarded, so it's flagged as wasted effort."""
    job = _valid_job()
    job["employment_type"] = "Full-time"
    problems = validate_parsed_job(job)
    assert any("employment_type" in p for p in problems)


def test_validate_parsed_job_flags_unknown_keys():
    """A key that doesn't match any canonical name (e.g. a typo'd rename
    like company_name instead of company) is flagged, not silently ignored."""
    job = _valid_job()
    job["company_name"] = job.pop("company")
    problems = validate_parsed_job(job)
    # Missing "company" (now empty/absent) AND the stray unknown key are
    # both flagged.
    assert any("company_name" in p for p in problems)
    assert any("company" in p for p in problems)


def test_validate_parsed_job_flags_wrong_salary_type():
    job = _valid_job()
    job["salary_min"] = "40000"
    problems = validate_parsed_job(job)
    assert any("salary_min" in p for p in problems)


# ── Cross-record (batch) validation ──────────────────────────────────────────


def _job(title, apply_url, source_job_id):
    return {
        "source_job_id": source_job_id,
        "title": title,
        "company": "Acme",
        "apply_url": apply_url,
    }


def test_validate_job_batch_flags_shared_apply_url_across_different_titles():
    """The exact bunq bug: a broken per-job link extraction falls back to
    one generic URL for every "job" — individually valid, collectively a
    sign the scraper never found the real per-job links."""
    jobs = [
        _job("Engineer", "https://acme.example/positions", "engineer"),
        _job("Designer", "https://acme.example/positions", "designer"),
        _job("Analyst", "https://acme.example/positions", "analyst"),
    ]
    problems = validate_job_batch(jobs)
    assert any("apply_url" in p for p in problems)


def test_validate_job_batch_allows_shared_apply_url_for_same_title():
    """Two entries for literally the same job (e.g. overlapping pagination)
    sharing a URL isn't the bug pattern — only *different*-titled jobs
    sharing a URL is suspicious."""
    jobs = [
        _job("Engineer", "https://acme.example/jobs/1", "eng-1"),
        _job("Engineer", "https://acme.example/jobs/1", "eng-1"),
    ]
    assert validate_job_batch(jobs) == []


def test_validate_job_batch_allows_distinct_urls():
    jobs = [
        _job("Engineer", "https://acme.example/jobs/1", "eng"),
        _job("Designer", "https://acme.example/jobs/2", "des"),
        _job("Analyst", "https://acme.example/jobs/3", "ana"),
    ]
    assert validate_job_batch(jobs) == []


def test_validate_job_batch_flags_shared_source_job_id():
    jobs = [
        _job("Engineer", "https://acme.example/jobs/1", "dup-id"),
        _job("Designer", "https://acme.example/jobs/2", "dup-id"),
    ]
    problems = validate_job_batch(jobs)
    assert any("source_job_id" in p for p in problems)


def test_validate_job_batch_ignores_single_job():
    """A batch of one has nothing to cross-check against."""
    assert validate_job_batch([_job("Engineer", "https://acme.example/1", "e")]) == []


def test_validate_job_batch_ignores_empty_list():
    assert validate_job_batch([]) == []
