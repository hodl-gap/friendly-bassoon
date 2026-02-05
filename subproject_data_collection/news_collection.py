"""
News Collection Module

Collects news articles from configured sources.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from states import DataCollectionState
from config import DEFAULT_NEWS_SOURCES, DEFAULT_TIME_WINDOW_DAYS

# Import RSS adapter
try:
    from adapters.news_adapters import RSSAdapter
    RSS_AVAILABLE = True
except ImportError:
    RSS_AVAILABLE = False
    print("[news_collection] Warning: RSS adapter not available")


def collect_news(state: DataCollectionState) -> DataCollectionState:
    """
    Collect news articles from configured sources.

    LangGraph node function.

    Args:
        state: Current workflow state with news_query, news_sources, time_window_days

    Returns:
        Updated state with collected_articles
    """
    query = state.get("news_query", "")
    sources = state.get("news_sources", DEFAULT_NEWS_SOURCES)
    time_window = state.get("time_window_days", DEFAULT_TIME_WINDOW_DAYS)

    print(f"[news_collection] Starting news collection")
    print(f"[news_collection] Query: {query}")
    print(f"[news_collection] Sources: {sources}")
    print(f"[news_collection] Time window: {time_window} days")

    if not RSS_AVAILABLE:
        print("[news_collection] RSS adapter not available")
        state["collected_articles"] = []
        state["errors"] = state.get("errors", []) + ["RSS adapter not available"]
        return state

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=time_window)

    # Initialize adapter and collect
    try:
        adapter = RSSAdapter()

        # If specific sources are requested, filter feeds
        feed_names = None
        if sources and sources != DEFAULT_NEWS_SOURCES:
            feed_names = sources

        articles = adapter.fetch_articles(
            query=query,
            start_date=start_date,
            end_date=end_date,
            max_articles=100,
            feed_names=feed_names
        )

        print(f"[news_collection] Collected {len(articles)} articles")

        # Convert datetime to string for serialization
        for article in articles:
            if isinstance(article.get("published"), datetime):
                article["published"] = article["published"].isoformat()

        state["collected_articles"] = articles

    except Exception as e:
        print(f"[news_collection] Error: {e}")
        state["collected_articles"] = []
        state["errors"] = state.get("errors", []) + [f"News collection error: {str(e)}"]

    return state


def collect_institutional_news(state: DataCollectionState) -> DataCollectionState:
    """
    Collect news specifically about institutional investors.

    Specialized collection focused on pension funds, sovereign wealth funds,
    insurance companies, and other large institutional investors.

    Args:
        state: Current workflow state

    Returns:
        Updated state with collected_articles focused on institutional news
    """
    time_window = state.get("time_window_days", DEFAULT_TIME_WINDOW_DAYS)

    print(f"[news_collection] Collecting institutional investor news")

    if not RSS_AVAILABLE:
        print("[news_collection] RSS adapter not available")
        state["collected_articles"] = []
        state["errors"] = state.get("errors", []) + ["RSS adapter not available"]
        return state

    try:
        adapter = RSSAdapter()
        articles = adapter.fetch_institutional_news(
            days_back=time_window,
            max_articles=100
        )

        print(f"[news_collection] Found {len(articles)} institutional news articles")

        # Convert datetime to string
        for article in articles:
            if isinstance(article.get("published"), datetime):
                article["published"] = article["published"].isoformat()

        state["collected_articles"] = articles

    except Exception as e:
        print(f"[news_collection] Error: {e}")
        state["collected_articles"] = []
        state["errors"] = state.get("errors", []) + [f"Institutional news error: {str(e)}"]

    return state


# Testing entry point
if __name__ == "__main__":
    from states import DataCollectionState

    state = DataCollectionState(
        mode="news_collection",
        news_query="pension fund, rebalancing",
        time_window_days=3
    )

    state = collect_news(state)
    print(f"\nCollected {len(state.get('collected_articles', []))} articles")

    for article in state.get("collected_articles", [])[:5]:
        print(f"\n- {article['title'][:60]}...")
        print(f"  Source: {article['source']}")
