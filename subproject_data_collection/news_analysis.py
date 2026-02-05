"""
News Analysis Module

Analyzes collected news for actionable insights and generates retriever queries.
"""

import json
from typing import Dict, Any, List
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))
from models import call_claude_haiku

from states import DataCollectionState
from news_analysis_prompts import (
    NEWS_ACTIONABILITY_PROMPT,
    RETRIEVER_QUERY_GENERATION_PROMPT
)
from news_collection_prompts import NEWS_RELEVANCE_PROMPT


def filter_relevant_articles(state: DataCollectionState) -> DataCollectionState:
    """
    Filter collected articles for relevance using LLM.

    LangGraph node function.

    Args:
        state: Current workflow state with collected_articles

    Returns:
        Updated state with filtered_articles
    """
    articles = state.get("collected_articles", [])
    query = state.get("news_query", "institutional investor rebalancing")

    if not articles:
        print("[news_analysis] No articles to filter")
        state["filtered_articles"] = []
        return state

    print(f"[news_analysis] Filtering {len(articles)} articles for relevance")

    filtered = []
    for article in articles:
        relevance = assess_article_relevance(article, query)

        if relevance.get("is_relevant", False) and relevance.get("relevance_score", 0) >= 0.6:
            article["relevance"] = relevance
            filtered.append(article)
            print(f"[news_analysis] Relevant: {article['title'][:50]}... (score: {relevance.get('relevance_score', 0):.2f})")

    print(f"[news_analysis] Filtered to {len(filtered)} relevant articles")
    state["filtered_articles"] = filtered

    return state


def assess_article_relevance(article: Dict[str, Any], query: str) -> Dict[str, Any]:
    """
    Assess relevance of a single article using LLM.

    Args:
        article: Article dictionary
        query: Search query/context

    Returns:
        Relevance assessment dict
    """
    prompt = NEWS_RELEVANCE_PROMPT.format(
        query=query,
        title=article.get("title", ""),
        source=article.get("source", ""),
        published=article.get("published", ""),
        summary=article.get("summary", "")[:500]
    )

    try:
        response = call_claude_haiku(prompt)
        print(f"[news_analysis] Relevance response: {response[:200]}...")

        # Parse JSON response
        result = json.loads(response)
        return result
    except json.JSONDecodeError:
        # Try to extract JSON from response
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception:
            pass

        return {"is_relevant": False, "relevance_score": 0.0, "error": "Parse error"}
    except Exception as e:
        print(f"[news_analysis] Error assessing relevance: {e}")
        return {"is_relevant": False, "relevance_score": 0.0, "error": str(e)}


def analyze_news_actionability(state: DataCollectionState) -> DataCollectionState:
    """
    Analyze filtered news for actionable insights.

    LangGraph node function.

    Args:
        state: Current workflow state with filtered_articles

    Returns:
        Updated state with analyzed_news
    """
    articles = state.get("filtered_articles", [])

    if not articles:
        print("[news_analysis] No articles to analyze")
        state["analyzed_news"] = []
        return state

    print(f"[news_analysis] Analyzing {len(articles)} articles for actionability")

    analyzed = []
    for article in articles:
        analysis = analyze_single_article(article)
        if analysis.get("confidence", 0) >= 0.5:
            analysis["article"] = {
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "published": article.get("published", ""),
                "link": article.get("link", "")
            }
            analyzed.append(analysis)
            print(f"[news_analysis] Actionable: {article['title'][:40]}... - {analysis.get('action', 'N/A')}")

    print(f"[news_analysis] Found {len(analyzed)} actionable insights")
    state["analyzed_news"] = analyzed

    return state


def analyze_single_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a single article for actionable insights.

    Args:
        article: Article dictionary with relevance data

    Returns:
        Analysis result with institution, action, direction, insight
    """
    prompt = NEWS_ACTIONABILITY_PROMPT.format(
        title=article.get("title", ""),
        source=article.get("source", ""),
        published=article.get("published", ""),
        summary=article.get("summary", "")[:800],
        content=article.get("content", "")[:1000] if article.get("content") else ""
    )

    try:
        response = call_claude_haiku(prompt)
        print(f"[news_analysis] Actionability response: {response[:200]}...")

        result = json.loads(response)
        return result
    except json.JSONDecodeError:
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception:
            pass

        return {"confidence": 0.0, "error": "Parse error"}
    except Exception as e:
        print(f"[news_analysis] Error analyzing article: {e}")
        return {"confidence": 0.0, "error": str(e)}


def generate_retriever_queries(state: DataCollectionState) -> DataCollectionState:
    """
    Generate follow-up queries for the retriever based on analyzed news.

    LangGraph node function.

    Args:
        state: Current workflow state with analyzed_news

    Returns:
        Updated state with retriever_queries
    """
    analyzed = state.get("analyzed_news", [])

    if not analyzed:
        print("[news_analysis] No analyzed news for query generation")
        state["retriever_queries"] = []
        return state

    # Filter for high-confidence insights
    actionable = [a for a in analyzed if a.get("confidence", 0) >= 0.6]

    if not actionable:
        print("[news_analysis] No high-confidence insights for queries")
        state["retriever_queries"] = []
        return state

    print(f"[news_analysis] Generating queries for {len(actionable)} actionable insights")

    # Build summary of insights for query generation
    insights_summary = []
    for insight in actionable[:5]:  # Limit to top 5
        insights_summary.append({
            "institution": insight.get("institution", "Unknown"),
            "action": insight.get("action", ""),
            "asset_class": insight.get("asset_class", ""),
            "direction": insight.get("direction", ""),
            "actionable_insight": insight.get("actionable_insight", "")
        })

    prompt = RETRIEVER_QUERY_GENERATION_PROMPT.format(
        insights=json.dumps(insights_summary, indent=2)
    )

    try:
        response = call_claude_haiku(prompt)
        print(f"[news_analysis] Query generation response: {response}")

        result = json.loads(response)
        queries = result.get("queries", [])

        print(f"[news_analysis] Generated {len(queries)} retriever queries")
        state["retriever_queries"] = queries

    except Exception as e:
        print(f"[news_analysis] Error generating queries: {e}")
        state["retriever_queries"] = []
        state["warnings"] = state.get("warnings", []) + [f"Query generation error: {str(e)}"]

    return state


# Testing entry point
if __name__ == "__main__":
    from states import DataCollectionState

    # Test with mock article
    state = DataCollectionState(
        mode="news_collection",
        news_query="institutional rebalancing",
        collected_articles=[
            {
                "title": "Japanese insurers shift allocations to domestic bonds amid yen weakness",
                "source": "reuters_markets",
                "published": "2026-01-27T10:00:00",
                "summary": "Major Japanese insurance companies are rebalancing portfolios toward JGBs as yen depreciation impacts foreign asset values.",
                "link": "https://example.com/article1"
            }
        ]
    )

    state = filter_relevant_articles(state)
    print(f"\nFiltered: {len(state.get('filtered_articles', []))} articles")

    state = analyze_news_actionability(state)
    print(f"Analyzed: {len(state.get('analyzed_news', []))} insights")

    state = generate_retriever_queries(state)
    print(f"Queries: {state.get('retriever_queries', [])}")
