"""Tests for the Recruitee scraper's salary normalization.

Regression coverage for a real bug: salary.min/max come back from
Recruitee's API as numeric strings, and salary.period varies ("month" for
most companies, "hour" for Keolis's transport roles) — found live via
validate_parsed_job() flagging "salary_min must be a number" across ~150
of 278 real jobs when Van Cranenbroek/Woonzorg Flevoland/Keolis were added
alongside Zoi (whose own postings never set a salary, so the string-typed
value went unnoticed until then).
"""

from src.job_scrapers.recruitee_scraper import _annual_salary


def test_annual_salary_defaults_to_yearly_when_no_period():
    assert _annual_salary("50000", None, None) == 50000.0


def test_annual_salary_converts_monthly_string_to_annual():
    assert _annual_salary("2500", "month", None) == 30000.0


def test_annual_salary_handles_decimal_strings():
    assert _annual_salary("3592.96", "month", None) == 3592.96 * 12


def test_annual_salary_converts_hourly_using_posting_hours():
    # 19.95/hour, 37 hours/week -> 19.95 * 37 * 52
    assert _annual_salary("19.95", "hour", 37) == 19.95 * 37 * 52


def test_annual_salary_hourly_falls_back_to_40_hours_when_missing():
    assert _annual_salary("20", "hour", None) == 20 * 40 * 52


def test_annual_salary_scales_down_for_part_time_hours():
    """A 15-hour/week role should convert to well below a 37-hour role at
    the same hourly rate — this is what the posting's own hours field is
    for, not a flat full-time assumption."""
    part_time = _annual_salary("20", "hour", 15)
    full_time = _annual_salary("20", "hour", 37)
    assert part_time < full_time
    assert part_time == 20 * 15 * 52


def test_annual_salary_returns_none_for_missing_value():
    assert _annual_salary(None, "month", 40) is None
    assert _annual_salary("", "month", 40) is None


def test_annual_salary_returns_none_for_unparseable_value():
    assert _annual_salary("negotiable", "month", 40) is None
