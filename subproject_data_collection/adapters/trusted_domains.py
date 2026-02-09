"""
Trusted Domains Module

Defines trusted web sources for logic chain extraction.
Only extracts from verified financial institutions, news outlets, and central banks.
"""

from typing import Dict, Tuple, List, Optional, Any
from urllib.parse import urlparse


# Trusted domains with tier and display name
# Tier 1: Investment banks, major financial news, central banks
# Tier 2: Secondary financial news (optional, configurable)
TRUSTED_DOMAINS: Dict[str, Dict[str, Any]] = {
    # Tier 1: Investment Banks
    "goldmansachs.com": {"name": "Goldman Sachs", "tier": 1},
    "gs.com": {"name": "Goldman Sachs", "tier": 1},
    "morganstanley.com": {"name": "Morgan Stanley", "tier": 1},
    "jpmorgan.com": {"name": "JPMorgan", "tier": 1},
    "jpmorganchase.com": {"name": "JPMorgan Chase", "tier": 1},
    "bankofamerica.com": {"name": "Bank of America", "tier": 1},
    "ml.com": {"name": "Merrill Lynch", "tier": 1},
    "citi.com": {"name": "Citi", "tier": 1},
    "citigroup.com": {"name": "Citigroup", "tier": 1},
    "ubs.com": {"name": "UBS", "tier": 1},
    "credit-suisse.com": {"name": "Credit Suisse", "tier": 1},
    "barclays.com": {"name": "Barclays", "tier": 1},
    "db.com": {"name": "Deutsche Bank", "tier": 1},
    "nomura.com": {"name": "Nomura", "tier": 1},
    "hsbc.com": {"name": "HSBC", "tier": 1},

    # Tier 1: Major Financial News
    "bloomberg.com": {"name": "Bloomberg", "tier": 1},
    "reuters.com": {"name": "Reuters", "tier": 1},
    "ft.com": {"name": "Financial Times", "tier": 1},
    "wsj.com": {"name": "Wall Street Journal", "tier": 1},
    "nikkei.com": {"name": "Nikkei", "tier": 1},
    "yahoo.com": {"name": "Yahoo Finance", "tier": 1},
    "finance.yahoo.com": {"name": "Yahoo Finance", "tier": 1},
    "forbes.com": {"name": "Forbes", "tier": 1},

    # Tier 1: Central Banks
    "federalreserve.gov": {"name": "Federal Reserve", "tier": 1},
    "ecb.europa.eu": {"name": "ECB", "tier": 1},
    "boj.or.jp": {"name": "Bank of Japan", "tier": 1},
    "bankofengland.co.uk": {"name": "Bank of England", "tier": 1},
    "snb.ch": {"name": "Swiss National Bank", "tier": 1},
    "rba.gov.au": {"name": "Reserve Bank of Australia", "tier": 1},
    "bis.org": {"name": "Bank for International Settlements", "tier": 1},
    "imf.org": {"name": "IMF", "tier": 1},

    # Tier 1: Major Asset Managers / Hedge Funds
    "bridgewater.com": {"name": "Bridgewater", "tier": 1},
    "blackrock.com": {"name": "BlackRock", "tier": 1},
    "pimco.com": {"name": "PIMCO", "tier": 1},
    "vanguard.com": {"name": "Vanguard", "tier": 1},
    "fidelity.com": {"name": "Fidelity", "tier": 1},
    "statestreet.com": {"name": "State Street", "tier": 1},
    "citadel.com": {"name": "Citadel", "tier": 1},
    "apollo.com": {"name": "Apollo", "tier": 1},
    "pictet.com": {"name": "Pictet", "tier": 1},

    # Tier 1: Additional Banks
    "sc.com": {"name": "Standard Chartered", "tier": 1},
    "standardchartered.com": {"name": "Standard Chartered", "tier": 1},
    "wellsfargo.com": {"name": "Wells Fargo", "tier": 1},
    "ing.com": {"name": "ING", "tier": 1},
    "bnpparibas.com": {"name": "BNP Paribas", "tier": 1},

    # Tier 1: US Government / Official
    "treasury.gov": {"name": "US Treasury", "tier": 1},
    "bls.gov": {"name": "Bureau of Labor Statistics", "tier": 1},
    "whitehouse.gov": {"name": "White House", "tier": 1},
    "newyorkfed.org": {"name": "NY Fed", "tier": 1},
    "sec.gov": {"name": "SEC", "tier": 1},

    # Tier 1: Research Firms
    "fundstrat.com": {"name": "Fundstrat", "tier": 1},
    "yardeni.com": {"name": "Yardeni Research", "tier": 1},
    "bcaresearch.com": {"name": "BCA Research", "tier": 1},
    "neddavis.com": {"name": "Ned Davis Research", "tier": 1},
    "tslombard.com": {"name": "TS Lombard", "tier": 1},
    "bernstein.com": {"name": "Bernstein", "tier": 1},
    "alliancebernstein.com": {"name": "Bernstein", "tier": 1},

    # Tier 1: ETF/Asset Managers
    "vaneck.com": {"name": "VanEck", "tier": 1},
    "ark-invest.com": {"name": "ARK Invest", "tier": 1},
    "ark-funds.com": {"name": "ARK Invest", "tier": 1},

    # Tier 1: Exchanges
    "cmegroup.com": {"name": "CME Group", "tier": 1},

    # Tier 2: Secondary Financial News
    "marketwatch.com": {"name": "MarketWatch", "tier": 2},
    "cnbc.com": {"name": "CNBC", "tier": 2},
    "economist.com": {"name": "The Economist", "tier": 2},
    "barrons.com": {"name": "Barron's", "tier": 2},
    "investing.com": {"name": "Investing.com", "tier": 2},
    "seekingalpha.com": {"name": "Seeking Alpha", "tier": 2},
    "zerohedge.com": {"name": "ZeroHedge", "tier": 2},
    "fortune.com": {"name": "Fortune", "tier": 2},
    "businessinsider.com": {"name": "Business Insider", "tier": 2},
    "morningstar.com": {"name": "Morningstar", "tier": 2},

    # Tier 2: Crypto Asset Managers / Research
    "grayscale.com": {"name": "Grayscale", "tier": 2},
    "bitwiseinvestments.com": {"name": "Bitwise", "tier": 2},
    "coinbase.com": {"name": "Coinbase", "tier": 2},
    "k33.com": {"name": "K33 Research", "tier": 2},

    # Tier 2: On-Chain Analytics
    "glassnode.com": {"name": "Glassnode", "tier": 2},
    "cryptoquant.com": {"name": "CryptoQuant", "tier": 2},
    "chainalysis.com": {"name": "Chainalysis", "tier": 2},

    # Tier 2: Crypto News
    "coindesk.com": {"name": "CoinDesk", "tier": 2},
    "cointelegraph.com": {"name": "Cointelegraph", "tier": 2},
    "theblock.co": {"name": "The Block", "tier": 2},
}


