"""
FRED Data Adapter

Fetches data from the Federal Reserve Economic Data (FRED) API.
Requires FRED_API_KEY in .env file.
"""

import requests
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from ._config import FRED_API_KEY, MAX_RETRIES, RETRY_DELAY_SECONDS

from .base_adapter import BaseDataAdapter
import time


class FREDAdapter(BaseDataAdapter):
    """Adapter for FRED (Federal Reserve Economic Data) API."""

    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: str = None):
        """
        Initialize FRED adapter.

        Args:
            api_key: FRED API key (defaults to FRED_API_KEY from config)
        """
        self.api_key = api_key or FRED_API_KEY
        if not self.api_key:
            print("[FRED] Warning: No API key configured. Set FRED_API_KEY in .env")

    @property
    def source_name(self) -> str:
        return "FRED"

    def fetch(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Fetch historical data from FRED.

        Args:
            series_id: FRED series ID (e.g., 'WTREGEN', 'DGS10')
            start_date: Start date
            end_date: End date

        Returns:
            Dict with data, metadata, source info
        """
        print(f"[FRED] Fetching {series_id} from {start_date.date()} to {end_date.date()}")

        # Check cache first
        cached = self._get_from_cache(series_id, start_date, end_date)
        if cached:
            return cached

        if not self.api_key:
            raise ValueError("FRED API key not configured")

        # Fetch from API
        url = f"{self.BASE_URL}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date.strftime("%Y-%m-%d"),
            "observation_end": end_date.strftime("%Y-%m-%d"),
            "sort_order": "asc"
        }

        data = self._make_request(url, params)

        if not data or "observations" not in data:
            raise ValueError(f"No data returned for series {series_id}")

        # Parse observations
        raw_data = []
        for obs in data["observations"]:
            date_str = obs["date"]
            value = obs["value"]
            if value != ".":  # FRED uses "." for missing values
                raw_data.append((date_str, value))

        # Get metadata
        metadata = self._get_series_metadata(series_id)

        result = {
            "data": self.normalize_data(raw_data),
            "metadata": metadata,
            "source": self.source_name,
            "series_id": series_id,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "data_points": len(raw_data)
        }

        # Cache result
        self._save_to_cache(series_id, start_date, end_date, result)

        print(f"[FRED] Fetched {len(raw_data)} data points for {series_id}")
        return result

    def validate_series(self, series_id: str) -> bool:
        """
        Check if FRED series exists.

        Args:
            series_id: FRED series ID

        Returns:
            bool: True if series exists
        """
        if not self.api_key:
            print("[FRED] Cannot validate: no API key")
            return False

        url = f"{self.BASE_URL}/series"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json"
        }

        try:
            data = self._make_request(url, params)
            return data is not None and "seriess" in data
        except Exception as e:
            print(f"[FRED] Validation error for {series_id}: {e}")
            return False

    def _get_series_metadata(self, series_id: str) -> Dict[str, Any]:
        """
        Get metadata for a FRED series.

        Args:
            series_id: FRED series ID

        Returns:
            Dict with title, frequency, units, etc.
        """
        url = f"{self.BASE_URL}/series"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json"
        }

        try:
            data = self._make_request(url, params)
            if data and "seriess" in data and data["seriess"]:
                series_info = data["seriess"][0]
                return {
                    "title": series_info.get("title", ""),
                    "frequency": series_info.get("frequency", ""),
                    "units": series_info.get("units", ""),
                    "seasonal_adjustment": series_info.get("seasonal_adjustment", ""),
                    "last_updated": series_info.get("last_updated", "")
                }
        except Exception as e:
            print(f"[FRED] Metadata error for {series_id}: {e}")

        return {}

    def _make_request(
        self,
        url: str,
        params: Dict[str, Any],
        retries: int = None
    ) -> Optional[Dict]:
        """
        Make HTTP request with retry logic.

        Args:
            url: Request URL
            params: Query parameters
            retries: Number of retries (defaults to MAX_RETRIES)

        Returns:
            JSON response or None
        """
        retries = retries or MAX_RETRIES

        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Rate limited
                    wait_time = RETRY_DELAY_SECONDS * (2 ** attempt)
                    print(f"[FRED] Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"[FRED] HTTP error: {e}")
                    if attempt == retries - 1:
                        raise

            except requests.exceptions.RequestException as e:
                print(f"[FRED] Request error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    raise

        return None


# Common FRED series mapping
COMMON_FRED_SERIES = {
    "tga": "WTREGEN",  # Treasury General Account
    "rrp": "RRPONTSYD",  # Overnight Reverse Repo
    "fed_balance_sheet": "WALCL",  # Total Assets
    "reserves": "TOTRESNS",  # Total Reserves
    "us02y": "DGS2",  # 2-Year Treasury
    "us10y": "DGS10",  # 10-Year Treasury
    "sofr": "SOFR",  # Secured Overnight Financing Rate
    "fed_funds": "FEDFUNDS",  # Federal Funds Rate
    "gold": "GOLDAMGBD228NLBM",  # Gold Price (London PM Fix)
    "vix": "VIXCLS",  # VIX Volatility Index
    "sp500": "SP500",  # S&P 500 Index
}
