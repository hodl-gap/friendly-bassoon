"""
Japan-Specific Adapters

Adapters for:
- BOJ International Investment Position (quarterly)
- BOJ Time-Series Search (monthly)
- Japan Insurer News (daily)
"""

from .boj_iip_scraper import BOJIIPScraper
from .boj_timeseries_scraper import BOJTimeseriesScraper
from .japan_insurer_news_scraper import JapanInsurerNewsScraper

__all__ = [
    "BOJIIPScraper",
    "BOJTimeseriesScraper",
    "JapanInsurerNewsScraper"
]
