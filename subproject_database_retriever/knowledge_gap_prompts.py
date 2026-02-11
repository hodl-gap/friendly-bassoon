"""Prompts for knowledge gap detection - topic-agnostic version.

This module is part of the retrieval layer. Gap detection prompts are
designed to work for ANY query topic, not just BTC-specific queries.
"""

SYSTEM_PROMPT = """You are an analyst assessing whether retrieved research provides sufficient information to answer the user's query comprehensively.

Your task is to evaluate the retrieved context against knowledge categories and identify specific gaps that could be filled with additional research.

IMPORTANT: You are topic-agnostic. Do NOT assume the query is about any specific topic like Bitcoin, crypto, or any particular market. Evaluate based on the ACTUAL query provided."""


GAP_DETECTION_PROMPT = """## USER QUERY
{query}

## RETRIEVED SYNTHESIS
{synthesis}

## RETRIEVED LOGIC CHAINS
{chains_text}

## TOPIC COVERAGE ANALYSIS
{topic_coverage_text}

---

Evaluate the retrieved information against these knowledge categories. For each category, determine if it's COVERED or a GAP.

**IMPORTANT**: Be STRICT about what counts as "covered":
- COVERED = specific, concrete information exists (numbers, dates, named sources)
- GAP = only vague/general information, or completely missing

**CRITICAL**: We have Yahoo Finance, FRED, and CoinGecko data adapters. We CAN compute correlations, drawdowns, and price changes ourselves from price data. Do NOT ask web search for things we can calculate. Each gap must specify `fill_method`:
- `"web_chain_extraction"` = topic not covered in DB, need to extract logic chains from trusted web sources
- `"web_search"` = facts we cannot compute: dates, announcements, analyst opinions, policy decisions
- `"data_fetch"` = quantitative data we can compute from price/economic series

## CATEGORIES TO EVALUATE

0. **Topic not covered (CRITICAL - evaluate carefully)**
   - COVERED: Synthesis directly ANSWERS the specific question asked (provides the actual triggers, causes, or mechanisms the query is asking about)
   - GAP: Synthesis does NOT answer the question, even if it mentions related topics or timeframes
   - fill_method: `"web_chain_extraction"` — search trusted sources for logic chains on this topic
   - IMPORTANT: Tangentially related content is NOT "covered". If query asks "What caused X?" and synthesis discusses Y (even if Y happened around the same time), that's a GAP.
   - Example: Query asks "What caused the SaaS meltdown?" → Synthesis discusses Fed policy in same timeframe → GAP (Fed policy ≠ SaaS meltdown cause)
   - When gap detected, provide a SPECIFIC search query targeting the actual question (e.g., "SaaS software stock meltdown causes triggers 2026")
   - **INPUT CLAIM VALIDATION**: If the query contains specific data claims (e.g., "Z-score +3", "record reading"), search for corroborating evidence. Example: Query claims "indicator X shows record reading" → search for corroborating evidence to validate and enrich

1. **Historical precedent depth**
   - COVERED: Multiple (≥2) similar historical episodes with specific dates AND outcomes
   - GAP: Only 1 example, or no specific dates for similar episodes
   - **CRITICAL FOR INDICATOR QUERIES**: If the query mentions a SPECIFIC INDICATOR with an extreme reading (e.g., "VIX at 40", "put/call ratio at 1.5", "AAII bearish at 60%"), the gap should ask: "What happened in PRIOR instances when THIS SAME INDICATOR reached similar extremes?"
   - fill_method: `"historical_analog"` — when query references a specific indicator at extreme level
   - fill_method: `"web_search"` — for generic historical precedent (no specific indicator)
   - For historical_analog: We will fetch price data (SPY, VIX) for prior extreme dates and compute what happened after
   - indicator_name: Name of the indicator (e.g., "VIX", "put/call ratio")
   - Example: Query says "VIX at 40" → GAP should be "What happened after prior VIX spikes to 40+?" with fill_method="historical_analog"

2. **Quantified relationships**
   - COVERED: Specific correlation coefficients or measured relationships
   - GAP: Only qualitative descriptions like "X correlates with Y"
   - fill_method: `"data_fetch"` — specify `instruments` using ONLY these known variable names:
     * Indices: spy, qqq, sp500, nasdaq, dow, russell2000
     * Sectors: igv (software), xlk (tech), smh/soxx (semis), xlf (financials), xle (energy)
     * Stocks: googl, amzn, msft, meta, aapl, nvda, orcl
     * FX/Crypto: btc, eth, dxy, usdjpy, eurusd
     * Volatility: vix, vvix
     * Rates: tlt, gld, gold
   - IMPORTANT: Only use data_fetch for PUBLIC data (Yahoo/FRED). Proprietary data (hedge fund positioning, prime broker data) must use web_search instead.

3. **Monitoring thresholds**
   - COVERED: Specific levels from analyst research (e.g., "analysts target X range")
   - GAP: Only current values mentioned, no analyst targets or key levels identified
   - fill_method: `"web_search"` — analyst targets are opinions, not in price data
   - search_query should name the specific instrument and ask for analyst targets/forecasts

4. **Event calendar**
   - COVERED: Specific upcoming dates (e.g., "Feb 8 meeting", "Jan 24 decision")
   - GAP: No dated upcoming events that could affect timing
   - fill_method: `"web_search"` — meeting schedules are not in price data

5. **Mechanism conditions**
   - COVERED: Specific preconditions for mechanism to work
   - GAP: Mechanism described but preconditions not specified
   - fill_method: `"web_search"` — qualitative expert analysis

6. **Exit criteria**
   - COVERED: Specific conditions that would end the thesis
   - GAP: No clear end conditions specified
   - fill_method: `"web_search"` — qualitative expert analysis

---

Respond in this EXACT JSON format:
```json
{{
  "coverage_rating": "COMPLETE|PARTIAL|INSUFFICIENT",
  "gaps": [
    {{
      "category": "topic_not_covered|historical_precedent_depth|quantified_relationships|monitoring_thresholds|event_calendar|mechanism_conditions|exit_criteria",
      "status": "COVERED|GAP",
      "fill_method": "web_chain_extraction|web_search|data_fetch|historical_analog",
      "found": "what was found (be specific)",
      "missing": "what specific information would fill this gap (null if COVERED)",
      "search_query": "web search query (null if COVERED or if fill_method is data_fetch/historical_analog)",
      "instruments": ["var1", "var2"],
      "indicator_name": "name of specific indicator for historical_analog (null otherwise)"
    }}
  ],
  "gap_count": 0
}}
```

## Examples
<!-- [FEW-SHOT v1] Source: run_20260211_075133 (RDE) + run_20260211_081110 (JPY Rally). Review & improve — add COMPLETE and INSUFFICIENT examples. -->

### Example 1: Simple query — broad taxonomy, 4 COVERED / 3 GAP

Query: "What does rising RDE indicate about liquidity conditions?"

```json
{{
  "coverage_rating": "PARTIAL",
  "gap_count": 3,
  "gaps": [
    {{"category": "topic_not_covered", "status": "COVERED", "found": "Synthesis directly answers the query with multiple causal chains for rising RDE → liquidity stress.", "missing": null, "fill_method": "web_chain_extraction", "search_query": null, "instruments": null, "indicator_name": null}},
    {{"category": "historical_precedent_depth", "status": "GAP", "found": "Mentions 2008, 2020, 2023 crises but no specific dates or detailed outcomes.", "missing": "Specific dates and Primary Credit levels during 2008, 2020, 2023 crises.", "fill_method": "historical_analog", "search_query": null, "instruments": null, "indicator_name": "Primary Credit"}},
    {{"category": "quantified_relationships", "status": "GAP", "found": "Directional relationships only, no correlation coefficients.", "missing": "Correlation between Primary Credit usage and market drawdowns.", "fill_method": "data_fetch", "search_query": null, "instruments": ["spy", "qqq", "vix"], "indicator_name": null}},
    {{"category": "monitoring_thresholds", "status": "COVERED", "found": "Thresholds specified: Primary Credit $50B+ crisis, overnight repo >$25B, bank reserves $3T.", "missing": null, "fill_method": "web_search", "search_query": null, "instruments": null, "indicator_name": null}},
    {{"category": "event_calendar", "status": "GAP", "found": "No upcoming dated events.", "missing": "Upcoming Fed meetings affecting Primary Credit demand.", "fill_method": "web_search", "search_query": "Fed FOMC meeting schedule 2025 policy decisions", "instruments": null, "indicator_name": null}},
    {{"category": "mechanism_conditions", "status": "COVERED", "found": "Preconditions specified: TGA drawdown, RRP depletion, T-bill issuance surges.", "missing": null, "fill_method": "web_search", "search_query": null, "instruments": null, "indicator_name": null}},
    {{"category": "exit_criteria", "status": "COVERED", "found": "Bank reserves rebound to $3T+ resolves stress.", "missing": null, "fill_method": "web_search", "search_query": null, "instruments": null, "indicator_name": null}}
  ],
  "gap_count": 3
}}
```

### Example 2: Event query with data claim — validates specific claim + computes correlation

Query: "On 2026-01-24, JPY/USD rallied to 155.90 rising 1.6% daily, and Japan finance minister warned speculators. What is the BTC impact?"

```json
{{
  "coverage_rating": "PARTIAL",
  "gap_count": 3,
  "gaps": [
    {{"category": "topic_not_covered", "status": "GAP", "found": "Synthesis provides BTC downward pressure thesis but does not validate the specific claim that JPY/USD rallied 1.6% to 155.90 on 2026-01-24.", "missing": "Corroborating evidence for the 2026-01-24 JPY/USD rally and finance minister warning.", "fill_method": "web_search", "search_query": "JPY USD 155.90 January 24 2026 Japan finance minister warning", "instruments": null, "indicator_name": null}},
    {{"category": "quantified_relationships", "status": "GAP", "found": "Historical BTC drawdowns of 20-30% during BOJ tightening mentioned but no measured USDJPY-BTC correlation.", "missing": "Correlation coefficient between USDJPY and BTC price changes.", "fill_method": "data_fetch", "search_query": null, "instruments": ["usdjpy", "btc"], "indicator_name": null}},
    {{"category": "event_calendar", "status": "GAP", "found": "BOJ rate hike identified as key trigger but no scheduled date.", "missing": "Next BOJ monetary policy decision date.", "fill_method": "web_search", "search_query": "BOJ monetary policy decision date January 2026 rate hike schedule", "instruments": null, "indicator_name": null}}
  ],
  "gap_count": 3
}}
```

---

Rules:
- coverage_rating: COMPLETE (0 gaps), PARTIAL (1-3 gaps), INSUFFICIENT (4+ gaps)
- gap_count must match the number of items with status=GAP
- fill_method: Use "web_chain_extraction" for topic_not_covered gaps
- fill_method: Use "data_fetch" for quantified_relationships
- fill_method: Use "historical_analog" for historical_precedent_depth when query mentions a SPECIFIC INDICATOR at extreme level
- fill_method: Use "web_search" for all others
- search_query: only for web_search/web_chain_extraction gaps. Must be a single-topic query (5-12 words) asking for RAW FACTS
- instruments: only for data_fetch gaps. List of normalized variable names to fetch
- indicator_name: only for historical_analog gaps. The specific indicator mentioned in query (e.g., "VIX", "put/call ratio")
- IMPORTANT: Keep "found" and "missing" fields BRIEF (1-2 sentences max, under 50 words each)
"""


