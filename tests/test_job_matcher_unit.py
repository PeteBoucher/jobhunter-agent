"""Unit tests for individual job_matcher scoring functions."""
from unittest.mock import MagicMock

import pytest

from src.job_matcher import (
    _location_terms,
    _normalize_skills,
    _score_experience,
    _score_location_remote,
    _score_salary,
    _score_skills,
    _score_title,
    _skill_matches,
)


def _job(**kwargs):
    j = MagicMock()
    j.title = kwargs.get("title", "")
    j.description = kwargs.get("description", "")
    j.location = kwargs.get("location", "")
    j.remote = kwargs.get("remote", "")
    j.country = kwargs.get("country", None)
    j.salary_min = kwargs.get("salary_min", None)
    j.salary_max = kwargs.get("salary_max", None)
    return j


def _prefs(**kwargs):
    p = MagicMock()
    p.target_titles = kwargs.get("target_titles", [])
    p.experience_level = kwargs.get("experience_level", None)
    p.remote_preference = kwargs.get("remote_preference", None)
    p.preferred_locations = kwargs.get("preferred_locations", [])
    p.preferred_countries = kwargs.get("preferred_countries", None)
    p.salary_min = kwargs.get("salary_min", None)
    p.salary_max = kwargs.get("salary_max", None)
    return p


def _skill(name):
    s = MagicMock()
    s.skill_name = name
    return s


# ---------------------------------------------------------------------------
# _normalize_skills
# ---------------------------------------------------------------------------


class TestNormalizeSkills:
    def test_splits_on_pipe(self):
        result = _normalize_skills([_skill("Python | SQL | Docker")])
        assert "python" in result
        assert "sql" in result
        assert "docker" in result

    def test_splits_on_dot_with_spaces(self):
        result = _normalize_skills(
            [_skill("Product Strategy . Backlog Prioritization . User Research")]
        )
        assert "product strategy" in result
        assert "backlog prioritization" in result
        assert "user research" in result

    def test_strips_section_headers(self):
        # "● Programming Languages: C++, Rust" — the header contains ':' and is skipped
        result = _normalize_skills([_skill("● Programming Languages: C++, Rust")])
        # Header "Programming Languages:" has a colon — should be dropped
        assert not any("languages" in s and "programming" in s for s in result)

    def test_drops_bullet_prefix(self):
        result = _normalize_skills([_skill("● Python")])
        assert "python" in result

    def test_deduplicates_case_insensitively(self):
        result = _normalize_skills(
            [_skill("Python"), _skill("python"), _skill("PYTHON")]
        )
        assert result.count("python") == 1

    def test_skips_very_short_fragments(self):
        result = _normalize_skills([_skill("AI | ML | x")])
        assert "ai" in result
        assert "ml" in result
        assert "x" not in result  # single char — dropped

    def test_empty_skill_name(self):
        s = MagicMock()
        s.skill_name = None
        assert _normalize_skills([s]) == []


# ---------------------------------------------------------------------------
# _skill_matches
# ---------------------------------------------------------------------------


class TestSkillMatches:
    def test_exact_substring_match(self):
        assert _skill_matches("python programming", "python") is True

    def test_word_level_overlap(self):
        # "aws" in "cloud computing (aws)" via word overlap
        assert _skill_matches("aws experience required", "cloud computing aws") is True

    def test_no_false_positive_req_in_skill(self):
        # Old bug: "management" in long skill string caused false positive.
        # The new code does NOT check req in skill — only skill in req or word overlap.
        long_skill = (
            "product strategy backlog prioritization user research agile delivery"
        )
        # "bookkeeping" should NOT match a long product-management skill string
        assert _skill_matches("bookkeeping", long_skill) is False

    def test_no_match_unrelated(self):
        assert _skill_matches("financial accounting", "python") is False

    def test_case_insensitive(self):
        assert _skill_matches("Python", "python") is True


# ---------------------------------------------------------------------------
# _score_title  (max 25 pts)
# ---------------------------------------------------------------------------


class TestScoreTitle:
    def test_exact_match(self):
        assert _score_title("Product Manager", ["Product Manager"]) == pytest.approx(
            25.0
        )

    def test_partial_word_overlap(self):
        # "Senior Product Manager" shares "product" and "manager" with "Product Manager"
        score = _score_title("Senior Product Manager", ["Product Manager"])
        assert score > 12.0  # meaningful overlap

    def test_unrelated_titles_low_score(self):
        score = _score_title("Chef de Cuisine", ["Software Engineer"])
        assert score < 12.5

    def test_no_target_titles(self):
        assert _score_title("Engineer", []) == 0.0
        assert _score_title("Engineer", None) == 0.0

    def test_multiple_targets_takes_best(self):
        score_single = _score_title("Product Manager", ["UX Designer"])
        score_multi = _score_title(
            "Product Manager", ["UX Designer", "Product Manager"]
        )
        assert score_multi > score_single

    def test_case_insensitive(self):
        assert _score_title("PRODUCT MANAGER", ["product manager"]) == pytest.approx(
            25.0
        )


