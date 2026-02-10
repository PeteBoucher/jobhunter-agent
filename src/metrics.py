"""Helpers to query and summarize scraper metrics."""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models import ScraperMetric


def get_metrics_summary(
    session: Session, since: Optional[datetime] = None, source: Optional[str] = None
) -> List[Tuple[str, str, int, int]]:
    """Return summarized metrics grouped by source and action.

    Returns a list of tuples: (source, action, count_rows, sum_value)
    """
    q = session.query(
        ScraperMetric.source,
        ScraperMetric.action,
        func.count(ScraperMetric.id),
        func.coalesce(func.sum(ScraperMetric.value), 0),
    )

    if since:
        q = q.filter(ScraperMetric.created_at >= since)
    if source:
        q = q.filter(ScraperMetric.source == source)

    q = q.group_by(ScraperMetric.source, ScraperMetric.action)
    rows = q.all()
    return [(r[0], r[1], int(r[2] or 0), int(r[3] or 0)) for r in rows]


__all__ = ["get_metrics_summary"]
