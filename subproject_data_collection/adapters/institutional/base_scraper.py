"""
Base Scraper

Abstract base class for all institutional allocation scrapers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json


class BaseScraper(ABC):
    """Abstract base class for institutional allocation scrapers."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Return the source name (e.g., 'ici_flows', 'aaii_sentiment').

        Used for storage directory naming and logging.
        """
        pass

    @property
    @abstractmethod
    def update_frequency(self) -> str:
        """
        Return the expected update frequency.

        Valid values: "daily", "weekly", "monthly", "quarterly", "annual"
        """
        pass

    @abstractmethod
    def fetch_latest(self) -> Dict[str, Any]:
        """
        Fetch the latest data from the source.

        Returns:
            Dict containing:
            - source: Source name
            - scraped_at: ISO timestamp of scrape
            - source_date: Date of the source data (if available)
            - source_url: URL where data was fetched from
            - data: The actual data (structure varies by source)
            - metadata: Additional metadata

        Raises:
            ConnectionError: If source is unreachable
            ValueError: If data cannot be parsed
        """
        pass

    @abstractmethod
    def check_for_update(self) -> bool:
        """
        Check if source has new data since last scrape.

        Returns:
            bool: True if new data is available, False otherwise
        """
        pass

    def get_last_scrape_info(self, storage_dir: Path) -> Optional[Dict[str, Any]]:
        """
        Get information about the last successful scrape.

        Args:
            storage_dir: Base directory for scraped data

        Returns:
            Dict with last scrape info or None if no previous scrapes
        """
        source_dir = storage_dir / self.source_name
        latest_link = source_dir / "latest.json"

        if not latest_link.exists():
            return None

        try:
            # Read the latest.json file directly
            with open(latest_link, 'r') as f:
                data = json.load(f)
            return {
                "scraped_at": data.get("scraped_at"),
                "source_date": data.get("source_date"),
                "source_url": data.get("source_url")
            }
        except Exception:
            return None

    def format_result(
        self,
        data: Dict[str, Any],
        source_date: Optional[str] = None,
        source_url: Optional[str] = None,
        update_detected: bool = True,
        previous_scrape: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format scrape result in standard format.

        Args:
            data: The scraped data
            source_date: Date of the source data (YYYY-MM-DD)
            source_url: URL where data was fetched
            update_detected: Whether this is new data
            previous_scrape: ISO timestamp of previous scrape

        Returns:
            Standardized result dict
        """
        return {
            "source": self.source_name,
            "scraped_at": datetime.now().isoformat() + "Z",
            "source_date": source_date,
            "source_url": source_url,
            "data": data,
            "metadata": {
                "update_detected": update_detected,
                "previous_scrape": previous_scrape,
                "update_frequency": self.update_frequency
            }
        }
