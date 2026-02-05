"""
Web Search Extraction Prompts

Prompts for extracting structured data from web search results.
Used by web_search_adapter.py.
"""

# =============================================================================
# DATA POINTS EXTRACTION
# =============================================================================
# For extracting quantitative data (numbers, percentages, rates, dates)

EXTRACT_DATA_POINTS_PROMPT = """Extract quantitative data points from these search results.

QUERY: {query}

SEARCH RESULTS:
{search_results}

Extract ALL relevant numbers, percentages, rates, and dated values.
Return JSON with this structure:

{{
    "data_points": [
        {{
            "metric": "description of what this number represents",
            "value": "the number/percentage/rate",
            "unit": "unit if applicable (%, bps, trillion, etc.)",
            "date": "date or time period if mentioned",
            "source": "which search result this came from (title or URL)",
            "confidence": "high/medium/low based on source reliability"
        }}
    ],
    "summary": "one sentence summary of the key finding",
    "data_freshness": "most recent date mentioned in results"
}}

Rules:
- Extract ONLY factual data points with specific numbers
- Include the source for each data point
- If no relevant data found, return empty data_points array
- Be conservative - only extract clear, unambiguous numbers

Return valid JSON only, no other text."""


# =============================================================================
# ANNOUNCEMENTS EXTRACTION
# =============================================================================
# For extracting entity announcements (who announced what, when)

EXTRACT_ANNOUNCEMENTS_PROMPT = """Extract company/institution announcements from these search results.

QUERY: {query}

SEARCH RESULTS:
{search_results}

Extract ALL relevant announcements about plans, decisions, or actions.
Return JSON with this structure:

{{
    "announcements": [
        {{
            "entity": "company or institution name",
            "entity_type": "insurer/bank/fund/central_bank/regulator/other",
            "action": "what they announced or decided",
            "direction": "buy/sell/increase/decrease/hold/neutral",
            "asset_class": "what asset class this relates to",
            "date": "when announced (if mentioned)",
            "source": "which search result this came from",
            "quote": "direct quote if available",
            "confidence": "high/medium/low"
        }}
    ],
    "summary": "one sentence summary of the key finding",
    "announcement_freshness": "most recent announcement date"
}}

Rules:
- Focus on CONCRETE announcements, not speculation
- Include direct quotes when available
- Entity names should be specific (e.g., "Fukoku Mutual Life Insurance" not just "Japanese insurer")
- If no relevant announcements found, return empty announcements array
- Confidence: high = direct statement, medium = attributed report, low = rumor/speculation

Return valid JSON only, no other text."""


# =============================================================================
# COMBINED CONTEXT EXTRACTION (for more complex queries)
# =============================================================================

EXTRACT_FULL_CONTEXT_PROMPT = """Extract both quantitative data AND announcements from these search results.

QUERY: {query}

SEARCH RESULTS:
{search_results}

Return JSON with this structure:

{{
    "data_points": [
        {{
            "metric": "description",
            "value": "number",
            "unit": "unit",
            "date": "date",
            "source": "source"
        }}
    ],
    "announcements": [
        {{
            "entity": "name",
            "action": "what they announced",
            "direction": "buy/sell/etc",
            "date": "when",
            "source": "source"
        }}
    ],
    "causal_links": [
        {{
            "cause": "what's causing something",
            "effect": "what's being caused",
            "evidence": "supporting data point or announcement"
        }}
    ],
    "summary": "2-3 sentence summary connecting the dots"
}}

Focus on:
1. Hard numbers and percentages
2. Specific entity announcements
3. Causal relationships between data and actions

Return valid JSON only, no other text."""


# =============================================================================
# KNOWLEDGE GAP EXTRACTION
# =============================================================================
# For filling specific knowledge gaps identified by gap detection

EXTRACT_KNOWLEDGE_GAP_PROMPT = """You are extracting specific information to fill a knowledge gap.

## GAP CATEGORY: {gap_category}
## WHAT WE'RE LOOKING FOR: {missing_description}
## SEARCH QUERY: {query}

## SEARCH RESULTS:
{search_results}

Extract ONLY information that directly addresses the gap. Return JSON:

{{
    "gap_filled": true or false,
    "confidence": 0.0 to 1.0,
    "extracted_facts": [
        {{
            "fact": "specific fact or data point",
            "source": "source URL or name",
            "date": "date if mentioned"
        }}
    ],
    "summary": "One sentence summary of what was found",
    "suggested_refinement": "A single short search query (5-10 words) to try next, or null"
}}

Rules:
- Set gap_filled=true ONLY if you found information that DIRECTLY addresses what's missing
- confidence: 0.8+ if found exact data, 0.5-0.8 if found related info, below 0.5 if weak/indirect
- If no relevant information found, set gap_filled=false and suggest a refined query
- suggested_refinement MUST be a single short search engine query (5-10 words). NOT instructions, NOT multiple queries joined with OR, NOT advice. Just a query string that can be pasted directly into a search engine.
  GOOD: "FOMC meeting schedule 2026"
  BAD: "Search for 'FOMC schedule 2026' and 'BOJ dates 2026' separately"
  BAD: "Bitcoin SOFR correlation OR carry trade sensitivity OR BTC drawdown analysis"
- The refined query should try a different angle (different keywords, narrower scope, one topic)
- Be strict about relevance - partial matches are NOT filled gaps

Return valid JSON only, no other text."""
