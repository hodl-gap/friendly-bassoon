"""Prompts for historical event detection and data enrichment."""

GAP_DETECTION_PROMPT = """You are analyzing a user query about macro/BTC impact to detect if they're asking about a HISTORICAL EVENT that needs actual market data to answer properly.

USER QUERY:
{query}

RETRIEVED RESEARCH SYNTHESIS:
{synthesis}

TOPIC COVERAGE NOTE:
{extrapolation_note}

Analyze the query and determine:
1. Is the user asking about a SPECIFIC HISTORICAL EVENT (e.g., "August 2024 yen crash", "2022 Fed tightening", "COVID crash")?
2. Does the retrieved research MENTION this event but lack ACTUAL HISTORICAL DATA (prices, correlations, magnitudes)?
3. Would fetching actual market data from that period help answer the question?

SIGNALS THAT INDICATE A HISTORICAL EVENT GAP:
- Temporal keywords: "what happened", "during", "in August 2024", "historical", "previous", "last time"
- References to past market events: crashes, rallies, corrections, interventions
- Topic coverage note mentions extrapolation from different topics
- Research describes past events qualitatively but lacks quantitative data

SIGNALS THAT DO NOT REQUIRE HISTORICAL DATA:
- Query is about current/forward-looking conditions
- Query is conceptual ("what IS the impact of X")
- Research already contains specific numbers for the historical period asked about

Respond with a JSON object:
{{
    "gap_detected": true/false,
    "event_description": "Brief description of the historical event (or null if no gap)",
    "date_search_query": "Search query to find exact dates (or null)",
    "reasoning": "One sentence explaining why gap detected or not"
}}

Return ONLY the JSON object, no other text."""


INSTRUMENT_MAPPING_PROMPT = """You are identifying which financial instruments would show the market impact of a historical event.

The user asked about this HISTORICAL EVENT:
{event_description}

USER QUERY:
{query}

RESEARCH CONTEXT (current analysis that mentions instruments):
{synthesis}

LOGIC CHAINS (variables mentioned in causal relationships):
{logic_chains}

Your task: Extract instruments from the research context that would also be relevant for the historical event.

LOGIC: If the current research about yen carry trade mentions USDJPY, VIX, BTC, NDX, then those SAME instruments would be relevant for a historical yen carry trade event.

Common instrument mappings:
- USDJPY, dollar yen → USDJPY=X (Yahoo)
- VIX, volatility → ^VIX (Yahoo)
- BTC, bitcoin → BTC-USD (Yahoo)
- S&P 500, SPX → ^GSPC (Yahoo)
- Nasdaq, NDX → ^IXIC or QQQ (Yahoo)
- DXY, dollar index → DX-Y.NYB (Yahoo)
- Gold → GC=F (Yahoo)
- 10Y Treasury → ^TNX (Yahoo)
- TGA, Treasury General Account → WTREGEN (FRED)

Return a JSON object with instruments found in the research:
{{
    "instruments": [
        {{"ticker": "USDJPY=X", "source": "Yahoo", "role": "Yen exchange rate"}},
        {{"ticker": "^VIX", "source": "Yahoo", "role": "Volatility index"}},
        {{"ticker": "BTC-USD", "source": "Yahoo", "role": "Bitcoin price"}}
    ]
}}

IMPORTANT:
- Only include instruments that are MENTIONED in the research context or logic chains
- Map them to correct Yahoo/FRED tickers
- Maximum 6 instruments
- Always include BTC-USD if the query is about BTC impact

Return ONLY the JSON object, no other text."""


DATE_EXTRACTION_PROMPT = """Extract the date range for a historical market event from these web search results.

EVENT: {event_description}

SEARCH RESULTS:
{search_results}

Your task: Identify the START and END dates of this market event based on the search results.

Guidelines:
- Start date: When the event began or market stress started
- End date: When initial volatility subsided (typically 2-4 weeks after peak stress)
- Add a few days buffer on each side if dates are approximate
- For crashes: start just before the crash, end after the recovery begins

Respond with a JSON object:
{{
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "peak_date": "YYYY-MM-DD or null if unclear",
    "confidence": "high/medium/low",
    "reasoning": "Brief explanation of date selection"
}}

Return ONLY the JSON object, no other text."""


def format_logic_chains_for_prompt(logic_chains: list) -> str:
    """Format logic chains for inclusion in prompts."""
    if not logic_chains:
        return "(No logic chains available)"

    lines = []
    for i, chain in enumerate(logic_chains[:10], 1):  # Limit to 10 chains
        # Handle parsed chains from Stage 1 answer text
        if chain.get("chain_text"):
            chain_text = chain["chain_text"]
            source = chain.get("source", "")
            if source:
                lines.append(f"{i}. {chain_text} [Source: {source}]")
            else:
                lines.append(f"{i}. {chain_text}")
        # Handle pre-indexed chains from chunk metadata
        elif chain.get("steps"):
            steps = chain.get("steps", [])
            step_texts = []
            for step in steps:
                cause = step.get("cause", "?")
                effect = step.get("effect", "?")
                step_texts.append(f"{cause} -> {effect}")
            if step_texts:
                source = chain.get("source", "")
                chain_str = " -> ".join(step_texts)
                if source:
                    lines.append(f"{i}. {chain_str} [Source: {source}]")
                else:
                    lines.append(f"{i}. {chain_str}")

    return "\n".join(lines) if lines else "(No logic chains available)"