# ---------------------------------------------------------------------------
# _score_skills  (max 35 pts)
# ---------------------------------------------------------------------------


class TestScoreSkills:
    def test_full_coverage(self):
        reqs = ["Python", "SQL", "Docker"]
        skills = [_skill("python"), _skill("sql"), _skill("docker")]
        assert _score_skills(reqs, skills) == pytest.approx(35.0)

    def test_partial_coverage(self):
        reqs = ["Python", "SQL", "Docker", "Kubernetes"]
        skills = [_skill("python"), _skill("sql")]
        score = _score_skills(reqs, skills)
        assert score == pytest.approx(17.5)  # 2/4 = 50% → 17.5 pts

    def test_no_skills(self):
        assert _score_skills(["Python"], []) == 0.0

    def test_no_requirements_returns_neutral(self):
        # Jobs without parsed requirements (e.g. LinkedIn) get 40% of max = 14 pts
        assert _score_skills([], [_skill("python")]) == pytest.approx(35.0 * 0.4)
        assert _score_skills(None, [_skill("python")]) == pytest.approx(35.0 * 0.4)

    def test_more_skills_than_reqs_does_not_penalise(self):
        reqs = ["Python", "SQL"]
        skills = [_skill(f"skill{i}") for i in range(18)] + [
            _skill("python"),
            _skill("sql"),
        ]
        assert _score_skills(reqs, skills) == pytest.approx(35.0)

    def test_substring_match(self):
        # "aws" should match a skill "cloud computing aws"
        reqs = ["aws"]
        skills = [_skill("cloud computing aws")]
        assert _score_skills(reqs, skills) == pytest.approx(35.0)

    def test_no_false_positive_long_skill_string(self):
        # A long un-normalized skill blob should NOT match an unrelated requirement
        reqs = ["bookkeeping", "accounts payable"]
        skills = [
            _skill("Product Strategy . Backlog Prioritization . User Research . Agile")
        ]
        # After normalization: ["product strategy", "backlog prioritization", ...]
        # None of which should match "bookkeeping" or "accounts payable"
        score = _score_skills(reqs, skills)
        assert score == 0.0

    def test_concatenated_skills_split_correctly(self):
        # "Excel | Power BI | Salesforce" should split and match "salesforce crm"
        reqs = ["Salesforce CRM"]
        skills = [_skill("Excel | Power BI | Salesforce")]
        assert _score_skills(reqs, skills) == pytest.approx(35.0)


# ---------------------------------------------------------------------------
# _score_experience  (max 15 pts)
# ---------------------------------------------------------------------------


class TestScoreExperience:
    def test_exact_level_match(self):
        job = _job(title="Senior Engineer")
        prefs = _prefs(experience_level="senior")
        assert _score_experience(job, prefs) == pytest.approx(15.0)

    def test_one_level_off(self):
        job = _job(title="Mid-level Engineer")
        prefs = _prefs(experience_level="senior")
        assert _score_experience(job, prefs) == pytest.approx(9.0)  # 15 * 0.6

    def test_two_levels_off(self):
        job = _job(title="Junior Engineer")
        prefs = _prefs(experience_level="senior")
        assert _score_experience(job, prefs) == pytest.approx(3.0)  # 15 * 0.2

    def test_director_vs_senior_penalised(self):
        job = _job(title="Director of Engineering")
        prefs = _prefs(experience_level="senior")
        # director=4, senior=3 → diff=1 → 9pts
        assert _score_experience(job, prefs) == pytest.approx(9.0)

    def test_no_seniority_signal_benefit_of_doubt(self):
        job = _job(title="Engineer", description="We need someone great.")
        prefs = _prefs(experience_level="senior")
        assert _score_experience(job, prefs) == pytest.approx(11.25)  # 15 * 0.75

    def test_no_user_preference_neutral(self):
        job = _job(title="Senior Engineer")
        prefs = _prefs(experience_level=None)
        assert _score_experience(job, prefs) == pytest.approx(7.5)  # 15 * 0.5


# ---------------------------------------------------------------------------
# _score_salary  (max 10 pts — unchanged)
# ---------------------------------------------------------------------------


