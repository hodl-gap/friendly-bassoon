"""Prompts for knowledge gap detection."""

SYSTEM_PROMPT = """You are an analyst assessing whether retrieved research provides sufficient information for a BTC impact analysis.

Your task is to evaluate the retrieved context against 6 knowledge categories and identify specific gaps that could be filled with additional research."""


GAP_DETECTION_PROMPT = """## USER QUERY
{query}

## RETRIEVED SYNTHESIS
{synthesis}

## RETRIEVED LOGIC CHAINS
{chains_text}

## CURRENT MARKET DATA
{current_values_text}

---

Evaluate the retrieved information against these 6 knowledge categories. For each category, determine if it's COVERED or a GAP.

**IMPORTANT**: Be STRICT about what counts as "covered":
- COVERED = specific, concrete information exists (numbers, dates, named sources)
- GAP = only vague/general information, or completely missing

**CRITICAL**: We have Yahoo Finance, FRED, and CoinGecko data adapters. We CAN compute correlations, drawdowns, and price changes ourselves from price data. Do NOT ask web search for things we can calculate. Each gap must specify `fill_method`:
- `"web_search"` = facts we cannot compute: dates, announcements, analyst opinions, policy decisions
- `"data_fetch"` = quantitative data we can compute from price/economic series

## CATEGORIES TO EVALUATE

0. **Topic not covered**
   - COVERED: Query topic explicitly discussed in synthesis/chains (e.g., query about "AI CAPEX" finds "AI CAPEX" mentioned)
   - GAP: Query topic NOT mentioned at all in synthesis - database has no relevant research on this topic
   - fill_method: `"web_chain_extraction"` — search trusted sources for logic chains on this topic
   - search_query should be the query topic + relevant context (e.g., "AI CAPEX impact tech stocks investment banks analysis")
   - ONLY mark as GAP if the topic is completely absent from synthesis (not just partially covered)

1. **Historical precedent depth**
   - COVERED: Multiple (≥2) similar historical episodes with specific dates
   - GAP: Only 1 example, or no specific dates for similar episodes
   - fill_method: `"web_search"` — search for EVENT DATES only (e.g., "when did BOJ hike rates?"). We compute BTC price reaction ourselves from those dates. Do NOT search for "BTC impact" or "Bitcoin price reaction" — that's our job.
   - GOOD search_query: "BOJ rate hike dates 2022 2023 2024"
   - BAD search_query: "BOJ rate hike Bitcoin price impact 2022" (we compute impact ourselves)

2. **Quantified relationships**
   - COVERED: Specific correlation coefficients or measured relationships (e.g., "BTC-equity correlation 0.26")
   - GAP: Only qualitative descriptions like "BTC correlates with equities"
   - fill_method: `"data_fetch"` — specify `instruments` (variable names like "btc", "usdjpy", "sofr", "dxy", "sp500", "gold", "vix", "us10y") and we fetch price data and compute correlation ourselves. No web search needed.

3. **Monitoring thresholds**
   - COVERED: Specific price levels from analyst research (e.g., "BofA targets 145-155 range")
   - GAP: Only current prices mentioned, no analyst targets or key levels identified
   - fill_method: `"web_search"` — analyst targets are opinions, not in price data
   - search_query should name the specific instrument and ask for analyst targets/forecasts
   - GOOD: "Goldman Sachs USD JPY forecast 2026"
   - GOOD: "analyst Bitcoin price target carry trade scenario"
   - BAD: "USD JPY intervention threshold 2024 2025 analyst targets" (too many years, too vague)

4. **Event calendar**
   - COVERED: Specific upcoming dates (e.g., "Feb 8 election", "Jan 24 BOJ meeting")
   - GAP: No dated upcoming events that could affect timing
   - fill_method: `"web_search"` — meeting schedules are not in price data

5. **Mechanism conditions**
   - COVERED: Specific preconditions for mechanism to work (e.g., "intervention alone insufficient without hawkish BoJ")
   - GAP: Mechanism described but preconditions not specified
   - fill_method: `"web_search"` — qualitative expert analysis

6. **Exit criteria**
   - COVERED: Specific conditions that would end the thesis (e.g., "pressure persists until yen stabilizes below 150")
   - GAP: No clear end conditions specified
   - fill_method: `"web_search"` — qualitative expert analysis
   - search_query should target the specific thesis resolution, not general policy outlook
   - GOOD: "carry trade unwind resolution conditions historical"
   - GOOD: "yen stabilization level after intervention historical"
   - BAD: "BOJ easing expectations timeline 2026" (too general, asks about policy not thesis exit)

---

Respond in this EXACT JSON format:
```json
{{
  "coverage_rating": "COMPLETE|PARTIAL|INSUFFICIENT",
  "gaps": [
    {{
      "category": "topic_not_covered|historical_precedent_depth|quantified_relationships|monitoring_thresholds|event_calendar|mechanism_conditions|exit_criteria",
      "status": "COVERED|GAP",
      "fill_method": "web_chain_extraction|web_search|data_fetch",
      "found": "what was found (be specific)",
      "missing": "what specific information would fill this gap (null if COVERED)",
      "search_query": "web search query (null if COVERED or if fill_method is data_fetch)",
      "instruments": ["var1", "var2"]
    }}
  ],
  "gap_count": 0
}}
```

Rules:
- coverage_rating: COMPLETE (0 gaps), PARTIAL (1-3 gaps), INSUFFICIENT (4+ gaps)
- gap_count must match the number of items with status=GAP
- fill_method: Use "web_chain_extraction" for topic_not_covered gaps (extracts logic chains from trusted sources)
- fill_method is REQUIRED for every GAP. Use "data_fetch" for quantified_relationships. Use "web_search" for all others.
- search_query: only for web_search gaps. Must be a single-topic query (5-12 words) asking for RAW FACTS (dates, schedules, analyst targets), NOT derived analysis.
- instruments: only for data_fetch gaps. List of normalized variable names (e.g., ["btc", "usdjpy"]) to fetch and compute correlation from.
"""
