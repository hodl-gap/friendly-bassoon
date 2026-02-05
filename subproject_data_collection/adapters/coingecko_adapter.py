"""
CoinGecko Data Adapter

Fetches cryptocurrency data from the CoinGecko API.
Free tier: 10-50 calls/minute (no API key required for basic access).
"""

import requests
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import MAX_RETRIES, RETRY_DELAY_SECONDS

from .base_adapter import BaseDataAdapter


class CoinGeckoAdapter(BaseDataAdapter):
    """Adapter for CoinGecko cryptocurrency data API."""

    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self):
        """Initialize CoinGecko adapter."""
        self._last_request_time = 0
        self._min_request_interval = 1.5  # seconds between requests (free tier limit)

    @property
    def source_name(self) -> str:
        return "CoinGecko"

    def fetch(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Fetch historical cryptocurrency data from CoinGecko.

        Args:
            series_id: CoinGecko coin ID (e.g., 'bitcoin', 'ethereum')
            start_date: Start date
            end_date: End date

        Returns:
            Dict with data, metadata, source info
        """
        print(f"[CoinGecko] Fetching {series_id} from {start_date.date()} to {end_date.date()}")

        # Check cache first
        cached = self._get_from_cache(series_id, start_date, end_date)
        if cached:
            return cached

        # CoinGecko uses UNIX timestamps
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())

        # Fetch from API
        url = f"{self.BASE_URL}/coins/{series_id}/market_chart/range"
        params = {
            "vs_currency": "usd",
            "from": start_ts,
            "to": end_ts
        }

        data = self._make_request(url, params)

        if not data or "prices" not in data:
            raise ValueError(f"No data returned for coin {series_id}")

        # Parse prices (format: [[timestamp_ms, price], ...])
        raw_data = []
        for price_point in data["prices"]:
            timestamp_ms = price_point[0]
            price = price_point[1]
            # Convert milliseconds to date string
            date_str = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d")
            raw_data.append((date_str, price))

        # Deduplicate by date (keep last value per day)
        date_to_price = {}
        for date_str, price in raw_data:
            date_to_price[date_str] = price
        deduped_data = [(d, p) for d, p in sorted(date_to_price.items())]

        # Get metadata
        metadata = self._get_coin_metadata(series_id)

        result = {
            "data": self.normalize_data(deduped_data),
            "metadata": metadata,
            "source": self.source_name,
            "series_id": series_id,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "data_points": len(deduped_data),
            "currency": "USD"
        }

        # Cache result
        self._save_to_cache(series_id, start_date, end_date, result)

        print(f"[CoinGecko] Fetched {len(deduped_data)} data points for {series_id}")
        return result

    def validate_series(self, series_id: str) -> bool:
        """
        Check if CoinGecko coin ID exists.

        Args:
            series_id: CoinGecko coin ID

        Returns:
            bool: True if coin exists
        """
        url = f"{self.BASE_URL}/coins/{series_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false"
        }

        try:
            data = self._make_request(url, params)
            return data is not None and "id" in data
        except Exception as e:
            print(f"[CoinGecko] Validation error for {series_id}: {e}")
            return False

    def _get_coin_metadata(self, series_id: str) -> Dict[str, Any]:
        """
        Get metadata for a cryptocurrency.

        Args:
            series_id: CoinGecko coin ID

        Returns:
            Dict with name, symbol, market cap rank, etc.
        """
        url = f"{self.BASE_URL}/coins/{series_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false"
        }

        try:
            data = self._make_request(url, params)
            if data:
                market_data = data.get("market_data", {})
                return {
                    "name": data.get("name", ""),
                    "symbol": data.get("symbol", "").upper(),
                    "market_cap_rank": data.get("market_cap_rank"),
                    "current_price_usd": market_data.get("current_price", {}).get("usd"),
                    "market_cap_usd": market_data.get("market_cap", {}).get("usd"),
                    "total_volume_usd": market_data.get("total_volume", {}).get("usd")
                }
        except Exception as e:
            print(f"[CoinGecko] Metadata error for {series_id}: {e}")

        return {}

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            sleep_time = self._min_request_interval - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _make_request(
        self,
        url: str,
        params: Dict[str, Any],
        retries: int = None
    ) -> Optional[Dict]:
        """
        Make HTTP request with rate limiting and retry logic.

        Args:
            url: Request URL
            params: Query parameters
            retries: Number of retries

        Returns:
            JSON response or None
        """
        retries = retries or MAX_RETRIES

        for attempt in range(retries):
            self._rate_limit()

            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Rate limited
                    wait_time = RETRY_DELAY_SECONDS * (2 ** attempt) * 2
                    print(f"[CoinGecko] Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"[CoinGecko] HTTP error: {e}")
                    if attempt == retries - 1:
                        raise

            except requests.exceptions.RequestException as e:
                print(f"[CoinGecko] Request error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    raise

        return None

    def get_coin_list(self) -> List[Dict[str, str]]:
        """
        Get list of all supported coins.

        Returns:
            List of dicts with id, symbol, name
        """
        url = f"{self.BASE_URL}/coins/list"
        try:
            data = self._make_request(url, {})
            return data or []
        except Exception as e:
            print(f"[CoinGecko] Error getting coin list: {e}")
            return []


# Common CoinGecko coin ID mappings
COMMON_COINGECKO_COINS = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "xrp": "ripple",
    "sol": "solana",
    "ada": "cardano",
    "doge": "dogecoin",
    "dot": "polkadot",
    "matic": "matic-network",
    "link": "chainlink",
    "uni": "uniswap",
    "avax": "avalanche-2",
    "atom": "cosmos",
    "ltc": "litecoin",
}