class TestScoreSalary:
    def test_in_range_full_marks(self):
        job = _job(salary_min=60_000)
        prefs = _prefs(salary_min=57_000, salary_max=70_000)
        assert _score_salary(job, prefs) == pytest.approx(10.0)

    def test_in_75_to_90pct_band(self):
        # 50k/57k ≈ 87.7% → falls in the 75–90% bracket → 3pts
        job = _job(salary_min=50_000)
        prefs = _prefs(salary_min=57_000, salary_max=70_000)
        assert _score_salary(job, prefs) == pytest.approx(3.0)

    def test_below_75pct_of_min_zero(self):
        job = _job(salary_min=40_000)
        prefs = _prefs(salary_min=57_000, salary_max=70_000)
        assert _score_salary(job, prefs) == pytest.approx(0.0)

    def test_25_pct_over_max_penalised(self):
        job = _job(salary_min=85_000)
        prefs = _prefs(salary_min=57_000, salary_max=70_000)
        # 85k/70k = 1.21 → under 1.25 → 8pts
        assert _score_salary(job, prefs) == pytest.approx(8.0)

    def test_50_pct_over_max_penalised(self):
        job = _job(salary_min=100_000)
        prefs = _prefs(salary_min=57_000, salary_max=70_000)
        # 100k/70k = 1.43 → between 1.25 and 1.5 → 5pts
        assert _score_salary(job, prefs) == pytest.approx(5.0)

    def test_directorial_salary_penalised(self):
        job = _job(salary_min=150_000)
        prefs = _prefs(salary_min=57_000, salary_max=70_000)
        # 150k/70k = 2.14 → > 1.5 → 2pts
        assert _score_salary(job, prefs) == pytest.approx(2.0)

    def test_no_salary_listed_benefit_of_doubt(self):
        job = _job(salary_min=None)
        prefs = _prefs(salary_min=57_000, salary_max=70_000)
        assert _score_salary(job, prefs) == pytest.approx(7.5)

    def test_no_user_preference_full_marks(self):
        job = _job(salary_min=30_000)
        prefs = _prefs(salary_min=None, salary_max=None)
        assert _score_salary(job, prefs) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# _location_terms
# ---------------------------------------------------------------------------


class TestLocationTerms:
    def test_simple_city_country(self):
        terms = _location_terms(["London, UK"])
        assert "london" in terms
        assert "uk" not in terms  # too short (≤2 chars)

    def test_full_street_address_filters_digits(self):
        terms = _location_terms(["C/ Los Naranjos 66, Casares 29692, Málaga, Spain"])
        assert "málaga" in terms
        assert "spain" in terms
        assert not any("66" in t or "29692" in t for t in terms)

    def test_multiple_locations(self):
        terms = _location_terms(["Madrid, Spain", "Barcelona, Spain"])
        assert "madrid" in terms
        assert "barcelona" in terms
        assert "spain" in terms


# ---------------------------------------------------------------------------
# _score_location_remote  (max 15 pts)
# ---------------------------------------------------------------------------


class TestScoreLocationRemote:
    def test_remote_pref_remote_job(self):
        job = _job(remote="remote")
        prefs = _prefs(remote_preference="remote")
        assert _score_location_remote(job, prefs) == pytest.approx(15.0)

    def test_remote_pref_onsite_job(self):
        job = _job(remote="onsite")
        prefs = _prefs(remote_preference="remote")
        assert _score_location_remote(job, prefs) == pytest.approx(0.0)

    def test_hybrid_pref_remote_job(self):
        job = _job(remote="remote")
        prefs = _prefs(remote_preference="hybrid")
        assert _score_location_remote(job, prefs) == pytest.approx(10.5)  # 15 * 0.7

    def test_location_match_from_full_address(self):
        job = _job(location="Málaga, Spain", remote="")
        prefs = _prefs(
            remote_preference=None,
            preferred_locations=["C/ Los Naranjos 66, Casares 29692, Málaga, Spain"],
        )
        assert _score_location_remote(job, prefs) == pytest.approx(15.0)

    def test_country_gate_blocks_wrong_country(self):
        # Gate only fires when preferred_countries is explicitly set
        job = _job(location="Malaga, Swan Area", country="au")
        prefs = _prefs(
            preferred_locations=["Malaga"],
            preferred_countries=["es", "gb"],
        )
        assert _score_location_remote(job, prefs) == pytest.approx(0.0)

    def test_country_gate_allows_correct_country(self):
        job = _job(location="Malaga, Andalusia", country="es")
        prefs = _prefs(
            preferred_locations=["Malaga", "Cadiz"],
            preferred_countries=["es"],
        )
        assert _score_location_remote(job, prefs) == pytest.approx(15.0)

    def test_country_gate_skipped_when_no_preferred_countries(self):
        # No preferred_countries set → gate is inactive, city match still works
        job = _job(location="Malaga, Swan Area", country="au")
        prefs = _prefs(preferred_locations=["Malaga"], preferred_countries=None)
        assert _score_location_remote(job, prefs) == pytest.approx(15.0)

    def test_country_gate_skipped_when_no_job_country(self):
        # Jobs without a country set should still match on location substring
        job = _job(location="Malaga, Swan Area", country=None)
        prefs = _prefs(
            preferred_locations=["Malaga"],
            preferred_countries=["es", "gb"],
        )
        assert _score_location_remote(job, prefs) == pytest.approx(15.0)

    def test_no_prefs_returns_zero(self):
        job = _job(remote="remote", location="London")
        assert _score_location_remote(job, None) == pytest.approx(0.0)
