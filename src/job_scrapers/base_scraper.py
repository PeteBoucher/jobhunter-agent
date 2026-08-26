"""Base scraper abstract class for all job scrapers."""

import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from src.models import Job, ScraperMetric, UserPreferences

_logger = logging.getLogger("jobhunter.scrapers")

# All US state names in lowercase.  Used by _infer_country to detect US-only
# remote roles whose country restriction is embedded in the description text
# rather than a structured field.
_US_STATES = frozenset(
    [
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
    ]
)

# Require at least this many US state names in a description before inferring
# country="us".  Threshold > 1 avoids false positives: "Georgia" alone is
# ambiguous with the country Georgia; "Texas" appears in many non-US contexts.
_US_STATE_THRESHOLD = 3

# Per-country regex fragments for residency detection.
# "strong" — unambiguous even mid-sentence; safe for verb+country patterns.
# "weak"   — too short/common as English words; only safe in "X-only" suffix.
_RESIDENCY_COUNTRIES: dict = {
    "us": {
        "strong": [r"united states", r"u\.s\.a?\.?", r"\busa\b"],
        "weak": [r"\bus\b"],
    },
    "gb": {
        "strong": [r"united kingdom", r"u\.k\.", r"england", r"scotland", r"wales"],
        "weak": [r"\buk\b"],
    },
    "pl": {"strong": [r"poland"], "weak": []},
    "de": {"strong": [r"germany"], "weak": []},
    "nl": {"strong": [r"netherlands"], "weak": []},
    "fr": {"strong": [r"france"], "weak": []},
    "es": {"strong": [r"spain"], "weak": []},
    "it": {"strong": [r"italy"], "weak": []},
    "au": {"strong": [r"australia"], "weak": []},
    "ca": {"strong": [r"canada"], "weak": []},
    "ie": {"strong": [r"ireland"], "weak": []},
    "se": {"strong": [r"sweden"], "weak": []},
    "no": {"strong": [r"norway"], "weak": []},
    "dk": {"strong": [r"denmark"], "weak": []},
    "pt": {"strong": [r"portugal"], "weak": []},
    "be": {"strong": [r"belgium"], "weak": []},
    "ch": {"strong": [r"switzerland"], "weak": []},
    "ro": {"strong": [r"romania"], "weak": []},
    "in": {"strong": [r"india"], "weak": []},
}

# Verbs/prepositions that, immediately before a strong country name, signal a
# residency requirement.
#   - "executed? from"  catches "executed from the United States" without
#     matching "execution excellence" (noun — not a residency verb)
#   - \b word boundaries prevent mid-word matches like work in "workover"
_RESIDENCY_VERB_RE = (
    r"\b(resides?|residing|located?|based|employed?"
    r"|executed?\s+from|work(?:ed|ing)?\s+(?:from|within|in|out\s+of)"
    r"|within|candidates?\s+in|open\s+to\s*.{0,20}\s*in"
    r"|this\s+role\s*.{0,20}\s*in)\b"
)

# Compile per-country patterns once at import time.
# Each entry: (iso2_code, location_re, residency_re, only_re)
#   location_re  — bare country name; used for structured location strings only
#   residency_re — residency verb + strong country name in free-text
#   only_re      — "country-only / country-based" suffix (strong + weak)
_COUNTRY_RESIDENCY_PATTERNS: list = []
for _code, _frags in _RESIDENCY_COUNTRIES.items():
    _strong_alt = "|".join(_frags["strong"])
    _all_alt = "|".join(_frags["strong"] + _frags["weak"])
    _COUNTRY_RESIDENCY_PATTERNS.append(
        (
            _code,
            re.compile(rf"\b({_all_alt})\b", re.IGNORECASE),
            re.compile(
                rf"{_RESIDENCY_VERB_RE}.{{0,60}}({_strong_alt})",
                re.IGNORECASE,
            ),
            re.compile(
                rf"\b({_all_alt})[- ](only|based|residents only|candidates only)\b",
                re.IGNORECASE,
            ),
        )
    )


