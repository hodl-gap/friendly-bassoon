"""
Scraper Storage

Handles saving and retrieving scraped data as JSON files.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


class ScraperStorage:
    """
    Storage handler for scraped institutional allocation data.

    Directory structure:
        data/scraped/
        ├── fund_manager/
        │   ├── ici_flows/
        │   │   ├── 2026-01-24.json
        │   │   ├── 2026-01-17.json
        │   │   └── latest.json  (copy of most recent)
        │   └── ...
        ├── insurer/
        │   └── ...
        └── japan/
            └── ...
    """

    def __init__(self, base_dir: Path):
        """
        Initialize storage.

        Args:
            base_dir: Base directory for scraped data (e.g., data/scraped/)
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_source_dir(self, source_name: str, category: str) -> Path:
        """Get directory for a specific source."""
        source_dir = self.base_dir / category / source_name
        source_dir.mkdir(parents=True, exist_ok=True)
        return source_dir

    def _determine_category(self, source_name: str) -> str:
        """Determine category from source name."""
        fund_manager_sources = ["ici_flows", "aaii_sentiment", "aaii_allocation", "bofa_fms"]
        insurer_sources = ["naic", "acli", "blackrock_insurance"]
        japan_sources = ["boj_iip", "boj_timeseries", "japan_insurer_news"]

        if source_name in fund_manager_sources:
            return "fund_manager"
        elif source_name in insurer_sources:
            return "insurer"
        elif source_name in japan_sources:
            return "japan"
        else:
            return "other"

    def save(
        self,
        source_name: str,
        data: Dict[str, Any],
        source_date: Optional[str] = None,
        category: Optional[str] = None
    ) -> Path:
        """
        Save scraped data to JSON file.

        Args:
            source_name: Name of the source (e.g., 'ici_flows')
            data: Data to save (should be the full result from scraper)
            source_date: Date of the source data (YYYY-MM-DD). If None, uses today.
            category: Category folder (fund_manager, insurer, japan). Auto-detected if None.

        Returns:
            Path to saved file
        """
        if category is None:
            category = self._determine_category(source_name)

        source_dir = self._get_source_dir(source_name, category)

        # Use source_date or today
        if source_date is None:
            source_date = datetime.now().strftime("%Y-%m-%d")

        # Save dated file
        dated_file = source_dir / f"{source_date}.json"
        with open(dated_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        # Update latest.json (copy, not symlink for cross-platform compatibility)
        latest_file = source_dir / "latest.json"
        with open(latest_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        print(f"[Storage] Saved {source_name} data to {dated_file}")
        return dated_file

    def load_latest(
        self,
        source_name: str,
        category: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Load the most recent data for a source.

        Args:
            source_name: Name of the source
            category: Category folder. Auto-detected if None.

        Returns:
            Latest data or None if no data exists
        """
        if category is None:
            category = self._determine_category(source_name)

        source_dir = self._get_source_dir(source_name, category)
        latest_file = source_dir / "latest.json"

        if not latest_file.exists():
            return None

        try:
            with open(latest_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Storage] Error loading {latest_file}: {e}")
            return None

    def load_by_date(
        self,
        source_name: str,
        date: str,
        category: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Load data for a specific date.

        Args:
            source_name: Name of the source
            date: Date string (YYYY-MM-DD)
            category: Category folder. Auto-detected if None.

        Returns:
            Data for that date or None if not found
        """
        if category is None:
            category = self._determine_category(source_name)

        source_dir = self._get_source_dir(source_name, category)
        dated_file = source_dir / f"{date}.json"

        if not dated_file.exists():
            return None

        try:
            with open(dated_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Storage] Error loading {dated_file}: {e}")
            return None

    def list_available_dates(
        self,
        source_name: str,
        category: Optional[str] = None
    ) -> List[str]:
        """
        List all available dates for a source.

        Args:
            source_name: Name of the source
            category: Category folder. Auto-detected if None.

        Returns:
            List of date strings (YYYY-MM-DD), sorted newest first
        """
        if category is None:
            category = self._determine_category(source_name)

        source_dir = self._get_source_dir(source_name, category)

        if not source_dir.exists():
            return []

        dates = []
        for f in source_dir.glob("*.json"):
            if f.name != "latest.json":
                # Extract date from filename
                date_str = f.stem
                dates.append(date_str)

        return sorted(dates, reverse=True)

    def get_last_scrape_time(
        self,
        source_name: str,
        category: Optional[str] = None
    ) -> Optional[datetime]:
        """
        Get the timestamp of the last scrape for a source.

        Args:
            source_name: Name of the source
            category: Category folder. Auto-detected if None.

        Returns:
            Datetime of last scrape or None
        """
        latest = self.load_latest(source_name, category)
        if latest and "scraped_at" in latest:
            try:
                # Handle both Z suffix and +00:00
                scraped_at = latest["scraped_at"]
                if scraped_at.endswith("Z"):
                    scraped_at = scraped_at[:-1]
                return datetime.fromisoformat(scraped_at)
            except Exception:
                return None
        return None
