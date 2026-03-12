"""Tests for the LLM-based CV parser."""

from unittest.mock import MagicMock, patch

# cv_parser_llm lives at web/api/ root — already on sys.path via conftest
from cv_parser_llm import parse_cv_with_llm

SAMPLE_CV = """
John Smith
Software Engineer | London, UK
john@example.com

Skills: Python, JavaScript, SQL, React, Docker, Kubernetes
Leadership, Communication, Agile
Languages: English (native), French (intermediate)

Experience:
Acme Corp — Senior Engineer (2021–present)
  Built distributed data pipelines using Python and Kafka.
"""


def _mock_response(input_data: dict) -> MagicMock:
    """Build a minimal fake Anthropic response with one tool-use block."""
    block = MagicMock()
    block.input = input_data
    response = MagicMock()
    response.content = [block]
    return response


FULL_RESULT = {
    "personal_info": {
        "name": "John Smith",
        "email": "john@example.com",
        "location": "London, UK",
        "title": "Software Engineer",
    },
    "skills": {
        "technical": ["Python", "JavaScript", "SQL", "React", "Docker"],
        "soft": ["Leadership", "Communication"],
        "languages": ["English", "French"],
    },
    "experience": [
        {
            "company": "Acme Corp",
            "title": "Senior Engineer",
            "duration": "2021–present",
            "description": "Built distributed data pipelines.",
        }
    ],
}


class TestParseCvWithLlm:
    def test_returns_structured_data(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("cv_parser_llm.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _mock_response(
                FULL_RESULT
            )
            result = parse_cv_with_llm(SAMPLE_CV)

        assert result["personal_info"]["name"] == "John Smith"
        assert "Python" in result["skills"]["technical"]
        assert "Leadership" in result["skills"]["soft"]
        assert "English" in result["skills"]["languages"]

    def test_returns_empty_dict_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = parse_cv_with_llm(SAMPLE_CV)
        assert result == {}

    def test_returns_empty_dict_on_api_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("cv_parser_llm.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = RuntimeError(
                "Connection error"
            )
            result = parse_cv_with_llm(SAMPLE_CV)
        assert result == {}

    def test_truncates_cv_to_max_chars(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        long_cv = "x" * 20_000
        with patch("cv_parser_llm.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _mock_response({})
            parse_cv_with_llm(long_cv)
            call_kwargs = mock_cls.return_value.messages.create.call_args[1]
            sent_content = call_kwargs["messages"][0]["content"]
        # "Parse this CV:\n\n" prefix + 12_000 chars of CV
        assert len(sent_content) <= 12_020

    def test_uses_tool_choice_to_force_structure(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("cv_parser_llm.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _mock_response({})
            parse_cv_with_llm(SAMPLE_CV)
            call_kwargs = mock_cls.return_value.messages.create.call_args[1]
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "parse_cv"}
        assert call_kwargs["tools"][0]["name"] == "parse_cv"

    def test_uses_haiku_model(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("cv_parser_llm.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _mock_response({})
            parse_cv_with_llm(SAMPLE_CV)
            call_kwargs = mock_cls.return_value.messages.create.call_args[1]
        assert "haiku" in call_kwargs["model"]
