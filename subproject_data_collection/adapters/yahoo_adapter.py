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

    def fetch_fundamentals(self, series_id: str) -> Dict[str, Any]:
        """
        Fetch fundamental data for a stock/ETF (P/E, market cap, etc.).

        This is critical for belief-space analysis where valuation context matters
        (e.g., "P/E compressed from 85x to 60x").

        Args:
            series_id: Yahoo ticker symbol (e.g., 'IGV', 'GOOGL', 'AMZN')

        Returns:
            Dict with valuation metrics, financials, and price data
        """
        print(f"[Yahoo] Fetching fundamentals for {series_id}")

        if not YFINANCE_AVAILABLE:
            raise ImportError("yfinance library not installed")

        try:
            ticker = yf.Ticker(series_id)
            info = ticker.info

            # Current price data
            current_price = info.get("regularMarketPrice") or info.get("previousClose")
            price_change_pct = info.get("regularMarketChangePercent", 0)

            # 52-week range for drawdown calculation
            fifty_two_week_high = info.get("fiftyTwoWeekHigh")
            fifty_two_week_low = info.get("fiftyTwoWeekLow")
            drawdown_from_high = None
            if fifty_two_week_high and current_price:
                drawdown_from_high = ((current_price - fifty_two_week_high) / fifty_two_week_high) * 100

            result = {
                "ticker": series_id,
                "name": info.get("longName", info.get("shortName", "")),
                "quote_type": info.get("quoteType", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),

                # Price data
                "current_price": current_price,
                "price_change_pct": price_change_pct,
                "fifty_two_week_high": fifty_two_week_high,
                "fifty_two_week_low": fifty_two_week_low,
                "drawdown_from_high_pct": drawdown_from_high,

                # Valuation metrics (critical for belief-space)
                "forward_pe": info.get("forwardPE"),
                "trailing_pe": info.get("trailingPE"),
                "peg_ratio": info.get("pegRatio"),
                "price_to_book": info.get("priceToBook"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "enterprise_value": info.get("enterpriseValue"),
                "ev_to_ebitda": info.get("enterpriseToEbitda"),
                "ev_to_revenue": info.get("enterpriseToRevenue"),

                # Size
                "market_cap": info.get("marketCap"),
                "shares_outstanding": info.get("sharesOutstanding"),

                # Financials (for CAPEX analysis)
                "total_revenue": info.get("totalRevenue"),
                "revenue_growth": info.get("revenueGrowth"),
                "gross_margins": info.get("grossMargins"),
                "operating_margins": info.get("operatingMargins"),
                "profit_margins": info.get("profitMargins"),
                "ebitda": info.get("ebitda"),
                "free_cash_flow": info.get("freeCashflow"),
                "operating_cash_flow": info.get("operatingCashflow"),
                "total_cash": info.get("totalCash"),
                "total_debt": info.get("totalDebt"),

                # Analyst estimates
                "target_mean_price": info.get("targetMeanPrice"),
                "target_high_price": info.get("targetHighPrice"),
                "target_low_price": info.get("targetLowPrice"),
                "recommendation_mean": info.get("recommendationMean"),
                "recommendation_key": info.get("recommendationKey"),
                "number_of_analyst_opinions": info.get("numberOfAnalystOpinions"),

                # ETF specific (for sector ETFs like IGV)
                "category": info.get("category"),
                "fund_family": info.get("fundFamily"),
                "total_assets": info.get("totalAssets"),

                "source": "Yahoo",
                "timestamp": datetime.now().isoformat()
            }

            # Filter out None values
            result = {k: v for k, v in result.items() if v is not None}

            print(f"[Yahoo] Fetched {len(result)} fundamental fields for {series_id}")
            return result

        except Exception as e:
            print(f"[Yahoo] Error fetching fundamentals for {series_id}: {e}")
            return {"error": str(e), "ticker": series_id}

    def fetch_fundamentals_batch(self, tickers: list) -> Dict[str, Dict[str, Any]]:
        """
        Fetch fundamentals for multiple tickers.

        Args:
            tickers: List of Yahoo ticker symbols

        Returns:
            Dict mapping ticker to fundamentals
        """
        results = {}
        for ticker in tickers:
            results[ticker] = self.fetch_fundamentals(ticker)
        return results


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
