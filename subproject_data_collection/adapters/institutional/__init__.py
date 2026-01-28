"""
Institutional Allocation Data Adapters

Adapters for collecting institutional allocation data from:
- Fund Manager Positioning (ICI, AAII, BofA FMS)
- Insurer Allocation (NAIC, ACLI, BlackRock)
- Japan-Specific (BOJ IIP, BOJ Time-Series, News)
"""

from .base_scraper import BaseScraper
from .storage import ScraperStorage
from .scheduler import ScraperScheduler

__all__ = ["BaseScraper", "ScraperStorage", "ScraperScheduler"]
