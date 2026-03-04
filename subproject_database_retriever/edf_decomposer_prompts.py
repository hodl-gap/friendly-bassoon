"""Prompts for EDF (Epistemic Decomposition Framework) query decomposition.

Phase 0 of the retrieval pipeline: an Opus call that decomposes a research query
into a structured knowledge tree across 7 knowledge dimensions.
"""

EDF_DECOMPOSITION_PROMPT = """You are a research decomposition engine for a macro-focused hedge fund.

Decompose this research query into its constituent knowledge requirements using the Epistemic Decomposition Framework (EDF). Produce a structured "knowledge tree" that defines what a thorough researcher would need to find.

## Query Type Classification

Before decomposing, classify the query:
- **actor-driven** (geopolitical, policy, regulatory events where human decisions drive outcomes): weight all 7 types, especially types 2-5
- **data-driven** (indicator readings, positioning, market structure where aggregate dynamics matter): weight types 1, 3, 6, 7 heavily; types 2, 4 only if a specific institutional actor is relevant (e.g., Fed for rates queries)
- **hybrid**: weight based on whether the forward path depends on actor decisions or system dynamics

Include the classification in your output as a top-level "query_type" field.

## The 7 Knowledge Types

| # | Type | Core Question |
|---|------|---------------|
| 1 | factual_specifics | What exactly is this? Numbers, dates, scope, legal citations |
| 2 | actor_knowledge | Who are the key people/institutions? What drives their behavior? |
| 3 | structural_knowledge | How does the system work — and where does it break? |
| 4 | behavioral_precedent | What have these actors done before in similar situations? |
| 5 | reaction_space | What could happen next? What constrains or forces the outcomes? |
| 6 | historical_analogs | When has something similar happened before? What were outcomes? |
| 7 | impact_channels | Through what specific mechanisms — obvious AND hidden — does this affect the target? |

Types 2-5 are the dimensions that distinguish deep analysis from shallow analysis. They capture the human and institutional dynamics that determine how events unfold. For actor-driven queries, do NOT skip them. For data-driven queries, include them only where a specific actor's decisions matter.

### Sub-Questions to Consider Within Each Type

**actor_knowledge (2)** — beyond "who and what role":
- What non-rational forces constrain actor behavior? (ideology, theology, lobby capture, institutional inertia, domestic political lock-in)
- What are the unstated or secondary strategic objectives beyond the declared ones?
- What happens if a key actor is eliminated, incapacitated, or replaced? (succession, command fragmentation, loss of negotiating counterparty)

**structural_knowledge (3)** — beyond "how does it work":
- Where are the non-linear thresholds or tipping points where system behavior changes discontinuously? (storage capacity cliffs, margin call cascades, treaty trigger points)
- What else transits the same infrastructure? (adjacent commodities, co-located supply chains — a chokepoint carries more than the obvious thing)

**reaction_space (5)** — beyond "what could happen next":
- Does the action actually achieve its stated objective? If not, what is the structural impasse?
- If an actor's primary capability is degraded, what alternative domains might they pivot to? (military → cyber, conventional → asymmetric, economic → political)
- What feedback loops constrain the event's own duration or intensity? (public opinion, fiscal cost, coalition fracture, humanitarian consequences → political pressure → forced de-escalation)
- What external political constraints bound the scenario space? (polls, elections, legislative requirements, allied support)

**impact_channels (7)** — beyond the obvious transmission:
- Can a secondary effect become an independent sustaining cause? (insurance withdrawal sustains blockade without military action; freight surcharges persist after conflict resolution)
- What is the fiscal/budgetary cost of the event itself, and how does that cost transmit to markets independently?
- What adjacent or hidden transmission channels exist beyond the obvious one? (oil is obvious; fertilizer, LNG, semiconductor energy costs are not)
- What are the lag structures? Which channels hit immediately vs. with months of delay?

## Priority Levels

| Priority | Definition |
|----------|------------|
| ESSENTIAL | Must know this to answer competently. Missing = analysis has a hole |
| IMPORTANT | Significantly improves quality. Missing = analysis is shallow |
| SUPPLEMENTARY | Adds depth and nuance. Missing = adequate but not exceptional |

## Source Hints

Each item should specify where you'd expect to find this information:
- **research_db**: Reasoning, interpretation, causal mechanisms, analyst frameworks (search vector database). The research DB contains logic chains from institutional analysts — use it for HOW things connect, WHY things happen, and WHAT mechanisms drive outcomes. NEVER use research_db as source_hint for specific data points (numbers, dates, dollar amounts, percentage moves) — those must come from web_search or data_api.
- **web_search**: Verifiable facts, news, government sites, legal databases, specific data points (search the web). This is the ground truth source for factual_specifics items.
- **data_api**: Market data, price series, economic indicators (fetch from data APIs). Use for quantitative data that needs computation (returns, correlations, levels).
- **parametric**: General knowledge the LLM already knows (no retrieval needed). Use for well-established frameworks, constitutional mechanics, basic economic theory.

## Instructions

1. Extract 3-5 core keywords/concepts from the query. Include:
   - The policy instrument or event (what happened)
   - The catalyst (why now)
   - The actor + reaction space (what happens next)
   - The target (what we're assessing impact on)
   - Implied concepts the query doesn't name but requires understanding

2. For each keyword, enumerate knowledge items across relevant types (skip types that genuinely don't apply). Aim for 5-15 items per keyword. Focus on ESSENTIAL items.

3. For each item provide:
   - Concise description of the knowledge needed
   - Priority: ESSENTIAL / IMPORTANT / SUPPLEMENTARY
   - Source hint: research_db / web_search / data_api / parametric
   - A concrete searchable query string (for research_db and web_search items). For data_api items, name the specific ticker/series. For parametric items, you may omit the searchable_query.

4. Avoid duplicate items across keywords. If a concept belongs to multiple keywords, put it under the most relevant one.

## Output Format

Respond with ONLY a JSON object. No markdown code fences, no preamble, no explanation before or after the JSON.

{{
  "query_type": "actor-driven | data-driven | hybrid",
  "keywords": [
    {{
      "id": "K1",
      "keyword": "keyword or concept name",
      "why_extracted": "one sentence explaining why this matters for the query",
      "items": [
        {{
          "id": "T1.01",
          "knowledge_type": "factual_specifics",
          "description": "what needs to be known",
          "priority": "ESSENTIAL",
          "source_hint": "web_search",
          "searchable_query": "concrete search string for retrieval"
        }}
      ]
    }},
    {{
      "id": "K2",
      "keyword": "second keyword",
      "why_extracted": "why this matters",
      "items": [
        {{
          "id": "T2.01",
          "knowledge_type": "behavioral_precedent",
          "description": "what needs to be known",
          "priority": "ESSENTIAL",
          "source_hint": "web_search",
          "searchable_query": "concrete search string"
        }}
      ]
    }}
  ]
}}

Item ID format: T{{keyword_number}}.{{item_number_two_digits}} (e.g., T1.01, T1.02, T2.01, T3.05)

## Query to Decompose

{query}"""


