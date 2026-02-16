"""Job scrapers for multiple platforms"""

from .base_scraper import BaseScraper
from .registry import DEFAULT_SOURCES, SCRAPER_MAP

__all__ = ["BaseScraper", "SCRAPER_MAP", "DEFAULT_SOURCES"]
