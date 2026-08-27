"""Tests for `job-agent scraper` CLI command group."""

import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """Isolated SQLite DB for each test."""
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    from src.database import init_db

    init_db()
    yield str(db_path)


@pytest.fixture
def runner():
    return CliRunner()


# ── scraper list ──────────────────────────────────────────────────────────────


def test_scraper_list_shows_hardcoded_defaults(runner):
    """scraper list shows hardcoded defaults even with an empty DB."""
    result = runner.invoke(cli, ["scraper", "list"])
    assert result.exit_code == 0
    # Hardcoded defaults from several scrapers should always appear
    assert "greenhouse" in result.output
    assert "workday" in result.output
    assert "hardcoded" in result.output


def test_scraper_list_includes_every_multi_company_scraper(runner):
    """Regression: recruitee (13 boards) and jobboardly (1 board) were
    missing from `scraper list`'s hand-maintained hardcoded-defaults
    enumeration — added when those scrapers were, undercounting the real
    total. Every scraper module that defines a DEFAULT_BOARDS/
    DEFAULT_COMPANIES-style constant must have a matching _hc() call in
    cli.py's scraper_list."""
    result = runner.invoke(cli, ["scraper", "list"])
    assert result.exit_code == 0
    assert "recruitee" in result.output
    assert "jobboardly" in result.output


def test_scraper_list_shows_row_after_insert(runner, tmp_path):
    """A row inserted into scraper_config appears in `scraper list` output."""
    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    row = ScraperConfig(
        source_name="greenhouse", config={"token": "stripe"}, is_active=True
    )
    session.add(row)
    session.commit()
    session.close()

    result = runner.invoke(cli, ["scraper", "list"])
    assert result.exit_code == 0
    assert "greenhouse" in result.output
    assert "stripe" in result.output


def test_scraper_list_filter_by_source(runner):
    """--source flag filters the table to a single ATS."""
    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    session.add(
        ScraperConfig(
            source_name="greenhouse", config={"token": "stripe"}, is_active=True
        )
    )
    session.add(
        ScraperConfig(
            source_name="lever", config={"company": "spotify"}, is_active=True
        )
    )
    session.commit()
    session.close()

    result = runner.invoke(cli, ["scraper", "list", "--source", "greenhouse"])
    assert result.exit_code == 0
    assert "greenhouse" in result.output
    assert "spotify" not in result.output


# ── scraper add (direct --ats --config mode) ──────────────────────────────────


def test_scraper_add_direct_mode(runner):
    """--ats + --config inserts a row without ATS detection."""
    with patch("src.job_scrapers.ats_detector.validate_config", return_value=True):
        result = runner.invoke(
            cli,
            ["scraper", "add", "--ats", "greenhouse", "--config", '{"token":"stripe"}'],
        )
    assert result.exit_code == 0
    assert "Added greenhouse" in result.output

    # Confirm it's in the DB
    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    row = session.query(ScraperConfig).filter_by(source_name="greenhouse").first()
    session.close()
    assert row is not None
    assert row.config == {"token": "stripe"}


def test_scraper_add_dry_run_does_not_persist(runner):
    """--dry-run prints the config but does not write to DB."""
    with patch("src.job_scrapers.ats_detector.validate_config", return_value=True):
        result = runner.invoke(
            cli,
            [
                "scraper",
                "add",
                "--ats",
                "lever",
                "--config",
                '{"company":"spotify"}',
                "--dry-run",
            ],
        )
    assert result.exit_code == 0
    assert "--dry-run" in result.output

    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    count = session.query(ScraperConfig).count()
    session.close()
    assert count == 0


def test_scraper_add_invalid_json_exits(runner):
    """Malformed --config JSON prints an error and exits non-zero."""
    result = runner.invoke(
        cli,
        ["scraper", "add", "--ats", "greenhouse", "--config", "{bad json}"],
    )
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output or "invalid" in result.output.lower()


def test_scraper_add_no_url_no_ats_exits(runner):
    """Calling add without URL or --ats prints usage error."""
    result = runner.invoke(cli, ["scraper", "add"])
    assert result.exit_code != 0


@patch("src.job_scrapers.ats_detector.detect_ats")
@patch("src.job_scrapers.ats_detector.validate_config", return_value=True)
def test_scraper_add_url_detection(mock_validate, mock_detect, runner):
    """URL detection path extracts config and inserts correctly."""
    mock_detect.return_value = ("greenhouse", {"token": "stripe"})

    result = runner.invoke(
        cli, ["scraper", "add", "https://boards.greenhouse.io/stripe"]
    )
    assert result.exit_code == 0
    assert "greenhouse" in result.output

    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    row = session.query(ScraperConfig).filter_by(source_name="greenhouse").first()
    session.close()
    assert row is not None
    assert row.config["token"] == "stripe"


