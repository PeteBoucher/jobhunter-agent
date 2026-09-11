"""Tests for the 50skills scraper's id-resolution and language-picking logic.

The 50skills API returns numeric ids for location/department (resolved via a
separate per-company lookup table) and a per-language array for title/
description rather than flat fields — both are exactly the kind of thing
that looks right on the one company checked live (Carbfix) and breaks on
the next one with different data shape (e.g. no English translation, or an
id with no matching lookup entry).
"""

from src.job_scrapers.fiftyskills_scraper import (
    FiftySkillsBoard,
    FiftySkillsScraper,
    _parse_remote,
    _pick_language,
    _resolve_label,
)

_LOCATIONS = [
    {
        "id": 2367,
        "translations": [
            {"language": "is", "title": "Iceland"},
            {"language": "en", "title": "Iceland"},
        ],
    },
    {
        "id": 2370,
        "translations": [
            {"language": "is", "title": "Ísland"},
            {"language": "en", "title": "Anywhere"},
        ],
    },
    {
        "id": 9999,
        "translations": [{"language": "is", "title": "Aðeins íslenska"}],
    },
]


class TestResolveLabel:
    def test_resolves_english_translation(self):
        assert _resolve_label(2367, _LOCATIONS) == "Iceland"

    def test_falls_back_to_first_translation_when_no_english(self):
        assert _resolve_label(9999, _LOCATIONS) == "Aðeins íslenska"

    def test_returns_none_for_unknown_id(self):
        assert _resolve_label(1, _LOCATIONS) is None

    def test_returns_none_for_none_id(self):
        assert _resolve_label(None, _LOCATIONS) is None

    def test_returns_none_for_empty_table(self):
        assert _resolve_label(2367, []) is None
        assert _resolve_label(2367, None) is None


class TestPickLanguage:
    def test_prefers_english(self):
        langs = [{"language": "is", "title": "A"}, {"language": "en", "title": "B"}]
        assert _pick_language(langs)["title"] == "B"

    def test_falls_back_to_first_when_no_english(self):
        langs = [{"language": "is", "title": "A"}, {"language": "fr", "title": "C"}]
        assert _pick_language(langs)["title"] == "A"

    def test_returns_none_for_empty_list(self):
        assert _pick_language([]) is None


class TestParseRemote:
    def test_anywhere_location_is_remote(self):
        assert _parse_remote("Anywhere", None) == "remote"

    def test_remote_keyword_in_location(self):
        assert _parse_remote("Remote - EU", None) == "remote"

    def test_hybrid_location(self):
        assert _parse_remote("Reykjavik (Hybrid)", None) == "hybrid"

    def test_falls_back_to_description_keyword(self):
        assert _parse_remote("Reykjavik", "This is a fully remote role.") == "remote"

    def test_no_signal_returns_none(self):
        assert _parse_remote("Reykjavik", "Join our team in the office.") is None
        assert _parse_remote(None, None) is None


class TestParseJob:
    def _job(self, **overrides):
        job = {
            "id": 44425,
            "url": "https://jobs.50skills.com/carbfix/44425",
            "location": 2367,
            "department": None,
            "languages": [
                {
                    "language": "is",
                    "title": "Starfsnám",
                    "description": "<p>Íslenskur texti</p>",
                },
                {
                    "language": "en",
                    "title": "Internship opportunities",
                    "description": "<p>Would you like to <b>join</b> us?</p>",
                },
            ],
            "_board": FiftySkillsBoard(company="Carbfix", slug="carbfix"),
            "_lookup": {"locations": _LOCATIONS, "departments": []},
        }
        job.update(overrides)
        return job

    def _scraper(self):
        return FiftySkillsScraper.__new__(FiftySkillsScraper)

    def test_picks_english_title_and_strips_html_description(self):
        p = self._scraper()._parse_job(self._job())
        assert p["title"] == "Internship opportunities"
        assert p["description"] == "Would you like to join us?"

    def test_resolves_location_via_lookup(self):
        p = self._scraper()._parse_job(self._job())
        assert p["location"] == "Iceland"

    def test_source_job_id_is_slug_prefixed(self):
        p = self._scraper()._parse_job(self._job())
        assert p["source_job_id"] == "carbfix:44425"

    def test_apply_url_from_raw_job(self):
        p = self._scraper()._parse_job(self._job())
        assert p["apply_url"] == "https://jobs.50skills.com/carbfix/44425"

    def test_company_portal_source_type(self):
        p = self._scraper()._parse_job(self._job())
        assert p["source_type"] == "company_portal"

    def test_anywhere_location_marks_remote(self):
        p = self._scraper()._parse_job(self._job(location=2370))
        assert p["remote"] == "remote"

    def test_missing_url_falls_back_to_board_page(self):
        job = self._job(url=None)
        p = self._scraper()._parse_job(job)
        assert p["apply_url"] == "https://jobs.50skills.com/carbfix"
