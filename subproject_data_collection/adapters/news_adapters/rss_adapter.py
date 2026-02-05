"""
RSS Feed Adapter

Fetches news articles from RSS feeds.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from email.utils import parsedate_to_datetime

from .base_news_adapter import BaseNewsAdapter

# Try to import feedparser
try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    print("[rss_adapter] Warning: feedparser not installed. RSS fetching unavailable.")


# Default RSS feeds for institutional/financial news
DEFAULT_RSS_FEEDS = {
    "reuters_markets": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "reuters_world": "https://www.reutersagency.com/feed/?taxonomy=best-regions&post_type=best",
    "ft_markets": "https://www.ft.com/markets?format=rss",
    "ft_world": "https://www.ft.com/world?format=rss",
    "bloomberg_markets": "https://feeds.bloomberg.com/markets/news.rss",
    "wsj_markets": "https://feeds.a]wsj.com/rss/RSSMarketsMain.xml",
    "nikkei_asia": "https://asia.nikkei.com/rss/feed/nar",
    "cnbc_finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
}

# Keywords for institutional investor news
INSTITUTIONAL_KEYWORDS = [
    "pension fund", "sovereign wealth", "insurance", "insurer",
    "rebalancing", "allocation", "portfolio", "institutional",
    "GPIF", "CalPERS", "Norges Bank", "GIC", "CIC", "ADIA",
    "central bank", "treasury", "reserve", "asset manager"
]


class RSSAdapter(BaseNewsAdapter):
    """Adapter for fetching news from RSS feeds."""

    def __init__(self, feeds: Dict[str, str] = None, rate_limit_delay: float = 1.0):
        """
        Initialize RSS adapter.

        Args:
            feeds: Dict of feed_name -> feed_url
            rate_limit_delay: Delay between feed requests in seconds
        """
        if not FEEDPARSER_AVAILABLE:
            raise ImportError("feedparser is required for RSSAdapter. Install with: pip install feedparser")

        self.feeds = feeds or DEFAULT_RSS_FEEDS
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0

    @property
    def source_name(self) -> str:
        return "RSS"

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def fetch_articles(
        self,
        query: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_articles: int = 50,
        feed_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch articles from RSS feeds.

        Args:
            query: Optional keywords to filter (comma-separated)
            start_date: Start of date range
            end_date: End of date range
            max_articles: Maximum articles to return
            feed_names: Specific feeds to query (None = all)

        Returns:
            List of article dictionaries
        """
        if not FEEDPARSER_AVAILABLE:
            print("[rss_adapter] feedparser not available")
            return []

        # Determine which feeds to query
        feeds_to_query = {}
        if feed_names:
            feeds_to_query = {k: v for k, v in self.feeds.items() if k in feed_names}
        else:
            feeds_to_query = self.feeds

        # Set default date range
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        # Parse keywords
        keywords = []
        if query:
            keywords = [kw.strip().lower() for kw in query.split(",")]

        all_articles = []

        for feed_name, feed_url in feeds_to_query.items():
            try:
                self._rate_limit()
                articles = self._parse_feed(feed_name, feed_url, start_date, end_date)
                all_articles.extend(articles)
                print(f"[rss_adapter] {feed_name}: {len(articles)} articles")
            except Exception as e:
                print(f"[rss_adapter] Error fetching {feed_name}: {e}")

        # Filter by keywords if provided
        if keywords:
            all_articles = self.filter_by_keywords(all_articles, keywords)

        # Sort by date (newest first) and limit
        all_articles.sort(key=lambda x: x.get("published", datetime.min), reverse=True)
        return all_articles[:max_articles]

    def _parse_feed(
        self,
        feed_name: str,
        feed_url: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Parse a single RSS feed.

        Args:
            feed_name: Name identifier for the feed
            feed_url: URL of the RSS feed
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of parsed articles
        """
        feed = feedparser.parse(feed_url)

        if feed.bozo and feed.bozo_exception:
            print(f"[rss_adapter] Feed parse warning for {feed_name}: {feed.bozo_exception}")

        articles = []

        for entry in feed.entries:
            # Parse published date
            published = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])
            elif hasattr(entry, 'published'):
                try:
                    published = parsedate_to_datetime(entry.published)
                except Exception:
                    published = datetime.now()
            else:
                published = datetime.now()

            # Make datetime naive for comparison if needed
            if published.tzinfo is not None:
                published = published.replace(tzinfo=None)

            # Filter by date range
            if published < start_date or published > end_date:
                continue

            # Build article dict
            article = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": published,
                "summary": entry.get("summary", entry.get("description", "")),
                "source": feed_name,
                "author": entry.get("author"),
                "content": self._extract_content(entry)
            }

            # Clean up summary (remove HTML tags)
            article["summary"] = self._clean_html(article["summary"])

            articles.append(article)

        return articles

    def _extract_content(self, entry) -> Optional[str]:
        """Extract full content from entry if available."""
        if hasattr(entry, 'content') and entry.content:
            if isinstance(entry.content, list) and entry.content:
                return self._clean_html(entry.content[0].get('value', ''))
        return None

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        if not text:
            return ""

        import re
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', ' ', text)
        # Normalize whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def get_available_sources(self) -> List[str]:
        """Get list of available feed names."""
        return list(self.feeds.keys())

    def add_feed(self, name: str, url: str):
        """Add a new RSS feed source."""
        self.feeds[name] = url

    def fetch_institutional_news(
        self,
        days_back: int = 7,
        max_articles: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Fetch news specifically about institutional investors.

        Args:
            days_back: How many days back to search
            max_articles: Maximum articles to return

        Returns:
            Articles filtered for institutional investor content
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        # Fetch all articles
        all_articles = self.fetch_articles(
            start_date=start_date,
            end_date=end_date,
            max_articles=200  # Fetch more, then filter
        )

        # Filter for institutional keywords
        filtered = self.filter_by_keywords(all_articles, INSTITUTIONAL_KEYWORDS)

        return filtered[:max_articles]


# Testing entry point
if __name__ == "__main__":
    if FEEDPARSER_AVAILABLE:
        adapter = RSSAdapter()
        print("Available feeds:", adapter.get_available_sources())

        # Test fetch
        print("\nFetching recent articles...")
        articles = adapter.fetch_articles(
            max_articles=5,
            feed_names=["yahoo_finance"]
        )

        for article in articles:
            print(f"\n- {article['title'][:60]}...")
            print(f"  Published: {article['published']}")
            print(f"  Source: {article['source']}")
    else:
        print("feedparser not installed. Run: pip install feedparser")