class BaseScraper(ABC):
    """Abstract base class for all job scrapers.

    Defines the interface that all job scrapers must implement.
    """

    def __init__(self, session: Session):
        """Initialize scraper with database session.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.source_name = self._get_source_name()
        self.logger = logging.getLogger(f"jobhunter.scrapers.{self.source_name}")
        # Set by scrape() after _fetch_jobs() succeeds; 0 means the source
        # returned nothing (API down, auth failure, HTML changed, etc.)
        self.last_raw_count: int = 0
        # Set by _fetch_jobs() when 0 results is intentional (quota exhausted,
        # no credentials, etc.) rather than a sign of breakage. The lambda
        # suppresses zero-result alerts when this is non-None.
        self.last_skip_reason: Optional[str] = None

    @abstractmethod
    def _get_source_name(self) -> str:
        """Get the name of the job source.

        Returns:
            Name of the source (e.g., 'github', 'microsoft')
        """
        pass

    @abstractmethod
    def _fetch_jobs(self, **kwargs) -> List[dict]:
        """Fetch raw job data from the source.

        This method should be implemented by subclasses to handle
        the actual scraping/API calls.

        Args:
            **kwargs: Source-specific parameters

        Returns:
            List of dictionaries containing raw job data
        """
        pass

    @abstractmethod
    def _parse_job(self, raw_job: dict) -> dict:
        """Parse raw job data into standardized format.

        The returned dict is read with `.get(key)` by `_create_job_object()`
        below — a missing or misspelled key fails silently as `None` on that
        `Job` column, not as an error. This is the one place scraper output
        actually has to agree with the rest of the codebase, so the field
        names and types below are load-bearing, not a suggestion. (This bit
        the generated Experis scraper: it returned "company_name" and
        "published_date" instead of "company"/"posted_date", so every job
        silently saved with a null company and null posted_date.)

        Required keys:
            source_job_id (str), title (str), company (str), apply_url (str)
                — not "url".

        Optional keys (all default to None via .get() if omitted):
            department (str), location (str)
            remote (str) — one of "remote" | "hybrid" | "onsite" | None.
                NOT a bool — job_matcher.py and job_searcher.py both compare
                it against these literal strings (`.lower() == "remote"`,
                `Job.remote == "onsite"`); a bool silently stores as "1"/"0"
                (or an error, on strict backends) and matches nothing.
            country (str) — lowercase ISO2 (e.g. "es", "gb"). Leave unset/None
                when the source has no reliable country data; the base class
                infers it from description/location rather than guessing.
            salary_min / salary_max (float)
            description (str)
            requirements (str) — despite the DB column being JSON-typed, the
                convention everywhere in this codebase is a plain string (or
                None), never an actual list.
            nice_to_haves (str) — rarely populated; None is fine.
            posted_date (datetime.datetime) — an actual datetime object, not
                an ISO date string. SQLAlchemy's DateTime column expects one.
            company_industry (str), company_size (str)
            source_type (str) — "company_portal" for a single company's own
                careers site (defaults to "aggregator" if omitted, which is
                wrong for a company-portal scraper — set it explicitly).

        There is no `employment_type` field on the `Job` model. Returning one
        doesn't error, it's just silently discarded — don't spend scraping
        effort computing a value nothing reads.

        `validate_parsed_job()` below checks a returned dict against this
        schema mechanically — the AI scraper generator runs it against a
        live sample automatically after generating a draft.

        Args:
            raw_job: Raw job data from the source

        Returns:
            Parsed job data with standardized fields (see above)
        """
        pass

    def scrape(self, **kwargs) -> List[Job]:
        """Main scraping method with retry/backoff for transient fetch errors.

        Fetches jobs from the source, parses them, and stores in database.

        Supports optional kwargs:
          - max_retries: int = number of fetch retries (default 3)
          - backoff_factor: float = base seconds for exponential backoff (default 1.0)

        Args:
            **kwargs: Source-specific parameters

        Returns:
            List of Job objects that were scraped
        """
        max_retries = int(kwargs.pop("max_retries", 3))
        backoff = float(kwargs.pop("backoff_factor", 1.0))

        try:
            # Retry _fetch_jobs on transient errors
            last_exc: Optional[BaseException] = None
            raw_jobs: Optional[List[Any]] = None
            for attempt in range(max_retries):
                try:
                    raw_jobs = self._fetch_jobs(**kwargs)
                    self.last_raw_count = len(raw_jobs)
                    break
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        sleep_time = backoff * (2**attempt)
                        time.sleep(sleep_time)
                        continue
                    else:
                        raise

            if raw_jobs is None:
                raise RuntimeError(
                    f"Failed to fetch jobs from {self.source_name}: {last_exc}"
                )

            # Release the DB connection back to the pool before making further
            # queries. _fetch_jobs() can run for a long time (e.g. LinkedIn with
            # many HTTP requests + sleep delays), leaving the connection idle long
            # enough for Neon to close the SSL link. invalidate() drops the
            # connection without attempting a rollback (session.close() tries to
            # rollback, which itself raises if the SSL link is already dead).
            # pool_pre_ping will then open a fresh connection on the next checkout.
            self.session.invalidate()

            # Load all existing source_job_ids for this source in one query
            existing_ids: set = self._load_existing_ids()

            jobs: List[Job] = []
            parse_errors = 0
            seen_source_ids: set = set()

            for raw_job in raw_jobs:
                try:
                    parsed_data = self._parse_job(raw_job)
                    job_id = parsed_data.get("source_job_id")
                    if job_id:
                        seen_source_ids.add(job_id)
                    if job_id in existing_ids:
                        continue
                    jobs.append(self._create_job_object(parsed_data))
                except Exception as e:
                    self.logger.exception(
                        f"Error parsing job from {self.source_name}: {e}"
                    )
                    parse_errors += 1
                    continue

            # Save all new jobs in a single commit
            if jobs:
                self.session.add_all(jobs)
                self.session.commit()

            # Mark all jobs seen in this fetch as active and refresh scraped_at
            # so the expiry clock resets for still-live listings.
            if seen_source_ids:
                self.session.query(Job).filter(
                    Job.source == self.source_name,
                    Job.source_job_id.in_(seen_source_ids),
                ).update(
                    {"scraped_at": datetime.utcnow(), "is_active": True},
                    synchronize_session=False,
                )
                self.session.commit()

            # Record a single summary metric for the run
            try:
                self._record_metric(
                    "jobs_added",
                    len(jobs),
                    f"raw={len(raw_jobs)} errors={parse_errors}",
                )
            except Exception:
                self.logger.debug("Failed to record jobs_added metric")

            return jobs

        except Exception as e:
            self.session.rollback()
            raise RuntimeError(f"Error scraping {self.source_name}: {e}") from e

    def _record_metric(
        self, action: str, value: int = 1, details: Optional[str] = None
    ) -> None:
        """Helper to persist a scraper metric row.

        This uses a short-lived session commit to ensure metrics are recorded
        even if the main scraping transaction rolls back.
        """
        try:
            metric = ScraperMetric(
                source=self.source_name,
                action=action,
                value=value,
                details=details,
            )
            self.session.add(metric)
            self.session.commit()
        except Exception:
            # If recording fails, try to rollback the metric insert
            # to keep the session stable
            try:
                self.session.rollback()
            except Exception:
                pass

    def _search_terms_from_prefs(
        self, fallback: Optional[List[str]] = None
    ) -> List[str]:
        """Return deduplicated search terms derived from all users' target_titles.

        Falls back to *fallback* (or a minimal generic list) when no preferences
        exist yet — e.g. before the first user signs up.
        """
        rows = self.session.query(UserPreferences.target_titles).all()
        terms: List[str] = []
        seen: set = set()
        for (titles,) in rows:
            if not titles:
                continue
            for t in titles:
                key = t.lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    terms.append(t.strip())
        if terms:
            self.logger.debug("search_terms_from_prefs source=db count=%d", len(terms))
            return terms
        default = fallback or [
            "product manager",
            "software engineer",
            "project manager",
        ]
        self.logger.debug(
            "search_terms_from_prefs source=fallback count=%d", len(default)
        )
        return default

    def _countries_from_prefs(self, fallback: Optional[List[str]] = None) -> List[str]:
        """Return deduplicated ISO2 country codes from all users' preferred_countries.

        Falls back to *fallback* (or ["gb"]) when no preferences exist yet.
        """
        rows = self.session.query(UserPreferences.preferred_countries).all()
        codes: List[str] = []
        seen: set = set()
        for (countries,) in rows:
            if not countries:
                continue
            for code in countries:
                c = code.lower().strip()
                if c and c not in seen:
                    seen.add(c)
                    codes.append(c)
        if codes:
            self.logger.debug("countries_from_prefs source=db count=%d", len(codes))
            return codes
        default = fallback or ["gb"]
        self.logger.debug("countries_from_prefs source=fallback count=%d", len(default))
        return default

    @staticmethod
    def _infer_country(
        description: Optional[str], location: Optional[str] = None
    ) -> Optional[str]:
        """Infer a country restriction from job description and location text.

        Many remote jobs embed residency requirements in free-text (e.g.
        "open to candidates who reside in: Arizona, California, Texas…")
        rather than a structured country field.  This heuristic detects:

        - Residency/location clauses near a country name for all major markets
          ("based in Poland", "executed from the United States", "UK-only")
        - US state enumerations: ≥3 US state names → infer "us"
        - Location string cues: "Remote, USA", "United Kingdom"

        Returns a lowercase ISO2 country code, or None if no restriction
        can be confidently detected.
        """
        # --- Location field (fast path, structured) ---
        # The location field is already structured ("Remote, United States"),
        # so a bare country name match is sufficient — no verb required.
        if location:
            for code, location_re, _, __ in _COUNTRY_RESIDENCY_PATTERNS:
                if location_re.search(location):
                    return code

        if not description:
            return None

        # --- Residency/location clause + country name in free text ---
        for code, _, residency_re, only_re in _COUNTRY_RESIDENCY_PATTERNS:
            if residency_re.search(description) or only_re.search(description):
                return code

        # --- US state enumeration (fallback for implicit US restrictions) ---
        # Count distinct state names that appear as whole words in the text.
        desc_lower = description.lower()
        state_count = sum(
            1
            for state in _US_STATES
            if re.search(r"\b" + re.escape(state) + r"\b", desc_lower)
        )
        if state_count >= _US_STATE_THRESHOLD:
            _logger.debug(
                "_infer_country: detected %d US states → country=us", state_count
            )
            return "us"

        return None

    def _load_db_config(self) -> List[dict]:
        """Return active scraper_config rows for this source as a list of dicts.

        Used by scrapers to merge DB-configured companies with their hardcoded
        defaults, so new companies can be added without a Lambda rebuild.
        """
        from src.models import ScraperConfig

        try:
            rows = (
                self.session.query(ScraperConfig)
                .filter_by(source_name=self._get_source_name(), is_active=True)
                .all()
            )
            return [row.config for row in rows]
        except Exception as e:
            self.logger.warning("Failed to load DB scraper config: %s", e)
            return []

    def _load_existing_ids(self) -> set:
        """Load all known source_job_ids for this source in one query."""
        rows = (
            self.session.query(Job.source_job_id)
            .filter(Job.source == self.source_name)
            .all()
        )
        return {row[0] for row in rows}

    def _create_job_object(self, parsed_data: dict) -> Job:
        """Create a Job object from parsed data.

        Args:
            parsed_data: Parsed job data

        Returns:
            Job object ready to be saved
        """
        # Use the explicitly parsed country when available; otherwise try to
        # infer it from description text (catches US-state-restricted remote
        # roles that embed residency requirements in free text).
        country = parsed_data.get("country") or self._infer_country(
            parsed_data.get("description"), parsed_data.get("location")
        )

        return Job(
            source=self.source_name,
            source_job_id=parsed_data.get("source_job_id"),
            title=parsed_data.get("title"),
            company=parsed_data.get("company"),
            department=parsed_data.get("department"),
            location=parsed_data.get("location"),
            remote=parsed_data.get("remote"),
            country=country,
            salary_min=parsed_data.get("salary_min"),
            salary_max=parsed_data.get("salary_max"),
            description=parsed_data.get("description"),
            requirements=parsed_data.get("requirements"),
            nice_to_haves=parsed_data.get("nice_to_haves"),
            apply_url=parsed_data.get("apply_url"),
            posted_date=parsed_data.get("posted_date"),
            scraped_at=datetime.utcnow(),
            company_industry=parsed_data.get("company_industry"),
            company_size=parsed_data.get("company_size"),
            source_type=parsed_data.get("source_type", "aggregator"),
        )


# ── _parse_job() output validation ──────────────────────────────────────────
#
# Checks a _parse_job() dict against the schema documented on _parse_job()
# above — the same problems (wrong key name, wrong type) that were caught by
# hand in the generated Experis scraper. Kept next to _create_job_object(),
# the method that actually reads these keys, so the two can't drift apart.

REQUIRED_PARSED_JOB_KEYS = ("source_job_id", "title", "company", "apply_url")

KNOWN_OPTIONAL_PARSED_JOB_KEYS = frozenset(
    {
        "department",
        "location",
        "remote",
        "country",
        "salary_min",
        "salary_max",
        "description",
        "requirements",
        "nice_to_haves",
        "posted_date",
        "company_industry",
        "company_size",
        "source_type",
    }
)

_VALID_REMOTE_VALUES = frozenset({"remote", "hybrid", "onsite"})


def validate_parsed_job(parsed: dict) -> List[str]:
    """Check a _parse_job() output dict against the documented schema.

    Returns a list of human-readable problem descriptions; an empty list
    means the dict is valid. Does not require a database or a live scraper
    instance — pure dict-in, list-out.
    """
    problems: List[str] = []

    for key in REQUIRED_PARSED_JOB_KEYS:
        if not parsed.get(key):
            problems.append(f"missing or empty required key {key!r}")

    remote = parsed.get("remote")
    if remote is not None and remote not in _VALID_REMOTE_VALUES:
        problems.append(
            f'"remote" must be "remote"/"hybrid"/"onsite"/None, got '
            f"{remote!r} ({type(remote).__name__}) — job_matcher.py and "
            "job_searcher.py compare it against these exact strings"
        )

    posted_date = parsed.get("posted_date")
    if posted_date is not None and not isinstance(posted_date, datetime):
        problems.append(
            '"posted_date" must be a datetime object or None, got '
            f"{type(posted_date).__name__} — SQLAlchemy's DateTime column "
            "expects one, not an ISO string"
        )

    for key in ("salary_min", "salary_max"):
        val = parsed.get(key)
        if val is not None and not isinstance(val, (int, float)):
            problems.append(
                f'"{key}" must be a number or None, got {type(val).__name__}'
            )

    if "employment_type" in parsed:
        problems.append(
            '"employment_type" is not a Job model field — it is silently '
            "discarded by _create_job_object(), don't spend scraping effort "
            "computing it"
        )

    unknown = (
        set(parsed) - set(REQUIRED_PARSED_JOB_KEYS) - KNOWN_OPTIONAL_PARSED_JOB_KEYS
    )
    if unknown:
        problems.append(
            f"unknown key(s) not read by _create_job_object(): {sorted(unknown)} "
            "— check for a typo against the canonical name (e.g. company_name "
            "instead of company, published_date instead of posted_date)"
        )

    return problems
