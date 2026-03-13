"""LLM-based CV parser using Claude claude-haiku-4-5 via tool use.

Used as a fallback when the regex-based CVParser yields too little data
(e.g. multi-column PDFs, non-Markdown CVs).  Returns the same dict
structure as CVParser.parse() so the rest of the pipeline is unchanged.
"""

import logging
import os
from typing import Any, Dict

import anthropic

logger = logging.getLogger("jobhunter.api")

# Tool definition — forces Claude to return a structured dict.
_PARSE_CV_TOOL: Dict[str, Any] = {
    "name": "parse_cv",
    "description": (
        "Extract structured information from a CV/resume. "
        "Be thorough — capture every skill, technology, and tool you can identify."
    ),
    "input_schema": {
        "type": "object",
        "required": ["personal_info", "skills"],
        "properties": {
            "personal_info": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Candidate's full name"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "location": {
                        "type": "string",
                        "description": "City, Country or similar",
                    },
                    "title": {
                        "type": "string",
                        "description": "Current or most recent job title",
                    },
                },
            },
            "professional_summary": {"type": "string"},
            "skills": {
                "type": "object",
                "required": ["technical", "soft", "languages"],
                "properties": {
                    "technical": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Technical skills, tools, languages, frameworks",
                    },
                    "soft": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Soft skills and management skills",
                    },
                    "languages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Spoken/written human languages (e.g. English, French)",  # noqa: E501
                    },
                },
            },
            "experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "title": {"type": "string"},
                        "duration": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "institution": {"type": "string"},
                        "degree": {"type": "string"},
                        "field": {"type": "string"},
                        "year": {"type": "string"},
                    },
                },
            },
        },
    },
}

# Cap input at ~3 k tokens to keep latency and cost low.
_MAX_CV_CHARS = 12_000


def parse_cv_with_llm(text: str) -> Dict[str, Any]:
    """Parse CV text with Claude claude-haiku-4-5 via tool use for guaranteed structure.

    Returns a dict matching CVParser.parse() output on success, or an empty
    dict if the API key is absent or the call fails (caller falls back to
    regex results).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping LLM CV parse")
        return {}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            tools=[_PARSE_CV_TOOL],
            tool_choice={"type": "tool", "name": "parse_cv"},
            messages=[
                {
                    "role": "user",
                    "content": f"Parse this CV:\n\n{text[:_MAX_CV_CHARS]}",
                }
            ],
        )
        if response.stop_reason == "max_tokens":
            logger.warning(
                "llm_cv_parse_truncated — increase max_tokens or reduce CV length"
            )
        result: Dict[str, Any] = response.content[0].input
        skill_count = sum(
            len(v) for v in result.get("skills", {}).values() if isinstance(v, list)
        )
        logger.info("llm_cv_parse_ok skills_extracted=%d", skill_count)
        return result

    except Exception as exc:
        logger.error("llm_cv_parse_error error=%r", exc, exc_info=True)
        return {}
