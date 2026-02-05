"""
Yahoo Finance Data Adapter

Fetches data from Yahoo Finance using the yfinance library.
No API key required.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))

from .base_adapter import BaseDataAdapter

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("[Yahoo] Warning: yfinance not installed. Run: pip install yfinance")


class YahooAdapter(BaseDataAdapter):
    """Adapter for Yahoo Finance data."""

    def __init__(self):
        """Initialize Yahoo adapter."""
        if not YFINANCE_AVAILABLE:
            print("[Yahoo] yfinance library not available")

    @property
    def source_name(self) -> str:
        return "Yahoo"

    def fetch(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Fetch historical data from Yahoo Finance.

        Args:
            series_id: Yahoo ticker symbol (e.g., 'GLD', 'SPY', 'BTC-USD')
            start_date: Start date
            end_date: End date

        Returns:
            Dict with data, metadata, source info
        """
        print(f"[Yahoo] Fetching {series_id} from {start_date.date()} to {end_date.date()}")

        if not YFINANCE_AVAILABLE:
            raise ImportError("yfinance library not installed")

        # Check cache first
        cached = self._get_from_cache(series_id, start_date, end_date)
        if cached:
            return cached

        # Fetch from Yahoo Finance
        ticker = yf.Ticker(series_id)

        try:
            # Get historical data
            df = ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                auto_adjust=True  # Adjust for splits/dividends
            )

            if df.empty:
                raise ValueError(f"No data returned for ticker {series_id}")

            # Extract close prices
            raw_data = []
            for date, row in df.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                close_price = row["Close"]
                raw_data.append((date_str, close_price))

            # Get metadata
            metadata = self._get_ticker_metadata(ticker)

            result = {
                "data": self.normalize_data(raw_data),
                "metadata": metadata,
                "source": self.source_name,
                "series_id": series_id,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "data_points": len(raw_data),
                "price_type": "adjusted_close"
            }

            # Cache result
            self._save_to_cache(series_id, start_date, end_date, result)

            print(f"[Yahoo] Fetched {len(raw_data)} data points for {series_id}")
            return result

        except Exception as e:
            print(f"[Yahoo] Error fetching {series_id}: {e}")
            raise

    def validate_series(self, series_id: str) -> bool:
        """
        Check if Yahoo ticker exists.

        Args:
            series_id: Yahoo ticker symbol

        Returns:
            bool: True if ticker exists
        """
        if not YFINANCE_AVAILABLE:
            return False

        try:
            ticker = yf.Ticker(series_id)
            info = ticker.info
            # Check if we got valid info (not just empty dict)
            return bool(info and info.get("regularMarketPrice"))
        except Exception as e:
            print(f"[Yahoo] Validation error for {series_id}: {e}")
            return False

    def _get_ticker_metadata(self, ticker) -> Dict[str, Any]:
        """
        Get metadata for a Yahoo ticker.

        Args:
            ticker: yfinance Ticker object

        Returns:
            Dict with name, currency, exchange, etc.
        """
        try:
            info = ticker.info
            return {
                "name": info.get("longName", info.get("shortName", "")),
                "currency": info.get("currency", "USD"),
                "exchange": info.get("exchange", ""),
                "quote_type": info.get("quoteType", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", "")
            }
        except Exception as e:
            print(f"[Yahoo] Metadata error: {e}")
            return {}


# Common Yahoo ticker mappings
COMMON_YAHOO_TICKERS = {
    # ETFs
    "spy": "SPY",  # S&P 500 ETF
    "qqq": "QQQ",  # Nasdaq 100 ETF
    "gld": "GLD",  # Gold ETF
    "tlt": "TLT",  # 20+ Year Treasury Bond ETF
    "hyg": "HYG",  # High Yield Corporate Bond ETF

    # Indices
    "sp500": "^GSPC",  # S&P 500 Index
    "nasdaq": "^IXIC",  # Nasdaq Composite
    "vix": "^VIX",  # VIX Volatility Index
    "dxy": "DX-Y.NYB",  # US Dollar Index

    # Currencies
    "usdjpy": "USDJPY=X",
    "eurusd": "EURUSD=X",
    "usdkrw": "USDKRW=X",

    # Crypto
    "btc": "BTC-USD",
    "eth": "ETH-USD",

    # Commodities
    "gold": "GC=F",  # Gold Futures
    "oil": "CL=F",  # Crude Oil Futures
}
