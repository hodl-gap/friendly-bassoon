"""
Prompts for extracting interview/meeting data
"""

from metrics_mapping_utils import load_metrics_mapping


def get_interview_extraction_prompt(messages_batch, channel_name, metrics_mapping_text=None):
    """Prompt for extracting structured data from interview/meeting messages with opinion grouping"""

    # Load metrics mapping if not provided
    if metrics_mapping_text is None:
        metrics_mapping_text = load_metrics_mapping()

    prompt = f"""You are extracting structured information from Fed official statements, FOMC minutes, or central bank meeting summaries.

**Channel**: {channel_name}

**Your task has TWO parts:**
1. Identify which messages belong to the same "meeting/interview summary"
2. Extract structured data from each message

**Messages to analyze:**

"""

    for i, msg in enumerate(messages_batch, 1):
        prompt += f"\n--- Message {i} ---\n"
        prompt += f"Date: {msg['date']}\n"
        prompt += f"Text: {msg['text']}\n"
        if msg.get('photo'):
            prompt += f"Has photo: Yes\n"
        prompt += "\n"

    prompt += """
**PART 1: Opinion Grouping**
Messages about the same meeting/event sent close together should get the same opinion_id.
Format: `{channel_name}_N` where N increments for each new opinion/article.

**PART 2: Data Extraction**

**CRITICAL: CONCISE OUTPUT RULE**
All text fields must be CONCISE and RETRIEVAL-OPTIMIZED:
- NO full sentences - use comma-separated phrases or key terms
- NO filler words - be direct and brief
- PRESERVE all meaningful data (numbers, thresholds, conditions)
- Format: "key point, key point" or "metric: value"

For EACH message, extract structured information about who said what.

**Output format (JSON array, one entry per message):**
```json
[
    {{
        "message_index": 1,
        "opinion_id": "{channel_name}_1",
        "meeting_type": "Fed speech" | "FOMC minutes" | "Fed meeting" | "CB meeting",
        "date": "YYYY-MM-DD",
        "participants": [
            {{
                "name": "Williams",
                "title": "NY Fed President",
                "stance": "dovish" | "hawkish" | "neutral" | "",
                "statements": [
                    {{
                        "topic": "labor" | "inflation" | "rates" | "policy tool" | "financial stability" | "other",
                        "data_mentioned": "NFP 3mo avg: 62k, unemployment: 4.1%",
                        "view": "labor cooling, disinflation on track",
                        "policy_implication": "rate cut support" | "rate hold" | "rate hike" | "",
                        "tags": "direct_liquidity|indirect_liquidity|irrelevant",
                        "topic_tags": ["US", "central_bank", "macro_data"]
                    }}
                ]
            }}
        ],
        "topic_tags": ["US", "central_bank", "rates"],
        "liquidity_metrics": [
            {{
                "raw": "RDE",
                "normalized": "RDE",
                "value": "-0.2",
                "direction": "up",
                "is_new": true,
                "suggested_category": "direct",
                "suggested_description": "Reserve Demand Elasticity",
                "suggested_cluster": "Fed_balance_sheet"
            }}
        ],
        "logic_chains": [
            {{
                "steps": [
                    {{"cause": "labor market cooling", "cause_normalized": "labor_market", "effect": "wage pressure easing", "effect_normalized": "wage_pressure", "mechanism": "fewer job openings reduce worker bargaining power", "conditional_on": "", "evidence_quote": "The labor market has been cooling, with job openings declining significantly", "polarity": "BEARISH"}},
                    {{"cause": "wage pressure easing", "cause_normalized": "wage_pressure", "effect": "inflation decline", "effect_normalized": "inflation", "mechanism": "lower wage growth reduces service inflation", "conditional_on": "no tariff-driven cost-push inflation", "evidence_quote": "This should help bring down service sector inflation over time", "polarity": "BULLISH"}}
                ]
            }}
        ],
        "temporal_context": {{
            "policy_regime": "QT",
            "liquidity_regime": "reserve_scarce",
            "valid_from": "2022-06",
            "valid_until": null,
            "is_forward_looking": false
        }}
    }}
]
```

**Important:**
- **CRITICAL: CONCISE OUTPUT** - No full sentences, use short phrases
- **CRITICAL: ALL text in ENGLISH** - Translate Korean/other languages
- Extract ALL participants and ALL their statements
- **Names**: "Williams" NOT "윌리엄스", "Powell" NOT "파월"
- **Titles**: "NY Fed President" NOT "뉴욕 연은 총재"
- **Stance**: "dovish", "hawkish", "neutral" (translate from 비둘기/매파/중립)
- **data_mentioned**: Only specific data points, format "metric: value, metric: value"
  - GOOD: "NFP: 180k, unemployment: 4.1%"
  - BAD: "nonfarm payrolls came in at 180k" (too wordy)
- **view**: Concise summary of their position
  - GOOD: "labor cooling, supports gradual cuts"
  - BAD: "He believes the labor market is cooling down" (too wordy)
- **policy_implication**: Brief policy stance
- **tags**: Liquidity classification
  - "direct_liquidity": Statement about Fed balance sheet, reserves, RRP, QT/QE, funding
  - "indirect_liquidity": Statement about rates/policy affecting liquidity channels
  - "irrelevant": Pure inflation/employment without liquidity angle (use sparingly)
- **topic_tags**: Array of topic tags for discovery (separate from liquidity tags)
  - At statement level: Tags for that statement's topic
  - At message level: Overall tags for the meeting
  - Categories: Asset class (equities, rates, FX, credit, commodities), Region (US, china, japan, europe, korea, EM), Data type (macro_data, earnings, central_bank), Mechanics (positioning, flows, volatility)
  - MUST have 1+ tags at both levels
- Messages about same meeting/event get same opinion_id

**liquidity_metrics field:**

**INCLUDE (only these categories):**
- Fed balance sheet: TGA, RRP, reserves, QE/QT, BTFP, SRF
- Money markets: SOFR, repo rates, fed funds, funding spreads
- Systematic flows: CTA flows/triggers, vol-control, dealer gamma
- Credit/funding: corporate issuance, buybacks, credit spreads (market-wide)
- FX liquidity: DXY, USD funding, carry trade flows
- Rate expectations: Fed cut/hike probability, policy rate path
- ETF/fund flows: aggregate ETF flows, fund manager positioning
- Positioning: HF leverage, margin debt, options positioning (market-wide)

**STRICT EXCLUSIONS (NEVER extract these):**
- Substrate/materials: BT price, ABF demand, T-glass, PCB share, CCL share
- Daily returns: SPY return, QQQ return, individual ETF returns
- Company fundamentals: revenue, net loss, IPO proceeds, PSR, EPS
- Product prices: DRAM, semiconductor, chip prices
- Valuation: P/E, multiples, target prices
- Battery/EV: battery orders, EV volumes
- Political: election probabilities
- Hiring/headcount metrics, M&A deal values
- Company-specific cash burn

**BEFORE MARKING is_new=true, CHECK THE MAPPING TABLE:**
1. Search BOTH "normalized" AND "variants" columns
2. If ANY variant matches your raw text (even partially), use that normalized name
3. Check for semantic equivalents (e.g., "CTA selling" matches "cta_forced_selling")
4. ONLY mark is_new=true if ZERO match in either column

**NAMING CONVENTION for new metrics:**
- Use snake_case: "cta_net_flow" NOT "CTA net flow"
- No values in names: "fed_cut_probability" NOT "Dec cut prob 80%"
- No temporal specifics: "etf_net_flows" NOT "ETF_Nov_inflows"
- Keep under 30 characters

**Structure:**
- "raw": Original text
- "normalized": Standardized name from mapping table (use snake_case for new)
- "value": Specific value, empty if none
- "direction": "up" | "down" | "stable" | ""
- "is_new": true ONLY if NOT in mapping table after checking variants
- If is_new: add "suggested_category", "suggested_description", and "suggested_cluster"
  - MUST use existing cluster if possible:
    cta_positioning, etf_flows, fed_balance_sheet, fx_liquidity,
    credit_spreads, equity_flows, volatility_metrics, positioning_leverage,
    rate_expectations, macro_indicators, market_microstructure, option_flows
- Empty array [] if no liquidity metrics

**logic_chains field:**
- Array of causal chains expressing policy logic (multi-step sequences)
- Each chain represents: cause → effect → next effect
- "steps": Array of ordered steps in the chain
  - Each step MUST have:
    - "cause": Initial condition (natural language)
    - "cause_normalized": Normalized variable name (snake_case, for cross-chunk linking)
    - "effect": Resulting outcome (natural language)
    - "effect_normalized": Normalized variable name (snake_case, for cross-chunk linking)
    - "mechanism": How cause leads to effect
    - "conditional_on": Conditions under which this causal link holds (free text, empty string if unconditional). E.g., "inflation at 2% target", "labor market cooling confirmed", "no external shock"
    - "evidence_quote": 1-3 sentences from the original message that support this step (REQUIRED)
    - "polarity": "BULLISH" | "BEARISH" | "NEUTRAL" - Market direction implied by this step (REQUIRED)
- Chains should have 2+ steps when the logic continues
- Single-step chains acceptable if no further effects
- When multiple speakers express distinct views, extract one chain per speaker's key policy stance — do NOT merge all speakers into 2-3 summary chains
- Empty array [] if no causal relationships

**Normalization Rules (CRITICAL for cross-chunk chain linking):**
- Check liquidity_metrics_mapping for existing normalized names (use exact match if found)
- If no exact match, create snake_case version of the concept
- Keep it short and standardized (max 30 chars)
- Common patterns: tga, rrp, sofr, fed_funds, bank_reserves, inflation, rate_cut, labor_market
- Examples:
  - "inflation falls to 2%" → cause_normalized: "inflation"
  - "rate cuts" → effect_normalized: "rate_cut"
  - "labor market cooling" → cause_normalized: "labor_market"

**Evidence Quote Rules (CRITICAL for preventing hallucination):**
- Must be VERBATIM text from the source message (Korean or English OK)
- Must contain the causal/threshold claim EXPLICITLY
- Do NOT paraphrase - use exact wording from the message
- If no clear quote available, include the most relevant sentence mentioning the cause or effect
- 1-3 sentences max per step

**Example chain from Fed speech:**
"If inflation falls to 2%, we can normalize rates, which would support housing"
→ Chain: inflation down → rate cuts → housing recovery

Structure as:
- Step 1: cause="inflation falls to 2%", cause_normalized="inflation", effect="rate cuts", effect_normalized="rate_cut", mechanism="target achieved allows policy normalization", conditional_on="no external supply shock", evidence_quote="If inflation falls to 2%, we can normalize rates"
- Step 2: cause="rate cuts", cause_normalized="rate_cut", effect="housing recovery", effect_normalized="housing", mechanism="lower mortgage rates increase affordability", conditional_on="", evidence_quote="which would support housing"

**temporal_context field:**
- Purpose: Enable retrieval filtering by policy/liquidity regime
- Structure:
  - "policy_regime": "QE" | "QT" | "hold" | "transition" - Current Fed policy stance
  - "liquidity_regime": "reserve_scarce" | "reserve_abundant" | "transitional"
  - "valid_from": Date when this logic became applicable (YYYY-MM format or null)
  - "valid_until": Date when superseded (null if still valid)
  - "is_forward_looking": true/false - Contains forecast/projection
- Example: {{"policy_regime": "QT", "liquidity_regime": "reserve_scarce", "valid_from": "2022-06", "valid_until": null, "is_forward_looking": false}}
- **IMPORTANT**: Empty object {{}} if regime context not clearly discernible from message content
- Do NOT infer regime from date alone - only tag when explicitly mentioned or strongly implied

---

{metrics_mapping_text}

---

Return ONLY the JSON array, nothing else."""

    return prompt
