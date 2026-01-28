"""
NAIC Insurance Industry Snapshots Scraper

Scrapes annual insurance industry asset allocation data from NAIC.
Source: https://content.naic.org/cipr-topics/insurance-industry-snapshots

Data includes:
- Asset allocation by type (bonds, stocks, mortgages, real estate)
- Breakdown by insurance type (life, P&C, health)
- Year-over-year changes
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from io import BytesIO
import re

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


class NAICScraper(BaseScraper):
    """Scraper for NAIC insurance industry asset allocation data."""

    BASE_URL = "https://content.naic.org/cipr-topics/insurance-industry-snapshots"

    @property
    def source_name(self) -> str:
        return "naic"

    @property
    def update_frequency(self) -> str:
        return "annual"

    def _find_download_links(self) -> List[Dict[str, str]]:
        """
        Find Excel/PDF download links on the NAIC page.

        Returns:
            List of dicts with 'url', 'title', 'type'
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.BASE_URL, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            links = []

            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.get_text(strip=True)

                # Look for data file links
                if any(ext in href.lower() for ext in ['.xlsx', '.xls', '.csv', '.pdf']):
                    full_url = href
                    if not href.startswith('http'):
                        full_url = 'https://content.naic.org' + href

                    file_type = 'excel' if any(ext in href.lower() for ext in ['.xlsx', '.xls', '.csv']) else 'pdf'

                    links.append({
                        'url': full_url,
                        'title': title,
                        'type': file_type
                    })

            return links

        except Exception as e:
            print(f"[{self.source_name}] Error finding links: {e}")
            return []

    def _download_excel(self, url: str) -> Optional[pd.DataFrame]:
        """Download and parse Excel file."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()

            if '.csv' in url.lower():
                df = pd.read_csv(BytesIO(response.content))
            else:
                df = pd.read_excel(BytesIO(response.content))

            return df

        except Exception as e:
            print(f"[{self.source_name}] Error downloading Excel: {e}")
            return None

    def _extract_allocation_from_df(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Extract asset allocation data from DataFrame.

        Returns:
            Dict with allocation percentages
        """
        data = {}

        # Convert column names to lowercase for easier matching
        df.columns = [str(c).lower().strip() for c in df.columns]

        # Look for asset type columns and value columns
        asset_keywords = {
            'bonds': ['bond', 'fixed income', 'debt'],
            'stocks': ['stock', 'equity', 'common stock', 'preferred stock'],
            'mortgages': ['mortgage', 'real estate loan'],
            'real_estate': ['real estate', 'property'],
            'cash': ['cash', 'short-term'],
            'other': ['other', 'miscellaneous']
        }

        # Try to find relevant data
        for col in df.columns:
            for asset_type, keywords in asset_keywords.items():
                if any(kw in col for kw in keywords):
                    # Get values from this column
                    values = df[col].dropna()
                    if len(values) > 0:
                        # Take the most recent value (usually last row with data)
                        try:
                            value = float(values.iloc[-1])
                            data[f"{asset_type}_pct"] = value
                        except (ValueError, TypeError):
                            pass

        return data

    def _scrape_page_tables(self) -> Dict[str, Any]:
        """
        Scrape allocation data from HTML tables on the page.

        Returns:
            Dict with allocation data
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.BASE_URL, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            data = {}

            # Find all tables
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        value_text = cells[-1].get_text(strip=True)

                        # Try to parse as number
                        value = self._parse_number(value_text)
                        if value is not None:
                            # Map to standardized keys
                            if 'bond' in label:
                                data['bonds_pct'] = value
                            elif 'stock' in label or 'equit' in label:
                                data['stocks_pct'] = value
                            elif 'mortgage' in label:
                                data['mortgages_pct'] = value
                            elif 'real estate' in label:
                                data['real_estate_pct'] = value
                            elif 'cash' in label:
                                data['cash_pct'] = value
                            elif 'total' in label and 'asset' in label:
                                data['total_assets_billion'] = value

            return data

        except Exception as e:
            print(f"[{self.source_name}] Error scraping tables: {e}")
            return {}

    def _parse_number(self, text: str) -> Optional[float]:
        """Parse number from text."""
        if not text:
            return None

        text = text.replace('$', '').replace(',', '').replace('%', '').strip()

        # Handle parentheses for negatives
        if text.startswith('(') and text.endswith(')'):
            text = '-' + text[1:-1]

        try:
            return float(text)
        except ValueError:
            return None

    def _get_report_year(self) -> str:
        """Get the year of the report (usually previous year)."""
        # NAIC reports typically cover the previous year
        return str(datetime.now().year - 1)

    def check_for_update(self) -> bool:
        """Check if new annual data is available."""
        try:
            from ..storage import ScraperStorage
        except ImportError:
            from storage import ScraperStorage
        storage_dir = Path(__file__).parent.parent.parent.parent / "data" / "scraped"
        storage = ScraperStorage(storage_dir)

        last_scrape = storage.get_last_scrape_time(self.source_name)
        if not last_scrape:
            return True

        # Check quarterly for annual updates (per plan)
        days_since = (datetime.now() - last_scrape).days
        return days_since >= 90

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest NAIC asset allocation data."""
        print(f"[{self.source_name}] Fetching latest NAIC data...")

        data = {}

        # Try to find and download Excel files
        links = self._find_download_links()
        print(f"[{self.source_name}] Found {len(links)} download links")

        excel_links = [l for l in links if l['type'] == 'excel']

        for link in excel_links[:3]:  # Try first 3 Excel files
            print(f"[{self.source_name}] Downloading: {link['url']}")
            df = self._download_excel(link['url'])

            if df is not None and len(df) > 0:
                extracted = self._extract_allocation_from_df(df)
                if extracted:
                    data.update(extracted)
                    data['source_file'] = link['url']
                    break

        # Fall back to HTML scraping if no Excel data
        if not data:
            print(f"[{self.source_name}] Falling back to HTML scraping")
            data = self._scrape_page_tables()

        # Add download links info
        data['available_downloads'] = [l['url'] for l in links[:5]]

        report_year = self._get_report_year()

        return self.format_result(
            data=data,
            source_date=f"{report_year}-12-31",
            source_url=self.BASE_URL
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = NAICScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")

    result = scraper.fetch_latest()
    print(f"Result: {result}")
