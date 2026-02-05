"""
Base News Adapter

Abstract interface for news collection adapters.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional


class BaseNewsAdapter(ABC):
    """Abstract base class for news data adapters."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the source name (e.g., 'RSS', 'NewsAPI')."""
        pass

    @abstractmethod
    def fetch_articles(
        self,
        query: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_articles: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Fetch articles from the news source.

        Args:
            query: Optional search query/keywords
            start_date: Start of date range
            end_date: End of date range
            max_articles: Maximum number of articles to return

        Returns:
            List of article dictionaries with structure:
            {
                "title": str,
                "link": str,
                "published": datetime,
                "summary": str,
                "source": str,
                "author": Optional[str],
                "content": Optional[str]
            }
        """
        pass

    @abstractmethod
    def get_available_sources(self) -> List[str]:
        """
        Get list of available news sources/feeds.

        Returns:
            List of source identifiers
        """
        pass

    def filter_by_keywords(
        self,
        articles: List[Dict[str, Any]],
        keywords: List[str],
        match_all: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Filter articles by keywords in title or summary.

        Args:
            articles: List of article dicts
            keywords: Keywords to search for
            match_all: If True, article must contain all keywords

        Returns:
            Filtered list of articles
        """
        if not keywords:
            return articles

        filtered = []
        keywords_lower = [kw.lower() for kw in keywords]

        for article in articles:
            text = f"{article.get('title', '')} {article.get('summary', '')}".lower()

            if match_all:
                if all(kw in text for kw in keywords_lower):
                    filtered.append(article)
            else:
                if any(kw in text for kw in keywords_lower):
                    filtered.append(article)

        return filtered
