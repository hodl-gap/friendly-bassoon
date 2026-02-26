"""
CSV Data Adapter

Reads normalized date,value CSV files from csv_series/ directory.
Supports any scraped dataset that follows the convention:
  subproject_data_collection/data/csv_series/{series_id}.csv
  with columns: date (YYYY-MM-DD), value (float)
"""

import csv
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

from .base_adapter import BaseDataAdapter

# Default path to csv_series directory
CSV_SERIES_DIR = Path(__file__).parent.parent / "data" / "csv_series"


class CSVAdapter(BaseDataAdapter):
    """Adapter for local CSV time series files."""

    def __init__(self, base_path: Path = None):
        self.base_path = base_path or CSV_SERIES_DIR

    @property
    def source_name(self) -> str:
        return "CSV"

    def _series_path(self, series_id: str) -> Path:
        return self.base_path / f"{series_id}.csv"

    def fetch(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """
        Fetch data from a local CSV file.

        Args:
            series_id: Filename stem (e.g., 'equity_pc_ratio')
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            Standard adapter dict with data, metadata, source info
        """
        path = self._series_path(series_id)
        if not path.exists():
            raise ValueError(f"CSV series file not found: {path}")

        print(f"[CSV] Reading {series_id} from {start_date.date()} to {end_date.date()}")

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        raw_data = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_str = row.get("date", "").strip()
                value_str = row.get("value", "").strip()
                if not date_str or not value_str:
                    continue
                if date_str < start_str or date_str > end_str:
                    continue
                raw_data.append((date_str, value_str))

        result = {
            "data": self.normalize_data(raw_data),
            "metadata": {
                "title": series_id,
                "source_file": str(path),
            },
            "source": self.source_name,
            "series_id": series_id,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "data_points": len(raw_data),
        }

        print(f"[CSV] Fetched {len(raw_data)} data points for {series_id}")
        return result

    def validate_series(self, series_id: str) -> bool:
        """Check if the CSV file exists."""
        return self._series_path(series_id).exists()
