"""
News Adapters Package

Provides adapters for collecting news from various sources.
"""

from .base_news_adapter import BaseNewsAdapter
from .rss_adapter import RSSAdapter

__all__ = [
    "BaseNewsAdapter",
    "RSSAdapter"
]
