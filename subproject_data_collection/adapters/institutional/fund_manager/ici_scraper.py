"""
ICI Fund Flows Scraper

Scrapes weekly mutual fund and ETF flow data from the Investment Company Institute.
Source: https://www.ici.org/research/stats/weekly

Data includes:
- Equity fund net flows
- Bond fund net flows
- Money market fund net flows
- Hybrid fund net flows
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
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


class ICIScraper(BaseScraper):
    """Scraper for ICI weekly fund flows data."""

    BASE_URL = "https://www.ici.org/research/stats/weekly"
    DATA_URL = "https://www.ici.org/research/stats/weekly_flow_data"

    @property
    def source_name(self) -> str:
        return "ici_flows"

    @property
    def update_frequency(self) -> str:
        return "weekly"

    def _get_latest_report_date(self) -> Optional[str]:
        """
        Get the date of the latest report from the ICI page.

        Returns:
            Date string (YYYY-MM-DD) or None
        """
        try:
            response = requests.get(self.BASE_URL, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for date in the page content
            # ICI typically shows "Week of [Month Day, Year]" or similar
            text = soup.get_text()

            # Try to find date patterns
            date_patterns = [
                r'Week (?:of|ending) (\w+ \d{1,2}, \d{4})',
                r'(\w+ \d{1,2}, \d{4})',
                r'(\d{1,2}/\d{1,2}/\d{4})'
            ]

            for pattern in date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    date_str = match.group(1)
                    # Try to parse and standardize
                    for fmt in ['%B %d, %Y', '%b %d, %Y', '%m/%d/%Y']:
                        try:
                            parsed = datetime.strptime(date_str, fmt)
                            return parsed.strftime('%Y-%m-%d')
                        except ValueError:
                            continue

            return None

        except Exception as e:
            print(f"[{self.source_name}] Error getting report date: {e}")
            return None

    def _download_excel_data(self) -> Optional[pd.DataFrame]:
        """
        Attempt to download Excel/CSV data from ICI.

        Returns:
            DataFrame or None
        """
        try:
            response = requests.get(self.BASE_URL, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for Excel/CSV download links
            for link in soup.find_all('a', href=True):
                href = link['href']
                if any(ext in href.lower() for ext in ['.xlsx', '.xls', '.csv']):
                    download_url = href
                    if not download_url.startswith('http'):
                        download_url = 'https://www.ici.org' + download_url

                    print(f"[{self.source_name}] Found data file: {download_url}")

                    # Download the file
                    file_response = requests.get(download_url, timeout=60)
                    file_response.raise_for_status()

                    # Save to temp and read
                    from io import BytesIO
                    if '.csv' in href.lower():
                        df = pd.read_csv(BytesIO(file_response.content))
                    else:
                        df = pd.read_excel(BytesIO(file_response.content))

                    return df

            return None

        except Exception as e:
            print(f"[{self.source_name}] Error downloading data: {e}")
            return None

    def _scrape_html_tables(self) -> Optional[Dict[str, Any]]:
        """
        Scrape flow data from HTML tables on the page.

        Returns:
            Dict with flow data or None
        """
        try:
            response = requests.get(self.BASE_URL, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all tables
            tables = soup.find_all('table')

            data = {}
            for table in tables:
                # Try to extract data from each table
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        value_text = cells[-1].get_text(strip=True)

                        # Try to parse numeric value
                        value = self._parse_number(value_text)
                        if value is not None:
                            # Clean up label
                            clean_label = re.sub(r'[^a-z0-9_]', '_', label)
                            clean_label = re.sub(r'_+', '_', clean_label).strip('_')
                            if clean_label and len(clean_label) > 2:
                                data[clean_label] = value

            return data if data else None

        except Exception as e:
            print(f"[{self.source_name}] Error scraping tables: {e}")
            return None

    def _parse_number(self, text: str) -> Optional[float]:
        """Parse a number from text, handling billions/millions notation."""
        if not text:
            return None

        # Remove common non-numeric chars but keep decimals and negatives
        text = text.replace('$', '').replace(',', '').strip()

        # Handle parentheses for negative
        if text.startswith('(') and text.endswith(')'):
            text = '-' + text[1:-1]

        try:
            return float(text)
        except ValueError:
            return None

    def check_for_update(self) -> bool:
        """Check if new weekly data is available."""
        latest_date = self._get_latest_report_date()
        if not latest_date:
            # Can't determine, assume update available
            return True

        # Compare with stored data
        try:
            from ..storage import ScraperStorage
        except ImportError:
            from storage import ScraperStorage
        storage_dir = Path(__file__).parent.parent.parent.parent / "data" / "scraped"
        storage = ScraperStorage(storage_dir)

        last_scrape = storage.get_last_scrape_time(self.source_name)
        if not last_scrape:
            return True

        # If latest report date is newer than our last scrape date, update available
        try:
            latest_dt = datetime.strptime(latest_date, '%Y-%m-%d')
            return latest_dt.date() > last_scrape.date()
        except Exception:
            return True

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest ICI fund flows data."""
        print(f"[{self.source_name}] Fetching latest fund flows data...")

        source_date = self._get_latest_report_date()
        data = {}

        # Try Excel download first
        df = self._download_excel_data()
        if df is not None:
            print(f"[{self.source_name}] Successfully downloaded Excel data")
            # Convert DataFrame to dict
            # Structure depends on actual ICI file format
            data = {
                "raw_columns": list(df.columns),
                "row_count": len(df),
                "data_preview": df.head(20).to_dict(orient='records')
            }
        else:
            # Fall back to HTML scraping
            print(f"[{self.source_name}] Falling back to HTML table scraping")
            scraped_data = self._scrape_html_tables()
            if scraped_data:
                data = scraped_data
            else:
                data = {"error": "Could not extract data from source"}

        return self.format_result(
            data=data,
            source_date=source_date,
            source_url=self.BASE_URL
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = ICIScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")
    print(f"Has update: {scraper.check_for_update()}")

    result = scraper.fetch_latest()
    print(f"Result keys: {result.keys()}")
    print(f"Data: {result.get('data', {})}")