EXTRACT_EXTREME_DATES_PROMPT = """You are given web search snippets about a financial indicator. Extract prior dates when this indicator reached extreme levels.

## INDICATOR
{indicator_name}

## SEARCH SNIPPETS
{snippets}

---

Extract dates when "{indicator_name}" reached extreme or notable levels. For each episode, provide:
- **date**: Best estimate in YYYY-MM-DD format (use first of month if only month known)
- **value**: The indicator reading if mentioned (e.g., "+2.5", "40", "1.5"), or "extreme" if value not specified
- **label**: Short description of the episode (e.g., "COVID crash", "2022 bear market")

Respond in this EXACT JSON format:
```json
{{
  "dates": [
    {{"date": "YYYY-MM-DD", "value": "...", "label": "..."}},
    ...
  ],
  "notes": "Any caveats about date accuracy"
}}
```

Rules:
- Only include episodes where the indicator actually reached an extreme (not normal readings)
- Maximum 8 episodes
- Order chronologically (oldest first)
- If no extreme dates can be identified from the snippets, return {{"dates": [], "notes": "..."}}
- Prefer specific dates over vague references
"""


EXTRACT_READINGS_FROM_IMAGE_PROMPT = """You are given a chart image of a financial indicator. Extract dates when this indicator reached extreme levels.

## INDICATOR
{indicator_name}

---

Analyze the chart image carefully. Identify dates when "{indicator_name}" reached extreme HIGH readings (spikes, record highs). Only extract peaks/spikes — do NOT include troughs or extreme lows. For each episode, provide:
- **date**: Best estimate in YYYY-MM-DD format (use first of month if only month known)
- **value**: The indicator reading if visible (e.g., "+2.5", "40", "1.5"), or "extreme" if value not clear
- **label**: Short description of the episode (e.g., "COVID crash", "2022 bear market")

Respond in this EXACT JSON format:
```json
{{
  "dates": [
    {{"date": "YYYY-MM-DD", "value": "...", "label": "..."}},
    ...
  ],
  "notes": "Any caveats about date accuracy"
}}
```

Rules:
- Only include episodes where the indicator reached an extreme HIGH (not normal readings, not lows/troughs)
- Do NOT include negative extremes or troughs — we only want the same-direction extremes as the current reading
- Maximum 8 episodes
- Order chronologically (oldest first)
- If no extreme dates can be identified from the chart, return {{"dates": [], "notes": "..."}}
- Prefer specific dates over vague references
- Read axis labels, annotations, and any text on the chart carefully
"""


