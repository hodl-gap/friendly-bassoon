"""
Base Data Adapter

Abstract base class for all data source adapters.
Defines the interface that all adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
import hashlib
import json
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import CACHE_DIR, ENABLE_CACHE, CACHE_EXPIRY_HOURS


class BaseDataAdapter(ABC):
    """Abstract base class for data source adapters."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Return the source name (e.g., 'FRED', 'Yahoo', 'CoinGecko').

        Returns:
            str: The name of the data source
        """
        pass

    @abstractmethod
    def fetch(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Fetch historical data for a series.

        Args:
            series_id: The identifier for the data series (e.g., 'WTREGEN' for FRED)
            start_date: Start date for the data range
            end_date: End date for the data range

        Returns:
            Dict containing:
            - data: List of (date, value) tuples
            - metadata: Dict with series metadata
            - source: Source name
            - series_id: The series identifier
            - start_date: Actual start date of data
            - end_date: Actual end date of data

        Raises:
            ValueError: If series_id is invalid
            ConnectionError: If API is unreachable
        """
        pass

    @abstractmethod
    def validate_series(self, series_id: str) -> bool:
        """
        Check if a series exists and is accessible.

        Args:
            series_id: The identifier for the data series

        Returns:
            bool: True if series exists and is accessible
        """
        pass

    def get_cache_key(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> str:
        """
        Generate a cache key for this request.

        Args:
            series_id: The series identifier
            start_date: Start date
            end_date: End date

        Returns:
            str: A unique cache key
        """
        key_str = f"{self.source_name}:{series_id}:{start_date.date()}:{end_date.date()}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_from_cache(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Try to get data from cache.

        Args:
            series_id: The series identifier
            start_date: Start date
            end_date: End date

        Returns:
            Cached data if found and valid, None otherwise
        """
        if not ENABLE_CACHE:
            return None

        cache_key = self.get_cache_key(series_id, start_date, end_date)
        cache_file = CACHE_DIR / f"{cache_key}.json"

        if not cache_file.exists():
            return None

        try:
            # Check if cache is expired
            file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            age_hours = (datetime.now() - file_mtime).total_seconds() / 3600

            if age_hours > CACHE_EXPIRY_HOURS:
                print(f"[{self.source_name}] Cache expired for {series_id}")
                return None

            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
                print(f"[{self.source_name}] Cache hit for {series_id}")
                return cached_data

        except Exception as e:
            print(f"[{self.source_name}] Cache read error: {e}")
            return None

    def _save_to_cache(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime,
        data: Dict[str, Any]
    ) -> None:
        """
        Save data to cache.

        Args:
            series_id: The series identifier
            start_date: Start date
            end_date: End date
            data: Data to cache
        """
        if not ENABLE_CACHE:
            return

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_key = self.get_cache_key(series_id, start_date, end_date)
            cache_file = CACHE_DIR / f"{cache_key}.json"

            with open(cache_file, 'w') as f:
                json.dump(data, f, default=str)
                print(f"[{self.source_name}] Cached data for {series_id}")

        except Exception as e:
            print(f"[{self.source_name}] Cache write error: {e}")

    def normalize_data(
        self,
        raw_data: List[Tuple[Any, Any]]
    ) -> List[Tuple[str, float]]:
        """
        Normalize data to consistent format: List of (date_str, float_value).

        Args:
            raw_data: Raw data from API

        Returns:
            List of (date_string, float_value) tuples
        """
        normalized = []
        for date_val, value in raw_data:
            # Convert date to string
            if isinstance(date_val, datetime):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                date_str = str(date_val)

            # Convert value to float
            try:
                float_val = float(value) if value is not None else None
            except (ValueError, TypeError):
                float_val = None

            if float_val is not None:
                normalized.append((date_str, float_val))

        return normalized