def extract_domain(url: str) -> str:
    """
    Extract the base domain from a URL.

    Examples:
        https://www.bloomberg.com/news/article → bloomberg.com
        https://research.gs.com/report → gs.com
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]

        # Handle subdomains: keep last two parts (e.g., research.gs.com → gs.com)
        parts = domain.split(".")
        if len(parts) >= 2:
            # Special handling for .co.uk, .or.jp, etc.
            if len(parts) >= 3 and parts[-2] in ("co", "or", "gov", "ac"):
                return ".".join(parts[-3:])
            return ".".join(parts[-2:])

        return domain
    except Exception:
        return ""


def is_trusted_domain(url: str, min_tier: int = 2) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if a URL is from a trusted domain.

    Args:
        url: The URL to check
        min_tier: Minimum tier required (1 = only Tier 1, 2 = include Tier 2)

    Returns:
        (is_trusted, domain_info) where domain_info contains name and tier
        Returns (False, None) if not trusted
    """
    domain = extract_domain(url)
    if not domain:
        return (False, None)

    if domain in TRUSTED_DOMAINS:
        info = TRUSTED_DOMAINS[domain]
        if info["tier"] <= min_tier:
            return (True, {"domain": domain, **info})

    return (False, None)


def filter_to_trusted_sources(
    results: List[Dict[str, Any]],
    min_tier: int = 2
) -> List[Dict[str, Any]]:
    """
    Filter search results to only include trusted sources.

    Args:
        results: List of search result dicts with 'url' field
        min_tier: Minimum tier required (1 = only Tier 1, 2 = include Tier 2)

    Returns:
        Filtered list with only trusted sources.
        Each result is annotated with 'trusted_source' info.
    """
    filtered = []

    for result in results:
        url = result.get("url", "")
        is_trusted, info = is_trusted_domain(url, min_tier)

        if is_trusted:
            # Annotate result with source info
            annotated = {
                **result,
                "trusted_source": info
            }
            filtered.append(annotated)

    return filtered


def get_trusted_domains_for_tier(tier: int) -> List[str]:
    """
    Get all trusted domains for a specific tier or below.

    Args:
        tier: Maximum tier to include (1 or 2)

    Returns:
        List of domain names
    """
    return [
        domain for domain, info in TRUSTED_DOMAINS.items()
        if info["tier"] <= tier
    ]
