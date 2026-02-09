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

1. **Historical precedent depth**
   - COVERED: Multiple (≥2) similar historical episodes with specific dates
   - GAP: Only 1 example, or no specific dates for similar episodes
   - fill_method: `"web_search"` — search for EVENT DATES only. We compute price reactions ourselves.
   - GOOD search_query: "event X dates 2022 2023 2024"
   - BAD search_query: "event X price impact 2022" (we compute impact ourselves)

2. **Quantified relationships**
   - COVERED: Specific correlation coefficients or measured relationships
   - GAP: Only qualitative descriptions like "X correlates with Y"
   - fill_method: `"data_fetch"` — specify `instruments` (variable names) and we fetch data and compute correlation ourselves

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
- fill_method: Use "web_chain_extraction" for topic_not_covered gaps
- fill_method: Use "data_fetch" for quantified_relationships
- fill_method: Use "web_search" for all others
- search_query: only for web_search/web_chain_extraction gaps. Must be a single-topic query (5-12 words) asking for RAW FACTS
- instruments: only for data_fetch gaps. List of normalized variable names to fetch
- IMPORTANT: Keep "found" and "missing" fields BRIEF (1-2 sentences max, under 50 words each)
"""