@patch("src.job_scrapers.ats_detector.detect_ats")
@patch("src.job_scrapers.ats_detector.validate_config", return_value=False)
def test_scraper_add_validation_failure_blocks_insert(
    mock_validate, mock_detect, runner
):
    """Validation failure exits non-zero and does not write to DB."""
    mock_detect.return_value = ("ashby", {"subdomain": "paddle"})

    result = runner.invoke(cli, ["scraper", "add", "https://www.paddle.com/careers"])
    assert result.exit_code != 0
    assert "Validation failed" in result.output

    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    count = session.query(ScraperConfig).count()
    session.close()
    assert count == 0


@patch("src.job_scrapers.ats_detector.detect_ats", return_value=None)
@patch("src.job_scrapers.scraper_generator.generate_scraper")
def test_scraper_add_unknown_ats_runs_generator(
    mock_gen, mock_detect, runner, tmp_path
):
    """Unknown ATS URL automatically falls through to AI scraper generation."""
    out_file = tmp_path / "unknown_scraper.py"
    out_file.write_text("# draft")
    mock_gen.return_value = (str(out_file), 2)

    result = runner.invoke(cli, ["scraper", "add", "https://careers.unknown.com/jobs"])
    assert result.exit_code == 0
    mock_gen.assert_called_once()
    assert "Draft written" in result.output or str(out_file) in result.output


# ── scraper disable / remove ──────────────────────────────────────────────────


def test_scraper_disable(runner):
    """Disabling a row sets is_active=False without deleting it."""
    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    row = ScraperConfig(
        source_name="lever", config={"company": "spotify"}, is_active=True
    )
    session.add(row)
    session.commit()
    row_id = row.id
    session.close()

    result = runner.invoke(cli, ["scraper", "disable", str(row_id)])
    assert result.exit_code == 0
    assert "Disabled" in result.output

    session = get_session()
    row = session.query(ScraperConfig).get(row_id)
    session.close()
    assert row is not None
    assert row.is_active is False


def test_scraper_disable_unknown_id(runner):
    """Disabling a non-existent ID exits non-zero."""
    result = runner.invoke(cli, ["scraper", "disable", "9999"])
    assert result.exit_code != 0
    assert "9999" in result.output


def test_scraper_remove(runner):
    """Hard-delete removes the row from the DB entirely."""
    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    row = ScraperConfig(
        source_name="ashby", config={"subdomain": "openai"}, is_active=True
    )
    session.add(row)
    session.commit()
    row_id = row.id
    session.close()

    result = runner.invoke(cli, ["scraper", "remove", str(row_id)])
    assert result.exit_code == 0
    assert "Removed" in result.output

    session = get_session()
    row = session.query(ScraperConfig).get(row_id)
    session.close()
    assert row is None


def test_scraper_remove_unknown_id(runner):
    """Removing a non-existent ID exits non-zero."""
    result = runner.invoke(cli, ["scraper", "remove", "9999"])
    assert result.exit_code != 0


# ── scraper generate ──────────────────────────────────────────────────────────


@patch("src.job_scrapers.ats_detector.validate_config", return_value=True)
@patch("src.job_scrapers.ats_detector.detect_ats")
def test_scraper_generate_known_ats_adds_directly(mock_detect, mock_validate, runner):
    """generate adds to DB directly when the URL matches a known ATS."""
    mock_detect.return_value = ("greenhouse", {"token": "stripe"})

    result = runner.invoke(
        cli, ["scraper", "generate", "https://boards.greenhouse.io/stripe"]
    )
    assert result.exit_code == 0
    assert "greenhouse" in result.output
    assert "scraper add" not in result.output  # no longer a redirect

    from src.database import get_session
    from src.models import ScraperConfig

    session = get_session()
    row = session.query(ScraperConfig).filter_by(source_name="greenhouse").first()
    session.close()
    assert row is not None
    assert row.config["token"] == "stripe"


@patch("src.job_scrapers.ats_detector.detect_ats", return_value=None)
@patch("src.job_scrapers.scraper_generator.generate_scraper")
def test_scraper_generate_unknown_ats_calls_generator(
    mock_gen, mock_detect, runner, tmp_path
):
    """generate calls generate_scraper for unknown ATS URLs."""
    out_file = tmp_path / "unknown_scraper.py"
    mock_gen.return_value = (str(out_file), 2)

    result = runner.invoke(cli, ["scraper", "generate", "https://careers.unknown.com"])
    assert result.exit_code == 0
    mock_gen.assert_called_once()
    assert "Draft scraper written" in result.output or str(out_file) in result.output


@patch("src.job_scrapers.ats_detector.detect_ats", return_value=None)
@patch(
    "src.job_scrapers.scraper_generator.generate_scraper",
    side_effect=RuntimeError("API error"),
)
def test_scraper_generate_handles_error(mock_gen, mock_detect, runner):
    """generate prints the error message and exits non-zero when generation fails."""
    result = runner.invoke(cli, ["scraper", "generate", "https://careers.unknown.com"])
    assert result.exit_code == 1
    assert "Generation failed" in result.output
    assert "API error" in result.output
