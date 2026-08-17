"""Centralized scraper registry.

All scrapers are registered here so that the CLI and worker can reference
a single source of truth instead of duplicating the mapping.
"""

from typing import Dict, List, Type

from src.job_scrapers.adzuna_scraper import AdzunaScraper
from src.job_scrapers.ashby_scraper import AshbyScraper
from src.job_scrapers.bamboohr_scraper import BambooHRScraper
from src.job_scrapers.base_scraper import BaseScraper
from src.job_scrapers.bcg_scraper import BCGScraper
from src.job_scrapers.coderland_scraper import CodelandScraper
from src.job_scrapers.coinbase_scraper import CoinbaseScraper
from src.job_scrapers.dejobs_scraper import DeJobsScraper
from src.job_scrapers.github_scraper import GitHubJobsScraper
from src.job_scrapers.greenhouse_scraper import GreenhouseScraper
from src.job_scrapers.innovairv_scraper import InnovaIRVScraper
from src.job_scrapers.lever_scraper import LeverScraper
from src.job_scrapers.linkedin_scraper import LinkedInScraper
from src.job_scrapers.microsoft_scraper import MicrosoftScraper
from src.job_scrapers.reed_scraper import ReedScraper
from src.job_scrapers.revolut_scraper import RevolutScraper
from src.job_scrapers.smartrecruiters_scraper import SmartRecruitersScraper
from src.job_scrapers.teamtailor_scraper import TeamtailorScraper
from src.job_scrapers.themuse_scraper import TheMuseScraper
from src.job_scrapers.thoughtworks_scraper import ThoughtworksScraper
from src.job_scrapers.uber_scraper import UberScraper
from src.job_scrapers.workable_scraper import WorkableScraper
from src.job_scrapers.workday_scraper import WorkdayScraper

# All available scrapers keyed by source name
SCRAPER_MAP: Dict[str, Type[BaseScraper]] = {
    "ashby": AshbyScraper,
    "bamboohr": BambooHRScraper,
    "coderland": CodelandScraper,
    "dejobs": DeJobsScraper,
    "bcg": BCGScraper,
    "greenhouse": GreenhouseScraper,
    "lever": LeverScraper,
    "linkedin": LinkedInScraper,
    "microsoft": MicrosoftScraper,
    "github": GitHubJobsScraper,
    "coinbase": CoinbaseScraper,
    "innovairv": InnovaIRVScraper,
    "workable": WorkableScraper,
    "workday": WorkdayScraper,
    "revolut": RevolutScraper,
    "teamtailor": TeamtailorScraper,
    "thoughtworks": ThoughtworksScraper,
    "uber": UberScraper,
    "adzuna": AdzunaScraper,
    "themuse": TheMuseScraper,
    "reed": ReedScraper,
    "smartrecruiters": SmartRecruitersScraper,
}

# Default sources to scrape (the ones that actually return data)
# LinkedIn is excluded: their guest endpoint actively blocks Lambda IPs,
# raises exceptions every run, and scraping violates their ToS.
DEFAULT_SOURCES: List[str] = [
    "ashby",
    "bamboohr",
    "bcg",
    "greenhouse",
    "lever",
    "adzuna",
    "themuse",
    "workday",
    "thoughtworks",
    "smartrecruiters",
    "coderland",
    "dejobs",
    "teamtailor",
    "workable",
    "innovairv",
]