INTERPRET_EVENT_STUDY_PROMPT = """You are given return data around dates when a financial indicator reached extreme levels. Classify each episode's outcome and identify the dominant pattern.

## INDICATOR
{indicator_name}

## CONTEXT
{gap_context}

## EPISODE DATA
{episodes_table}

---

For each episode, classify the market outcome based on the return data. Use descriptive labels like:
- "rally" (strong positive returns)
- "selloff" (significant negative returns)
- "squeeze" (sharp reversal higher, especially with VIX crush)
- "sideways" (minimal movement)
- "volatile" (large moves in both directions)
- Or any other appropriate label based on the data

Then identify the dominant pattern across all episodes.

Respond in this EXACT JSON format:
```json
{{
  "episode_outcomes": [
    {{"label": "...", "date": "YYYY-MM-DD", "outcome": "rally|selloff|squeeze|sideways|volatile|...","reasoning": "brief explanation"}},
    ...
  ],
  "dominant_pattern": "most common outcome label",
  "pattern_probability": 0.0-1.0,
  "pattern_summary": "1-2 sentence summary of the historical pattern",
  "interpretation": "2-3 sentence interpretation of what this means for the current reading"
}}
```

Rules:
- Base classifications ONLY on the return data provided, not assumptions
- pattern_probability = count of dominant_pattern / total episodes
- Keep reasoning brief (under 20 words per episode)
- interpretation should reference the specific indicator name
"""
