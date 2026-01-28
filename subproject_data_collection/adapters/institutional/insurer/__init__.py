"""
Insurer Allocation Adapters

Adapters for:
- NAIC Insurance Industry Snapshots (annual)
- ACLI Life Insurers Fact Book (annual)
- BlackRock Global Insurance Report (annual)
"""

from .naic_scraper import NAICScraper
from .acli_scraper import ACLIScraper
from .blackrock_insurance_scraper import BlackRockInsuranceScraper

__all__ = [
    "NAICScraper",
    "ACLIScraper",
    "BlackRockInsuranceScraper"
]
