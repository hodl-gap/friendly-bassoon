"""
BOJ International Investment Position Scraper

Scrapes quarterly International Investment Position data from Bank of Japan.
Source: https://www.boj.or.jp/en/statistics/br/bop_06/index.htm

Data includes:
- Japanese foreign holdings by country
- Portfolio investment assets
- Direct investment assets
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from io import BytesIO

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


class BOJIIPScraper(BaseScraper):
    """Scraper for BOJ International Investment Position data."""

    BASE_URL = "https://www.boj.or.jp/en/statistics/br/bop_06/index.htm"

    @property
    def source_name(self) -> str:
        return "boj_iip"

    @property
    def update_frequency(self) -> str:
        return "quarterly"

    def _find_data_files(self) -> List[Dict[str, str]]:
        """
        Find Excel/CSV data file links on the BOJ page.

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

                if any(ext in href.lower() for ext in ['.xlsx', '.xls', '.csv']):
                    full_url = href
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            full_url = 'https://www.boj.or.jp' + href
                        else:
                            full_url = 'https://www.boj.or.jp/en/statistics/br/bop_06/' + href

                    links.append({
                        'url': full_url,
                        'title': title,
                        'type': 'excel'
                    })

            return links

        except Exception as e:
            print(f"[{self.source_name}] Error finding files: {e}")
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
                # Try different sheets
                try:
                    df = pd.read_excel(BytesIO(response.content), sheet_name=0)
                except Exception:
                    df = pd.read_excel(BytesIO(response.content))

            return df

        except Exception as e:
            print(f"[{self.source_name}] Error downloading Excel: {e}")
            return None

    def _extract_iip_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Extract IIP data from DataFrame.

        Returns:
            Dict with country-level foreign holdings
        """
        data = {
            "portfolio_assets_by_country": {},
            "direct_investment_by_country": {},
            "total_foreign_assets_yen_trillion": None,
            "raw_columns": list(df.columns)[:20],
            "row_count": len(df)
        }

        # BOJ data format can vary, try to extract country data
        # Common structure: rows are countries, columns are time periods

        # Convert column names to string
        df.columns = [str(c) for c in df.columns]

        # Look for country names in first column
        if len(df.columns) > 0:
            first_col = df.columns[0]
            countries = df[first_col].dropna().astype(str).tolist()

            # Common country names to look for
            target_countries = ['United States', 'US', 'USA', 'China', 'United Kingdom', 'UK',
                              'Germany', 'France', 'Australia', 'Korea', 'Taiwan', 'Hong Kong']

            for idx, country in enumerate(countries):
                for target in target_countries:
                    if target.lower() in country.lower():
                        # Get the most recent value (last numeric column)
                        for col in reversed(df.columns[1:]):
                            try:
                                value = float(df.iloc[idx][col])
                                data["portfolio_assets_by_country"][country.strip()] = value
                                break
                            except (ValueError, TypeError):
                                continue
                        break

        # Try to find totals
        for idx, row in df.iterrows():
            row_str = str(row.iloc[0]).lower() if len(row) > 0 else ""
            if 'total' in row_str:
                for col in reversed(df.columns[1:]):
                    try:
                        value = float(row[col])
                        data["total_foreign_assets_yen_trillion"] = value
                        break
                    except (ValueError, TypeError):
                        continue
                break

        return data

    def _scrape_page_tables(self) -> Dict[str, Any]:
        """Scrape data from HTML tables if Excel not available."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.BASE_URL, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            data = {"tables": []}

            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                table_data = []
                for row in rows[:20]:  # First 20 rows
                    cells = row.find_all(['td', 'th'])
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    if row_data:
                        table_data.append(row_data)
                if table_data:
                    data["tables"].append(table_data)

            return data

        except Exception as e:
            print(f"[{self.source_name}] Error scraping tables: {e}")
            return {}

    def _get_quarter(self) -> str:
        """Get current quarter string."""
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        return f"{now.year}-Q{quarter}"

    def check_for_update(self) -> bool:
        """Check if new quarterly data is available."""
        try:
            from ..storage import ScraperStorage
        except ImportError:
            from storage import ScraperStorage
        storage_dir = Path(__file__).parent.parent.parent.parent / "data" / "scraped"
        storage = ScraperStorage(storage_dir)

        last_scrape = storage.get_last_scrape_time(self.source_name)
        if not last_scrape:
            return True

        # Check monthly for quarterly updates
        days_since = (datetime.now() - last_scrape).days
        return days_since >= 30

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest BOJ IIP data."""
        print(f"[{self.source_name}] Fetching latest BOJ IIP data...")

        data = {}

        # Find data files
        files = self._find_data_files()
        print(f"[{self.source_name}] Found {len(files)} data files")

        # Try to download and parse Excel files
        for file_info in files[:3]:
            print(f"[{self.source_name}] Downloading: {file_info['url']}")
            df = self._download_excel(file_info['url'])

            if df is not None and len(df) > 0:
                extracted = self._extract_iip_data(df)
                if extracted.get('portfolio_assets_by_country'):
                    data.update(extracted)
                    data['source_file'] = file_info['url']
                    break

        # Fallback to HTML scraping
        if not data:
            print(f"[{self.source_name}] Falling back to HTML scraping")
            data = self._scrape_page_tables()

        data['available_files'] = [f['url'] for f in files[:5]]

        quarter = self._get_quarter()

        return self.format_result(
            data=data,
            source_date=quarter,
            source_url=self.BASE_URL
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = BOJIIPScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")

    result = scraper.fetch_latest()
    print(f"Result keys: {result.keys()}")
    print(f"Data: {result.get('data', {})}")
