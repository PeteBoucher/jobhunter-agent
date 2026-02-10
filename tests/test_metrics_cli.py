from datetime import datetime

from click.testing import CliRunner

from src.database import get_session, init_db
from src.models import ScraperMetric


def test_metrics_cli(tmp_path, monkeypatch):
    db_file = tmp_path / "metrics.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    session = get_session()

    # Insert sample metrics
    now = datetime.utcnow()
    session.add_all(
        [
            ScraperMetric(
                source="github", action="fetch_attempt", value=1, created_at=now
            ),
            ScraperMetric(
                source="github", action="jobs_added", value=2, created_at=now
            ),
            ScraperMetric(
                source="microsoft", action="fetch_attempt", value=1, created_at=now
            ),
        ]
    )
    session.commit()
    session.close()

    from src.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["metrics"])
    assert result.exit_code == 0
    assert "github" in result.output
    assert "microsoft" in result.output
