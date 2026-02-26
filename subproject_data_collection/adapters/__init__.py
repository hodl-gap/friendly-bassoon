"""
Data Source Adapters

This package contains adapters for fetching data from various sources:
- FRED (Federal Reserve Economic Data) - macro time series
- Yahoo Finance - market prices
- CoinGecko (Cryptocurrency data) - crypto prices
- WebSearch - web search + LLM extraction for qualitative data
- Institutional - institutional allocation scrapers (fund managers, insurers, Japan)
"""

from .base_adapter import BaseDataAdapter
from .fred_adapter import FREDAdapter
from .yahoo_adapter import YahooAdapter
from .coingecko_adapter import CoinGeckoAdapter
from .csv_adapter import CSVAdapter
from .web_search_adapter import WebSearchAdapter, search_data_points, search_announcements

# Institutional allocation scrapers
from .institutional import BaseScraper, ScraperStorage, ScraperScheduler

__all__ = [
    "BaseDataAdapter",
    "FREDAdapter",
    "YahooAdapter",
    "CoinGeckoAdapter",
    "CSVAdapter",
    "WebSearchAdapter",
    "search_data_points",
    "search_announcements",
    # Institutional
    "BaseScraper",
    "ScraperStorage",
    "ScraperScheduler",
]
