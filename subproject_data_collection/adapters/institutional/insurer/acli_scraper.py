"""
ACLI Life Insurers Fact Book Scraper

Scrapes annual life insurer asset allocation data from ACLI.
Source: https://www.acli.com/life-insurers-fact-book

Uses PDF extraction with pdfplumber for the fact book PDF.

Data includes:
- Total general account assets
- Bond allocation
- Stock allocation
- Mortgage allocation
- Other investments
"""

from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from io import BytesIO
import re

import requests
from bs4 import BeautifulSoup

try:
    from ..base_scraper import BaseScraper
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from base_scraper import BaseScraper

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


class ACLIScraper(BaseScraper):
    """Scraper for ACLI Life Insurers Fact Book data."""

    BASE_URL = "https://www.acli.com/life-insurers-fact-book"

    @property
    def source_name(self) -> str:
        return "acli"

    @property
    def update_frequency(self) -> str:
        return "annual"

    def _find_factbook_pdf(self) -> Optional[str]:
        """
        Find the fact book PDF URL on the ACLI page.

        Returns:
            PDF URL or None
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.BASE_URL, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for PDF links
            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.get_text(strip=True).lower()

                if '.pdf' in href.lower():
                    # Look for fact book related links
                    if any(kw in title or kw in href.lower() for kw in ['fact', 'book', 'report']):
                        full_url = href
                        if not href.startswith('http'):
                            full_url = 'https://www.acli.com' + href
                        return full_url

            return None

        except Exception as e:
            print(f"[{self.source_name}] Error finding PDF: {e}")
            return None

    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download PDF file."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=120)
            response.raise_for_status()
            return response.content

        except Exception as e:
            print(f"[{self.source_name}] Error downloading PDF: {e}")
            return None

    def _extract_from_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
        """
        Extract asset allocation data from PDF.

        Returns:
            Dict with extracted data
        """
        if not PDFPLUMBER_AVAILABLE:
            return {"error": "pdfplumber not installed. Run: pip install pdfplumber"}

        try:
            data = {
                "total_assets_billion": None,
                "bonds_pct": None,
                "stocks_pct": None,
                "mortgages_pct": None,
                "real_estate_pct": None,
                "policy_loans_pct": None,
                "other_pct": None,
                "extracted_tables": [],
                "extracted_text_snippets": []
            }

            with pdfplumber.open(BytesIO(pdf_content)) as pdf:
                print(f"[{self.source_name}] PDF has {len(pdf.pages)} pages")

                # Search first 30 pages for asset allocation data
                for page_num, page in enumerate(pdf.pages[:30]):
                    text = page.extract_text() or ""

                    # Look for asset allocation sections
                    if any(kw in text.lower() for kw in ['asset', 'allocation', 'investment', 'portfolio']):

                        # Extract tables from this page
                        tables = page.extract_tables()
                        for table in tables:
                            if table and len(table) > 1:
                                # Process table rows
                                for row in table:
                                    if not row or len(row) < 2:
                                        continue

                                    label = str(row[0]).lower() if row[0] else ""
                                    value_str = str(row[-1]) if row[-1] else ""

                                    value = self._parse_number(value_str)
                                    if value is None:
                                        continue

                                    # Map to standardized keys
                                    if 'bond' in label:
                                        data['bonds_pct'] = value
                                    elif 'stock' in label or 'equit' in label:
                                        data['stocks_pct'] = value
                                    elif 'mortgage' in label:
                                        data['mortgages_pct'] = value
                                    elif 'real estate' in label:
                                        data['real_estate_pct'] = value
                                    elif 'policy loan' in label:
                                        data['policy_loans_pct'] = value
                                    elif 'total' in label and 'asset' in label:
                                        data['total_assets_billion'] = value

                                # Store table for reference
                                data['extracted_tables'].append({
                                    'page': page_num + 1,
                                    'rows': len(table)
                                })

                    # Also try regex patterns on text
                    patterns = [
                        (r'bonds?\s*[:\-]?\s*(\d+\.?\d*)\s*%', 'bonds_pct'),
                        (r'stocks?\s*[:\-]?\s*(\d+\.?\d*)\s*%', 'stocks_pct'),
                        (r'equit(?:y|ies)\s*[:\-]?\s*(\d+\.?\d*)\s*%', 'stocks_pct'),
                        (r'mortgages?\s*[:\-]?\s*(\d+\.?\d*)\s*%', 'mortgages_pct'),
                        (r'total\s*(?:general\s*account\s*)?assets?\s*[:\-]?\s*\$?(\d+\.?\d*)\s*(?:trillion|billion)', 'total_assets_billion'),
                    ]

                    for pattern, key in patterns:
                        match = re.search(pattern, text, re.IGNORECASE)
                        if match and data.get(key) is None:
                            try:
                                data[key] = float(match.group(1))
                            except ValueError:
                                pass

                    # Store relevant text snippets
                    if any(kw in text.lower() for kw in ['general account', 'asset allocation']):
                        snippet = text[:500] if len(text) > 500 else text
                        data['extracted_text_snippets'].append({
                            'page': page_num + 1,
                            'snippet': snippet
                        })

            return data

        except Exception as e:
            print(f"[{self.source_name}] PDF extraction error: {e}")
            return {"error": str(e)}

    def _parse_number(self, text: str) -> Optional[float]:
        """Parse number from text."""
        if not text:
            return None

        text = str(text).replace('$', '').replace(',', '').replace('%', '').strip()

        # Handle parentheses
        if text.startswith('(') and text.endswith(')'):
            text = '-' + text[1:-1]

        try:
            return float(text)
        except ValueError:
            return None

    def _get_report_year(self) -> str:
        """Get the year covered by the report."""
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

        # Check quarterly
        days_since = (datetime.now() - last_scrape).days
        return days_since >= 90

    def fetch_latest(self) -> Dict[str, Any]:
        """Fetch the latest ACLI fact book data."""
        print(f"[{self.source_name}] Fetching latest ACLI data...")

        # Find PDF
        pdf_url = self._find_factbook_pdf()

        if not pdf_url:
            # Try direct search
            print(f"[{self.source_name}] PDF not found on page, trying web search...")
            data = {"error": "Could not find fact book PDF on ACLI website"}
        else:
            print(f"[{self.source_name}] Found PDF: {pdf_url}")

            # Download PDF
            pdf_content = self._download_pdf(pdf_url)

            if pdf_content:
                # Extract data
                data = self._extract_from_pdf(pdf_content)
                data['pdf_url'] = pdf_url
            else:
                data = {"error": "Failed to download PDF"}

        report_year = self._get_report_year()

        return self.format_result(
            data=data,
            source_date=f"{report_year}-12-31",
            source_url=pdf_url or self.BASE_URL
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = ACLIScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")

    if not PDFPLUMBER_AVAILABLE:
        print("Warning: pdfplumber not installed")

    result = scraper.fetch_latest()
    print(f"Result: {result}")
