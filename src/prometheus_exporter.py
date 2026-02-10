"""Prometheus exporter for scraper metrics."""

import logging

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.exposition import REGISTRY

from src.database import get_session
from src.models import ScraperMetric

logger = logging.getLogger("jobhunter.prometheus")


class ScraperMetricsCollector:
    """Custom Prometheus collector for scraper metrics from database."""

    def __init__(self):
        """Initialize the collector."""
        self.registry = CollectorRegistry()

    def collect(self):
        """Yield metrics from database.

        This is called by Prometheus on each scrape.
        """
        session = get_session()
        try:
            # Query metrics from database
            rows = session.query(
                ScraperMetric.source,
                ScraperMetric.action,
            ).distinct()

            # Create gauge for each unique (source, action) pair
            metrics_data = {}
            for source, action in rows:
                count = (
                    session.query(ScraperMetric)
                    .filter(
                        ScraperMetric.source == source,
                        ScraperMetric.action == action,
                    )
                    .count()
                )
                key = f"{source}_{action}"
                metrics_data[key] = count

            # Yield gauge metric
            metric = GaugeMetricFamily(
                "jobhunter_scraper_events_total",
                "Total scraper events by source and action",
                labels=["source", "action"],
            )

            for source, action in rows:
                count = (
                    session.query(ScraperMetric)
                    .filter(
                        ScraperMetric.source == source,
                        ScraperMetric.action == action,
                    )
                    .count()
                )
                metric.add_metric([source, action], count)

            yield metric

        except Exception as e:
            logger.exception(f"Error collecting metrics: {e}")
        finally:
            session.close()


def create_exporter():
    """Create and register the Prometheus exporter.

    Returns:
        The custom collector instance
    """
    collector = ScraperMetricsCollector()
    REGISTRY.register(collector)
    return collector


def get_metrics_bytes():
    """Get metrics in Prometheus text format.

    Returns:
        Bytes of metrics in Prometheus exposition format
    """
    return generate_latest(REGISTRY)


__all__ = ["create_exporter", "get_metrics_bytes", "ScraperMetricsCollector"]