EDF_COVERAGE_ASSESSMENT_PROMPT = """Score the gathered research material against this knowledge tree.

QUERY: {query}

## Knowledge Tree Items to Score

{tree_items}

## Material Gathered

Pinecone chunks ({chunk_count} total):
{chunk_summaries}

Web chains ({web_chain_count} total):
{web_chain_summaries}

Web search facts ({web_search_count} searches):
{web_search_summaries}

## CRITICAL: Source Credibility Rules

The Pinecone database contains logic chains from Telegram-forwarded institutional research. These are POINTERS — they tell you what mechanisms exist, what variables matter, what causal paths to investigate. They are NOT ground truth data sources.

**Pinecone chunks and web chains CAN score Y for:**
- impact_channels (causal mechanisms: A causes B through mechanism C)
- behavioral_precedent (actor patterns: Trump did X, then Y, then Z)
- structural_knowledge (how systems work: Section 122 allows 150-day emergency tariffs)
- reaction_space (scenario frameworks: bull case is X, bear case is Y)
- actor_knowledge (who matters and their roles)

**Pinecone chunks and web chains can ONLY score P (never Y) for:**
- factual_specifics that cite specific numbers, dates, or dollar amounts (e.g., "BoJ sold $1T", "tariff rate 25%", "S&P up 0.69%"). The chain tells you what data points to look for, but the numbers themselves need verification from web search or data API results.
- historical_analogs with specific quantified outcomes (e.g., "market rallied 12% after Bush tariff removal"). The analog identification is valid but the specific market data needs primary source verification.

**Web search results CAN score Y for any item type** — they are primary/verifiable sources.

**Parametric items** can be scored Y if the knowledge is well-established (constitutional mechanics, basic economic frameworks, etc.).

## Scoring

For each item ID:
- **Y** (YES): Covered by appropriate source (see rules above)
- **P** (PARTIAL): Touched on but incompletely, OR covered by Pinecone but needs data verification
- **N** (NO): Not addressed at all

## Rating Rules

- **INSUFFICIENT**: 2+ ESSENTIAL items scored N — must search more
- **ADEQUATE**: 0-1 ESSENTIAL items scored N — proceed to synthesis
- **COMPLETE**: 0 ESSENTIAL items scored N and 0-2 IMPORTANT items scored N

Respond with ONLY a JSON object:
{{
    "rating": "COMPLETE" | "ADEQUATE" | "INSUFFICIENT",
    "scores": {{
        "T1.01": "Y",
        "T1.02": "P",
        "T1.03": "N"
    }},
    "essential_gaps": ["T1.03", "T2.05"],
    "suggested_queries": [
        "concrete search query to fill gap T1.03",
        "concrete search query to fill gap T2.05"
    ]
}}"""
