"""
Fund Manager Positioning Adapters

Adapters for:
- ICI Fund Flows (weekly)
- AAII Sentiment (weekly)
- AAII Asset Allocation (monthly)
- BofA Global Fund Manager Survey (monthly, via web search)
"""

from .ici_scraper import ICIScraper
from .aaii_sentiment_scraper import AAIISentimentScraper
from .aaii_allocation_scraper import AAIIAllocationScraper
from .bofa_fms_scraper import BofAFMSScraper

__all__ = [
    "ICIScraper",
    "AAIISentimentScraper",
    "AAIIAllocationScraper",
    "BofAFMSScraper"
]
