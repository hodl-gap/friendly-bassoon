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

## CATEGORIES TO EVALUATE

1. **Historical precedent depth**
   - COVERED: Multiple (≥2) similar historical episodes with specific outcomes (e.g., "Sep 2022: -32%, Oct 2023: -28%")
   - GAP: Only 1 example, or no specific outcome numbers, or examples are for DIFFERENT event types

2. **Quantified relationships**
   - COVERED: Specific correlation coefficients or measured relationships (e.g., "BTC-equity correlation 0.26")
   - GAP: Only qualitative descriptions like "BTC correlates with equities"

3. **Monitoring thresholds**
   - COVERED: Specific price levels from analyst research (e.g., "BofA targets 145-155 range")
   - GAP: Only current prices mentioned, no analyst targets or key levels identified

4. **Event calendar**
   - COVERED: Specific upcoming dates (e.g., "Feb 8 election", "Jan 24 BOJ meeting")
   - GAP: No dated upcoming events that could affect timing

5. **Mechanism conditions**
   - COVERED: Specific preconditions for mechanism to work (e.g., "intervention alone insufficient without hawkish BoJ")
   - GAP: Mechanism described but preconditions not specified

6. **Exit criteria**
   - COVERED: Specific conditions that would end the thesis (e.g., "pressure persists until yen stabilizes below 150")
   - GAP: No clear end conditions specified

---

Respond in this EXACT JSON format:
```json
{{
  "coverage_rating": "COMPLETE|PARTIAL|INSUFFICIENT",
  "gaps": [
    {{
      "category": "historical_precedent_depth|quantified_relationships|monitoring_thresholds|event_calendar|mechanism_conditions|exit_criteria",
      "status": "COVERED|GAP",
      "found": "what was found (be specific)",
      "missing": "what specific information would fill this gap (null if COVERED)",
      "search_query": "suggested web search query to fill gap (null if COVERED)"
    }}
  ],
  "gap_count": 0
}}
```

Rules:
- coverage_rating: COMPLETE (0 gaps), PARTIAL (1-3 gaps), INSUFFICIENT (4+ gaps)
- gap_count must match the number of items with status=GAP
- search_query must be a single-topic search engine query (5-12 words). Focus on the MOST important missing piece. Do NOT combine multiple topics into one query.
  GOOD: "FOMC meeting schedule 2026"
  GOOD: "BOJ monetary policy meeting dates 2026"
  BAD: "BOJ meeting schedule 2026 FOMC dates January February" (two topics combined)
"""
