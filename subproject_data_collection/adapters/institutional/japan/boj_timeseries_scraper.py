"""
BOJ Time-Series Search Scraper

Scrapes time-series data from Bank of Japan's statistical database.
Source: https://www.stat-search.boj.or.jp/index_en.html

Data includes:
- Portfolio investment flows
- International investment statistics
- Various financial time series
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from io import StringIO

import requests
from bs4 import BeautifulSoup
import pandas as pd

try:
    from ..base_scraper import BaseScraper
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from base_scraper import BaseScraper


class BOJTimeseriesScraper(BaseScraper):
    """Scraper for BOJ time-series data."""

    BASE_URL = "https://www.stat-search.boj.or.jp/index_en.html"
    API_BASE = "https://www.stat-search.boj.or.jp/ssi/cgi-bin/famecgi2"

    # Pre-defined series IDs for portfolio investment
    DEFAULT_SERIES = {
        "portfolio_investment_assets": "BP'BPFIA_QPIASSETSA",
        "portfolio_investment_liabilities": "BP'BPFIA_QPILIABA",
        "direct_investment_abroad": "BP'BPFIA_QDIABORADA",
        "direct_investment_japan": "BP'BPFIA_QDINJAPANA",
    }

    @property
    def source_name(self) -> str:
        return "boj_timeseries"

    @property
    def update_frequency(self) -> str:
        return "weekly"

    def _fetch_series(self, series_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific time series from BOJ.

        Args:
            series_id: BOJ series identifier

        Returns:
            Dict with series data or None
        """
        try:
            # BOJ stat-search uses a specific API format
            # This is a simplified approach - actual implementation may need adjustment

            params = {
                'cgi': '$nsdatar498',
                'date': 'A',  # Annual
                'frcyc': 'Q',  # Quarterly
                'series': series_id,
                'format': 'csv'
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(
                self.API_BASE,
                params=params,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                # Try to parse as CSV
                try:
                    df = pd.read_csv(StringIO(response.text))
                    if len(df) > 0:
                        return {
                            "series_id": series_id,
                            "data": df.to_dict(orient='records'),
                            "columns": list(df.columns)
                        }
                except Exception:
                    pass

            return None

        except Exception as e:
            print(f"[{self.source_name}] Error fetching series {series_id}: {e}")
            return None

    def _scrape_available_series(self) -> List[Dict[str, str]]:
        """
        Scrape list of available series from BOJ website.

        Returns:
            List of series info dicts
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.BASE_URL, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            series_list = []

            # Look for links to data categories
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)

                # Look for relevant categories
                if any(kw in text.lower() for kw in ['balance of payments', 'international', 'investment', 'portfolio']):
                    series_list.append({
                        'name': text,
                        'url': href
                    })

            return series_list

        except Exception as e:
            print(f"[{self.source_name}] Error scraping series list: {e}")
            return []

    def _fetch_via_web_interface(self) -> Dict[str, Any]:
        """
        Alternative: scrape data from web interface tables.

        Returns:
            Dict with scraped data
        """
        try:
            # Try to access balance of payments section
            bop_url = "https://www.stat-search.boj.or.jp/ssi/mtshtml/bp_1_en.html"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(bop_url, headers=headers, timeout=30)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                data = {"tables": [], "links": []}

                # Extract tables
                tables = soup.find_all('table')
                for table in tables[:5]:
                    rows = table.find_all('tr')
                    table_data = []
                    for row in rows[:20]:
                        cells = row.find_all(['td', 'th'])
                        row_data = [cell.get_text(strip=True) for cell in cells]
                        if row_data:
                            table_data.append(row_data)
                    if table_data:
                        data["tables"].append(table_data)

                # Extract download links
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if any(ext in href.lower() for ext in ['.csv', '.xlsx', '.xls']):
                        data["links"].append({
                            'url': href,
                            'text': a.get_text(strip=True)
                        })

                return data

            return {}

        except Exception as e:
            print(f"[{self.source_name}] Error fetching web interface: {e}")
            return {}

    def check_for_update(self) -> bool:
        """Check if new data is available."""
        try:
            from ..storage import ScraperStorage
        except ImportError:
            from storage import ScraperStorage
        storage_dir = Path(__file__).parent.parent.parent.parent / "data" / "scraped"
        storage = ScraperStorage(storage_dir)

        last_scrape = storage.get_last_scrape_time(self.source_name)
        if not last_scrape:
            return True

        # Check weekly
        days_since = (datetime.now() - last_scrape).days
        return days_since >= 7

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest BOJ time-series data."""
        print(f"[{self.source_name}] Fetching latest BOJ time-series data...")

        data = {
            "series_data": {},
            "available_series": [],
            "web_interface_data": {}
        }

        # Try fetching predefined series
        for name, series_id in self.DEFAULT_SERIES.items():
            print(f"[{self.source_name}] Fetching series: {name}")
            series_data = self._fetch_series(series_id)
            if series_data:
                data["series_data"][name] = series_data

        # Get list of available series
        available = self._scrape_available_series()
        data["available_series"] = available

        # Also get web interface data
        web_data = self._fetch_via_web_interface()
        data["web_interface_data"] = web_data

        return self.format_result(
            data=data,
            source_date=datetime.now().strftime('%Y-%m-%d'),
            source_url=self.BASE_URL
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = BOJTimeseriesScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")

    result = scraper.fetch_latest()
    print(f"Result keys: {result.keys()}")
    print(f"Data keys: {result.get('data', {}).keys()}")
