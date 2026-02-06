"""
Test script for on-the-fly logic chain extraction from trusted web sources.

Tests:
1. Trusted domain filtering
2. Chain extraction from search results
3. Evidence quote verification
"""

import sys
from pathlib import Path

# Add parent paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / '.env')

from adapters.web_search_adapter import WebSearchAdapter
from adapters.trusted_domains import (
    TRUSTED_DOMAINS,
    is_trusted_domain,
    filter_to_trusted_sources,
    get_trusted_domains_for_tier
)
from config import TRUSTED_DOMAIN_MIN_TIER


def test_trusted_domains():
    """Test domain filtering logic."""
    print("=" * 60)
    print("TEST 1: Trusted Domain Filtering")
    print("=" * 60)

    print(f"\nCurrent config: TRUSTED_DOMAIN_MIN_TIER = {TRUSTED_DOMAIN_MIN_TIER}")

    tier1_domains = get_trusted_domains_for_tier(1)
    print(f"Tier 1 domains: {len(tier1_domains)}")

    # Test some URLs
    test_urls = [
        "https://www.bloomberg.com/news/articles/2026/ai-capex",
        "https://research.gs.com/report/ai-spending",
        "https://www.cnbc.com/2026/01/tech-capex.html",  # Tier 2
        "https://random-blog.com/ai-thoughts",  # Not trusted
        "https://www.federalreserve.gov/monetarypolicy",
    ]

    print("\nURL trust checks:")
    for url in test_urls:
        is_trusted, info = is_trusted_domain(url, min_tier=TRUSTED_DOMAIN_MIN_TIER)
        status = f"✓ {info['name']} (Tier {info['tier']})" if is_trusted else "✗ Not trusted"
        print(f"  {url[:50]}... → {status}")

    # Test filter function
    mock_results = [
        {"url": "https://www.bloomberg.com/test", "title": "Bloomberg"},
        {"url": "https://cnbc.com/test", "title": "CNBC"},  # Tier 2
        {"url": "https://random.com/test", "title": "Random"},
    ]
    filtered = filter_to_trusted_sources(mock_results, min_tier=TRUSTED_DOMAIN_MIN_TIER)
    print(f"\nFilter test: {len(mock_results)} results → {len(filtered)} trusted (Tier 1 only)")

    return True


def test_chain_extraction():
    """Test full chain extraction pipeline."""
    print("\n" + "=" * 60)
    print("TEST 2: Logic Chain Extraction")
    print("=" * 60)

    adapter = WebSearchAdapter(max_results=8)

    # Test query from the plan
    query = "AI CAPEX impact tech stocks investment analysis"
    topic = "AI capital expenditure impact on technology stocks"

    print(f"\nQuery: {query}")
    print(f"Topic: {topic}")
    print(f"Min tier: {TRUSTED_DOMAIN_MIN_TIER} (Tier 1 only)")
    print("\nSearching and extracting chains...")

    result = adapter.search_and_extract_chains(
        query=query,
        topic=topic,
        min_tier=TRUSTED_DOMAIN_MIN_TIER,
        verify_quotes=True
    )

    print("\n" + "-" * 60)
    print("RESULTS:")
    print("-" * 60)

    print(f"\nAll sources found: {len(result.get('all_sources', []))}")
    for url in result.get('all_sources', [])[:5]:
        print(f"  - {url[:70]}...")

    print(f"\nTrusted sources (Tier 1): {result.get('trusted_sources_count', 0)}")
    for url in result.get('filtered_sources', []):
        print(f"  - {url[:70]}...")

    chains = result.get('chains', [])
    print(f"\nChains extracted: {len(chains)}")

    for i, chain in enumerate(chains, 1):
        print(f"\n  Chain {i}:")
        print(f"    Cause: {chain.get('cause', 'N/A')[:60]}...")
        print(f"    Effect: {chain.get('effect', 'N/A')[:60]}...")
        print(f"    Polarity: {chain.get('polarity', 'N/A')}")
        print(f"    Source: {chain.get('source_name', 'N/A')}")
        print(f"    Confidence: {chain.get('confidence', 'N/A')}")
        quote = chain.get('evidence_quote', '')
        print(f"    Quote verified: {chain.get('quote_verified', 'N/A')}")
        if quote:
            print(f"    Evidence: \"{quote[:80]}...\"")

    if result.get('summary'):
        print(f"\nSummary: {result.get('summary')}")

    if result.get('warning'):
        print(f"\n⚠️ Warning: {result.get('warning')}")

    if result.get('error'):
        print(f"\n❌ Error: {result.get('error')}")

    return result


def main():
    print("\n" + "=" * 60)
    print("WEB CHAIN EXTRACTION TEST")
    print("=" * 60)

    # Test 1: Domain filtering
    test_trusted_domains()

    # Test 2: Full chain extraction
    result = test_chain_extraction()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    return result


if __name__ == "__main__":
    main()
