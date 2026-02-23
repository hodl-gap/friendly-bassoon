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
- Refinement queries must ask for RAW FACTS (dates, levels, schedules, analyst targets), NOT derived analysis. We compute price reactions, correlations, and impacts ourselves.
  GOOD: "BOJ rate hike dates 2023 2024"
  BAD: "BOJ rate hike Bitcoin price reaction" (we compute that ourselves)
- Be strict about relevance - partial matches are NOT filled gaps

Return valid JSON only, no other text."""


# =============================================================================
# LOGIC CHAIN EXTRACTION
# =============================================================================
# For extracting causal logic chains from trusted web sources

EXTRACT_LOGIC_CHAINS_PROMPT = """Extract causal logic chains from these search results.

QUERY: {query}
TOPIC: {topic}

SEARCH RESULTS:
{search_results}

Extract TWO types of chains:

1. MECHANISM chains: Current cause-and-effect relationships (A causes B, which leads to C).
2. PRECEDENT chains: Historical episodes where a similar pattern played out before. Each precedent should be a SEPARATE chain with the specific date/period and what happened.

IMPORTANT for precedents:
- Scan the sources for ALL historical episodes mentioned, not just the most detailed one
- Each distinct historical episode = one separate precedent chain (e.g., 2001 crash, 2008 crisis, 2020 COVID are 3 chains, not 1)
- If a source says "similar to 2008, 2020, and 2022", extract each as its own chain
- Only include precedents that meaningfully existed in the source — do NOT fabricate

Example: If a source about put/call ratio mentions Sept 2022, March 2020, and Nov 2022, return 3 separate precedent chains:
  {{"cause": "September 2022 PCR surge to 99th percentile", "effect": "Dow rallied 20% starting one week later", "chain_type": "precedent", ...}}
  {{"cause": "March 2020 pandemic shock PCR spike above 1.00", "effect": "PCR exceeded 1.00 for first time in 5 years amid COVID crash", "chain_type": "precedent", ...}}
  {{"cause": "November 2022 PCR record 1.46 (7.4 std devs above mean)", "effect": "Unprecedented repeated pessimism spikes over 5 weeks", "chain_type": "precedent", ...}}
Do NOT collapse these into one generic "high PCR historically leads to rallies" mechanism chain.

Return JSON with this structure:

{{
    "chains": [
        {{
            "cause": "The initiating event or condition",
            "effect": "The resulting outcome or impact",
            "mechanism": "How the cause leads to the effect (the why/how)",
            "polarity": "positive|negative|mixed",
            "chain_type": "mechanism|precedent",
            "evidence_quote": "VERBATIM quote from source supporting this chain",
            "source_url": "URL where this chain was found",
            "source_name": "Name of the source (e.g., Goldman Sachs, Bloomberg)",
            "confidence": "high|medium|low"
        }}
    ],
    "summary": "2-3 sentence synthesis of the key causal relationships found",
    "chain_count": 0
}}

Rules:
- Extract ONLY chains with clear cause-effect logic
- chain_type: "mechanism" = current causal relationship, "precedent" = historical episode where similar pattern occurred
- For precedent chains: put the date/period in the cause field (e.g., "September 2008 Lehman collapse")
- polarity: "positive" = cause increases effect, "negative" = cause decreases effect, "mixed" = depends on conditions
- evidence_quote MUST be a VERBATIM quote from the source (copy-paste exact text)
- Keep evidence_quote SHORT (1-2 sentences max, under 200 characters) - just enough to prove the claim
- Do NOT paraphrase or summarize for evidence_quote - it must be the exact words from the source
- confidence: "high" = explicit causal statement, "medium" = implied causation, "low" = speculative
- source_name should be the institution/publication name (e.g., "Goldman Sachs", "Bloomberg")
- source_url should be the URL where this was found (keep it short if possible)
- If no relevant chains found, return empty chains array
- Maximum 5 mechanism chains + up to 3 precedent chains per query (8 total max)

Return valid JSON only, no other text."""
