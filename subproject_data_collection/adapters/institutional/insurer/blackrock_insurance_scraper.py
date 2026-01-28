"""
BlackRock Global Insurance Report Scraper

Scrapes annual BlackRock Global Insurance Report data.
Uses web search to find the latest report PDF and extracts data.

Data includes:
- Global insurer asset allocation trends
- Investment strategy shifts
- Regional allocation differences
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from io import BytesIO
import json

import requests
from bs4 import BeautifulSoup

try:
    from ..base_scraper import BaseScraper
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from base_scraper import BaseScraper

# Add parent path for models import
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


# Extraction prompt for BlackRock insurance survey
BLACKROCK_EXTRACTION_PROMPT = """Extract key findings from the BlackRock Global Insurance Report search results.

Search results:
{search_results}

Extract and return a JSON object with these fields (use null if not found):
{{
    "report_year": "year of the report",
    "total_assets_surveyed_trillion": "total AUM of surveyed insurers in trillions",
    "respondent_count": "number of insurers surveyed",
    "allocation_shifts": {{
        "increasing": ["asset classes with increasing allocation"],
        "decreasing": ["asset classes with decreasing allocation"]
    }},
    "top_concerns": ["list of top investment concerns"],
    "private_markets_allocation_pct": "percentage allocated to private markets",
    "esg_focus": "key ESG/sustainability findings",
    "regional_trends": {{
        "americas": "key trend for Americas insurers",
        "emea": "key trend for EMEA insurers",
        "apac": "key trend for APAC insurers"
    }},
    "key_findings": ["list of other notable findings"],
    "source_urls": ["urls with data"]
}}

Only include data explicitly mentioned in the search results.
Return valid JSON only.
"""


class BlackRockInsuranceScraper(BaseScraper):
    """Scraper for BlackRock Global Insurance Report."""

    @property
    def source_name(self) -> str:
        return "blackrock_insurance"

    @property
    def update_frequency(self) -> str:
        return "annual"

    def _search_for_report(self) -> List[Dict]:
        """Search for BlackRock insurance report."""
        try:
            from duckduckgo_search import DDGS

            current_year = datetime.now().year
            queries = [
                f"BlackRock Global Insurance Report {current_year}",
                f"BlackRock insurance survey {current_year} asset allocation",
                f"BlackRock Global Insurance Report {current_year - 1}"
            ]

            all_results = []
            with DDGS() as ddgs:
                for query in queries:
                    results = list(ddgs.text(query, max_results=5))
                    for r in results:
                        all_results.append({
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                            "url": r.get("href", "")
                        })
                    import time
                    time.sleep(0.5)

            return all_results

        except ImportError:
            print(f"[{self.source_name}] duckduckgo-search not installed")
            return []
        except Exception as e:
            print(f"[{self.source_name}] Search error: {e}")
            return []

    def _find_pdf_url(self, search_results: List[Dict]) -> Optional[str]:
        """Find PDF URL from search results or by crawling pages."""
        for result in search_results:
            url = result.get('url', '')
            # Check if direct PDF link
            if '.pdf' in url.lower():
                return url

            # Check if BlackRock page that might have PDF
            if 'blackrock.com' in url.lower():
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    response = requests.get(url, headers=headers, timeout=30)
                    soup = BeautifulSoup(response.text, 'html.parser')

                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if '.pdf' in href.lower() and 'insurance' in href.lower():
                            if not href.startswith('http'):
                                href = 'https://www.blackrock.com' + href
                            return href

                except Exception:
                    continue

        return None

    def _extract_from_pdf(self, pdf_url: str) -> Dict[str, Any]:
        """Download and extract data from PDF."""
        if not PDFPLUMBER_AVAILABLE:
            return {"error": "pdfplumber not installed"}

        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(pdf_url, headers=headers, timeout=120)
            response.raise_for_status()

            data = {
                "allocation_trends": {},
                "top_concerns": [],
                "key_findings": [],
                "extracted_text": []
            }

            with pdfplumber.open(BytesIO(response.content)) as pdf:
                print(f"[{self.source_name}] PDF has {len(pdf.pages)} pages")

                for page_num, page in enumerate(pdf.pages[:20]):
                    text = page.extract_text() or ""

                    # Look for relevant sections
                    if any(kw in text.lower() for kw in ['allocation', 'investment', 'portfolio', 'survey']):
                        # Store snippets
                        data['extracted_text'].append({
                            'page': page_num + 1,
                            'snippet': text[:1000]
                        })

                        # Extract tables
                        tables = page.extract_tables()
                        for table in tables:
                            if table and len(table) > 1:
                                data.setdefault('tables', []).append({
                                    'page': page_num + 1,
                                    'data': table[:10]  # First 10 rows
                                })

            return data

        except Exception as e:
            print(f"[{self.source_name}] PDF extraction error: {e}")
            return {"error": str(e)}

    def _extract_from_search(self, search_results: List[Dict]) -> Dict[str, Any]:
        """Extract key data from search results using LLM."""
        if not search_results:
            return {"error": "No search results"}

        # Format results
        formatted = []
        for i, r in enumerate(search_results, 1):
            formatted.append(f"[{i}] {r.get('title', '')}\n{r.get('snippet', '')}\nURL: {r.get('url', '')}\n")

        formatted_text = "\n".join(formatted)

        try:
            from models import call_claude_haiku

            prompt = BLACKROCK_EXTRACTION_PROMPT.format(search_results=formatted_text)
            messages = [{"role": "user", "content": prompt}]
            response = call_claude_haiku(messages, temperature=0.0, max_tokens=1500)

            print(f"[{self.source_name}] Raw LLM response:\n{response}")

            # Parse JSON
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            return json.loads(json_str)

        except Exception as e:
            print(f"[{self.source_name}] Extraction error: {e}")
            return {"error": str(e), "raw_results": formatted_text[:2000]}

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
        """Fetch the latest BlackRock insurance report data."""
        print(f"[{self.source_name}] Searching for BlackRock insurance report...")

        # Search for report
        search_results = self._search_for_report()
        print(f"[{self.source_name}] Found {len(search_results)} search results")

        data = {}
        source_url = "web_search"

        # Try to find and extract from PDF
        pdf_url = self._find_pdf_url(search_results)
        if pdf_url:
            print(f"[{self.source_name}] Found PDF: {pdf_url}")
            pdf_data = self._extract_from_pdf(pdf_url)
            data.update(pdf_data)
            source_url = pdf_url

        # Also extract from search results
        search_extracted = self._extract_from_search(search_results)
        data['search_extracted'] = search_extracted

        # Get source URLs
        source_urls = search_extracted.get('source_urls', [])
        if source_urls and not pdf_url:
            source_url = source_urls[0]

        # Determine report year
        report_year = search_extracted.get('report_year') or str(datetime.now().year - 1)

        return self.format_result(
            data=data,
            source_date=f"{report_year}-12-31",
            source_url=source_url
        )


if __name__ == "__main__":
    # Test the scraper
    scraper = BlackRockInsuranceScraper()
    print(f"Source: {scraper.source_name}")
    print(f"Frequency: {scraper.update_frequency}")

    result = scraper.fetch_latest()
    print(f"Result keys: {result.keys()}")
