"""
Prompts for extracting data opinion structure
"""

from metrics_mapping_utils import load_metrics_mapping

# =============================================================================
# PROMPT CACHING SUPPORT
# =============================================================================
# Claude's prompt caching allows caching of static system prompts for 5 minutes.
# This separates the large static instructions (~200KB with metrics mapping)
# from the dynamic per-batch content (channel + messages).
# Use get_data_opinion_system_prompt() + get_data_opinion_user_prompt() with
# call_claude_with_cache() for cost savings on repeated batches.

# Cache for the static system prompt (rebuilt only when metrics change)
_system_prompt_cache = None
_system_prompt_metrics_hash = None


def get_data_opinion_system_prompt(metrics_mapping_text=None) -> str:
    """
    Get the STATIC system prompt for data opinion extraction.

    This contains all instructions and the metrics mapping table.
    It should be cached by Claude for 5 minutes using cache_control.

    Returns:
        Static system prompt string (for use with cache_control)
    """
    global _system_prompt_cache, _system_prompt_metrics_hash

    # Load metrics mapping if not provided
    if metrics_mapping_text is None:
        metrics_mapping_text = load_metrics_mapping()

    # Simple hash to detect metrics changes
    metrics_hash = hash(metrics_mapping_text)

    # Return cached if available and metrics unchanged
    if _system_prompt_cache is not None and _system_prompt_metrics_hash == metrics_hash:
        return _system_prompt_cache

    system_prompt = """You are extracting structured information from financial research analysis messages.

**Your task has TWO parts:**
1. Identify which messages belong to the same "opinion/article"
2. Extract structured data from each message

**PART 1: Opinion Grouping**
Messages sent close together in time (within minutes) that discuss the same topic or are continuations should get the same opinion_id.
Format: `{channel_name}_N` where N increments for each new opinion/article.

**PART 2: Data Extraction**

**CRITICAL: CONCISE OUTPUT RULE**
All text fields must be CONCISE and RETRIEVAL-OPTIMIZED:
- NO full sentences - use comma-separated phrases or key terms
- NO filler words (jumped, decreased, increased) - use symbols or short forms
- PRESERVE all meaningful data (numbers, thresholds, conditions)
- Format: "metric: value, metric: value" or "key point, key point"

For EACH message, extract the following fields:

1. **source** - Institution name only (MUST be in English)
   - e.g., "Fed", "Bloomberg", "BLS", "NY Fed", "BOJ"
   - NOT: "The Federal Reserve Bank" → just "Fed"

2. **data_source** - Data source name only (MUST be in English)
   - e.g., "H.4.1", "Daily Treasury Statement", "FOMC Minutes"
   - Can be same as source. Empty string if none.

3. **asset_class** - Asset class, concise (MUST be in English)
   - e.g., "UST", "JGBs", "money markets", "FX", "equities"
   - Empty string if not applicable

4. **used_data** - Data points ONLY, no sentences (MUST be in English)
   - Format: "metric: value, metric: value"
   - GOOD: "RDE: -0.2→0.5, TGA: $750B, ON RRP: $100B"
   - BAD: "RDE jumped from -0.2 to 0.5" (too verbose)
   - Empty string if no specific data

5. **what_happened** - Key observations, concise (MUST be in English)
   - Format: short phrases, comma-separated
   - GOOD: "RDE spike signals funding stress, TGA drawdown"
   - BAD: "A sharp rise in RDE indicates elevated funding demand" (too wordy)
   - Empty string if just announcement

6. **interpretation** - Implications, concise (MUST be in English)
   - Format: short phrases
   - GOOD: "Fed may pause QT, liquidity injection via TGA"
   - BAD: "This may force the Fed to halt QT soon" (too wordy)
   - Empty string if no interpretation

7. **tags** - Liquidity relevance classification
   - **"direct_liquidity"**: Monetary liquidity mechanisms
     - Fed balance sheet: QE, QT, RRP, TGA, SRF, BTFP, reserves
     - Money markets: SOFR, repo rates, fed funds, funding stress
     - Examples: "TGA drawdown", "RRP spiked", "QT ending"
   - **"indirect_liquidity"**: Market channels affecting liquidity
     - Positioning: CTA flows, dealer gamma, systematic flows
     - Credit: corporate issuance, buybacks, credit spreads
     - Policy expectations: rate cut/hike impact on markets
     - FX: DXY, USD liquidity effects
     - Examples: "CTA selling $23B", "negative gamma", "buybacks supporting"
   - **"irrelevant"**: NO liquidity connection (use sparingly)
     - Pure company fundamentals without market implications
     - Product prices (DRAM) without funding angle
     - ONLY when content has zero liquidity relevance

8. **topic_tags** - Array of topic tags for discovery (ALWAYS populate, separate from liquidity)
   - Purpose: Enable search by TOPIC regardless of liquidity relevance
   - Categories (select ALL applicable, typically 2-4):
     - Asset Class: "equities", "rates", "FX", "credit", "commodities"
     - Region: "US", "china", "japan", "europe", "korea", "EM"
     - Data Type: "macro_data", "earnings", "central_bank"
     - Mechanics: "positioning", "flows", "volatility"
   - Examples:
     - TGA drawdown: ["US", "central_bank"]
     - Fed rate cut: ["US", "central_bank", "rates"]
     - CTA selling equities: ["equities", "positioning", "flows"]
     - Samsung earnings: ["korea", "equities", "earnings"]

9. **liquidity_metrics** - Array of liquidity-related metrics ONLY

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
   - Daily returns: SPY return, QQQ return, DIA return, individual ETF returns
   - Company fundamentals: revenue, net loss, IPO proceeds, PSR, EPS, earnings
   - Product prices: DRAM, semiconductor, chip prices
   - Valuation: P/E, multiples, target prices
   - Battery/EV: battery orders, EV volumes
   - Political: election probabilities
   - Hiring/headcount metrics
   - M&A deal values
   - Company-specific cash burn (e.g., "OpenAI cash burn" is NOT liquidity)

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
   - Use standard abbreviations: cta, etf, hf, dxy, tga, rrp

   **Structure:**
   - "raw": Original text as mentioned
   - "normalized": Standardized name from mapping table (use snake_case for new)
   - "value": Specific value (e.g., "750B", "4.5%"), empty if none
   - "direction": "up" | "down" | "stable" | ""
   - "is_new": true ONLY if NOT in mapping table after checking variants
   - If is_new=true:
     - "suggested_category": "direct" | "indirect"
     - "suggested_description": Brief description of what this metric measures
     - "suggested_cluster": MUST use existing cluster if possible:
       cta_positioning, etf_flows, fed_balance_sheet, fx_liquidity,
       credit_spreads, equity_flows, volatility_metrics, positioning_leverage,
       rate_expectations, macro_indicators, market_microstructure, option_flows
   - Empty array [] if no liquidity metrics

10. **logic_chains** - Array of causal chains (multi-step sequences)
   - Each chain represents a connected sequence: cause → effect → next effect
   - "steps": Array of ordered steps in the chain
     - Each step MUST have:
       - "cause": Initial condition (natural language)
       - "cause_normalized": Normalized variable name (snake_case, for cross-chunk linking)
       - "effect": Resulting outcome (natural language)
       - "effect_normalized": Normalized variable name (snake_case, for cross-chunk linking)
       - "mechanism": How cause leads to effect
       - "evidence_quote": 1-3 sentences from the original message that support this step (REQUIRED)
   - Chains should have 2+ steps when the logic continues
   - Single-step chains are acceptable if no further effects
   - Empty array [] if no causal relationships

   **Normalization Rules (CRITICAL for cross-chunk chain linking):**
   - Check liquidity_metrics_mapping for existing normalized names (use exact match if found)
   - If no exact match, create snake_case version of the concept
   - Keep it short and standardized (max 30 chars)
   - Common patterns: tga, rrp, sofr, fed_funds, bank_reserves, carry_trade, risk_off, jpy_weakness
   - Examples:
     - "TGA drawdown" → cause_normalized: "tga"
     - "bank reserves increase" → effect_normalized: "bank_reserves"
     - "JPY weakness" → cause_normalized: "jpy_weakness"
     - "carry trade unwind" → effect_normalized: "carry_unwind"

   **Evidence Quote Rules (CRITICAL for preventing hallucination):**
   - Must be VERBATIM text from the source message (Korean or English OK)
   - Must contain the causal/threshold claim EXPLICITLY
   - Do NOT paraphrase - use exact wording from the message
   - If no clear quote available, include the most relevant sentence mentioning the cause or effect
   - 1-3 sentences max per step

   **Example of a 3-step chain:**
   Fed rate cuts → real rates down → risk asset valuations up

   **How to structure:**
   - Step 1: cause="Fed rate cuts", cause_normalized="fed_rate_cut", effect="real rates down", effect_normalized="real_rates", mechanism="rate cuts reduce yields", evidence_quote="Fed는 25bp 인하를 단행했고..."
   - Step 2: cause="real rates down", cause_normalized="real_rates", effect="risk asset valuations up", effect_normalized="risk_asset_valuation", mechanism="lower real yields increase PV", evidence_quote="실질 금리 하락은..."

11. **temporal_context** - Temporal and regime information for retrieval filtering
   - Purpose: Enable retrieval filtering by policy/liquidity regime
   - Structure:
     - "policy_regime": "QE" | "QT" | "hold" | "transition" - Current Fed policy stance
     - "liquidity_regime": "reserve_scarce" | "reserve_abundant" | "transitional"
     - "valid_from": Date when this logic became applicable (YYYY-MM format or null)
     - "valid_until": Date when superseded (null if still valid)
     - "is_forward_looking": true/false - Contains forecast/projection
   - Example: {"policy_regime": "QT", "liquidity_regime": "reserve_scarce", "valid_from": "2022-06", "valid_until": null, "is_forward_looking": false}
   - **IMPORTANT**: Empty object {} if regime context not clearly discernible from message content
   - Do NOT infer regime from date alone - only tag when explicitly mentioned or strongly implied

**Output format (JSON array, one entry per message):**
```json
[
    {
        "message_index": 1,
        "opinion_id": "{channel_name}_1",
        "source": "Fed",
        "data_source": "H.4.1, Daily Treasury Statement",
        "asset_class": "money markets",
        "used_data": "RDE: -0.2→0.5, TGA: $750B",
        "what_happened": "RDE spike signals funding stress, TGA drawdown",
        "interpretation": "Fed may pause QT, liquidity injection via TGA",
        "tags": "direct_liquidity",
        "topic_tags": ["US", "central_bank", "rates"],
        "liquidity_metrics": [
            {
                "raw": "TGA 잔고",
                "normalized": "TGA",
                "value": "750B",
                "direction": "down",
                "is_new": false
            }
        ],
        "logic_chains": [
            {
                "steps": [
                    {"cause": "TGA drawdown", "cause_normalized": "tga", "effect": "bank reserves increase", "effect_normalized": "bank_reserves", "mechanism": "Treasury spending releases TGA funds", "evidence_quote": "TGA 잔고가 750B로 감소하면서 시스템 유동성이 증가"}
                ]
            }
        ],
        "temporal_context": {
            "policy_regime": "QT",
            "liquidity_regime": "reserve_scarce",
            "valid_from": "2022-06",
            "valid_until": null,
            "is_forward_looking": false
        }
    }
]
```

**Important:**
- **CRITICAL: CONCISE OUTPUT** - No full sentences, use short phrases and "metric: value" format
- **CRITICAL: ALL text in ENGLISH** - Translate Korean/other languages
- **ALL fields in English**: source, data_source, asset_class, used_data, what_happened, interpretation
- **Asset class**: Use abbreviations - "JGBs", "UST", "FX" (not full names)
- **Preserve meaning**: Keep all numbers, thresholds, conditions - just remove filler words
- If field doesn't apply, use empty string "" or empty array []
- Messages about same topic sent close together get same opinion_id
- message_index = message number (1, 2, 3...)
- For liquidity_metrics, use mapping table below to normalize metric names

---

""" + metrics_mapping_text + """

---

Return ONLY the JSON array, nothing else."""

    # Cache the result
    _system_prompt_cache = system_prompt
    _system_prompt_metrics_hash = metrics_hash

    return system_prompt


def get_data_opinion_user_prompt(messages_batch, channel_name) -> str:
    """
    Get the DYNAMIC user prompt for data opinion extraction.

    This contains only the channel name and messages to process.
    This part changes per batch and should NOT be cached.

    Returns:
        Dynamic user prompt string
    """
    prompt = f"""**Channel**: {channel_name}

**Messages to analyze:**

"""
    for i, msg in enumerate(messages_batch, 1):
        prompt += f"\n--- Message {i} ---\n"
        prompt += f"Date: {msg['date']}\n"
        prompt += f"Text: {msg['text']}\n"
        if msg.get('photo'):
            prompt += f"Has photo: Yes\n"
        prompt += "\n"

    return prompt


def get_data_opinion_extraction_prompt(messages_batch, channel_name, metrics_mapping_text=None):
    """Prompt for extracting data_opinion structure from a batch of messages with opinion grouping"""

    # Load metrics mapping if not provided
    if metrics_mapping_text is None:
        metrics_mapping_text = load_metrics_mapping()

    prompt = f"""You are extracting structured information from financial research analysis messages.

**Channel**: {channel_name}

**Your task has TWO parts:**
1. Identify which messages belong to the same "opinion/article"
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
Messages sent close together in time (within minutes) that discuss the same topic or are continuations should get the same opinion_id.
Format: `{channel_name}_N` where N increments for each new opinion/article.

**PART 2: Data Extraction**

**CRITICAL: CONCISE OUTPUT RULE**
All text fields must be CONCISE and RETRIEVAL-OPTIMIZED:
- NO full sentences - use comma-separated phrases or key terms
- NO filler words (jumped, decreased, increased) - use symbols or short forms
- PRESERVE all meaningful data (numbers, thresholds, conditions)
- Format: "metric: value, metric: value" or "key point, key point"

For EACH message, extract the following fields:

1. **source** - Institution name only (MUST be in English)
   - e.g., "Fed", "Bloomberg", "BLS", "NY Fed", "BOJ"
   - NOT: "The Federal Reserve Bank" → just "Fed"

2. **data_source** - Data source name only (MUST be in English)
   - e.g., "H.4.1", "Daily Treasury Statement", "FOMC Minutes"
   - Can be same as source. Empty string if none.

3. **asset_class** - Asset class, concise (MUST be in English)
   - e.g., "UST", "JGBs", "money markets", "FX", "equities"
   - Empty string if not applicable

4. **used_data** - Data points ONLY, no sentences (MUST be in English)
   - Format: "metric: value, metric: value"
   - GOOD: "RDE: -0.2→0.5, TGA: $750B, ON RRP: $100B"
   - BAD: "RDE jumped from -0.2 to 0.5" (too verbose)
   - Empty string if no specific data

5. **what_happened** - Key observations, concise (MUST be in English)
   - Format: short phrases, comma-separated
   - GOOD: "RDE spike signals funding stress, TGA drawdown"
   - BAD: "A sharp rise in RDE indicates elevated funding demand" (too wordy)
   - Empty string if just announcement

6. **interpretation** - Implications, concise (MUST be in English)
   - Format: short phrases
   - GOOD: "Fed may pause QT, liquidity injection via TGA"
   - BAD: "This may force the Fed to halt QT soon" (too wordy)
   - Empty string if no interpretation

7. **tags** - Liquidity relevance classification
   - **"direct_liquidity"**: Monetary liquidity mechanisms
     - Fed balance sheet: QE, QT, RRP, TGA, SRF, BTFP, reserves
     - Money markets: SOFR, repo rates, fed funds, funding stress
     - Examples: "TGA drawdown", "RRP spiked", "QT ending"
   - **"indirect_liquidity"**: Market channels affecting liquidity
     - Positioning: CTA flows, dealer gamma, systematic flows
     - Credit: corporate issuance, buybacks, credit spreads
     - Policy expectations: rate cut/hike impact on markets
     - FX: DXY, USD liquidity effects
     - Examples: "CTA selling $23B", "negative gamma", "buybacks supporting"
   - **"irrelevant"**: NO liquidity connection (use sparingly)
     - Pure company fundamentals without market implications
     - Product prices (DRAM) without funding angle
     - ONLY when content has zero liquidity relevance

8. **topic_tags** - Array of topic tags for discovery (ALWAYS populate, separate from liquidity)
   - Purpose: Enable search by TOPIC regardless of liquidity relevance
   - Categories (select ALL applicable, typically 2-4):
     - Asset Class: "equities", "rates", "FX", "credit", "commodities"
     - Region: "US", "china", "japan", "europe", "korea", "EM"
     - Data Type: "macro_data", "earnings", "central_bank"
     - Mechanics: "positioning", "flows", "volatility"
   - Examples:
     - TGA drawdown: ["US", "central_bank"]
     - Fed rate cut: ["US", "central_bank", "rates"]
     - CTA selling equities: ["equities", "positioning", "flows"]
     - Samsung earnings: ["korea", "equities", "earnings"]

9. **liquidity_metrics** - Array of liquidity-related metrics ONLY

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
   - Daily returns: SPY return, QQQ return, DIA return, individual ETF returns
   - Company fundamentals: revenue, net loss, IPO proceeds, PSR, EPS, earnings
   - Product prices: DRAM, semiconductor, chip prices
   - Valuation: P/E, multiples, target prices
   - Battery/EV: battery orders, EV volumes
   - Political: election probabilities
   - Hiring/headcount metrics
   - M&A deal values
   - Company-specific cash burn (e.g., "OpenAI cash burn" is NOT liquidity)

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
   - Use standard abbreviations: cta, etf, hf, dxy, tga, rrp

   **Structure:**
   - "raw": Original text as mentioned
   - "normalized": Standardized name from mapping table (use snake_case for new)
   - "value": Specific value (e.g., "750B", "4.5%"), empty if none
   - "direction": "up" | "down" | "stable" | ""
   - "is_new": true ONLY if NOT in mapping table after checking variants
   - If is_new=true:
     - "suggested_category": "direct" | "indirect"
     - "suggested_description": Brief description of what this metric measures
     - "suggested_cluster": MUST use existing cluster if possible:
       cta_positioning, etf_flows, fed_balance_sheet, fx_liquidity,
       credit_spreads, equity_flows, volatility_metrics, positioning_leverage,
       rate_expectations, macro_indicators, market_microstructure, option_flows
   - Empty array [] if no liquidity metrics

10. **logic_chains** - Array of causal chains (multi-step sequences)
   - Each chain represents a connected sequence: cause → effect → next effect
   - "steps": Array of ordered steps in the chain
     - Each step MUST have:
       - "cause": Initial condition (natural language)
       - "cause_normalized": Normalized variable name (snake_case, for cross-chunk linking)
       - "effect": Resulting outcome (natural language)
       - "effect_normalized": Normalized variable name (snake_case, for cross-chunk linking)
       - "mechanism": How cause leads to effect
       - "evidence_quote": 1-3 sentences from the original message that support this step (REQUIRED)
   - Chains should have 2+ steps when the logic continues
   - Single-step chains are acceptable if no further effects
   - Empty array [] if no causal relationships

   **Normalization Rules (CRITICAL for cross-chunk chain linking):**
   - Check liquidity_metrics_mapping for existing normalized names (use exact match if found)
   - If no exact match, create snake_case version of the concept
   - Keep it short and standardized (max 30 chars)
   - Common patterns: tga, rrp, sofr, fed_funds, bank_reserves, carry_trade, risk_off, jpy_weakness
   - Examples:
     - "TGA drawdown" → cause_normalized: "tga"
     - "bank reserves increase" → effect_normalized: "bank_reserves"
     - "JPY weakness" → cause_normalized: "jpy_weakness"
     - "carry trade unwind" → effect_normalized: "carry_unwind"

   **Evidence Quote Rules (CRITICAL for preventing hallucination):**
   - Must be VERBATIM text from the source message (Korean or English OK)
   - Must contain the causal/threshold claim EXPLICITLY
   - Do NOT paraphrase - use exact wording from the message
   - If no clear quote available, include the most relevant sentence mentioning the cause or effect
   - 1-3 sentences max per step

   **Example of a 3-step chain:**
   Fed rate cuts → real rates down → risk asset valuations up

   **How to structure:**
   - Step 1: cause="Fed rate cuts", cause_normalized="fed_rate_cut", effect="real rates down", effect_normalized="real_rates", mechanism="rate cuts reduce yields", evidence_quote="Fed는 25bp 인하를 단행했고..."
   - Step 2: cause="real rates down", cause_normalized="real_rates", effect="risk asset valuations up", effect_normalized="risk_asset_valuation", mechanism="lower real yields increase PV", evidence_quote="실질 금리 하락은..."

11. **temporal_context** - Temporal and regime information for retrieval filtering
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

**Output format (JSON array, one entry per message):**
```json
[
    {{
        "message_index": 1,
        "opinion_id": "{channel_name}_1",
        "source": "Fed",
        "data_source": "H.4.1, Daily Treasury Statement",
        "asset_class": "money markets",
        "used_data": "RDE: -0.2→0.5, TGA: $750B",
        "what_happened": "RDE spike signals funding stress, TGA drawdown",
        "interpretation": "Fed may pause QT, liquidity injection via TGA",
        "tags": "direct_liquidity",
        "topic_tags": ["US", "central_bank", "rates"],
        "liquidity_metrics": [
            {{
                "raw": "TGA 잔고",
                "normalized": "TGA",
                "value": "750B",
                "direction": "down",
                "is_new": false
            }},
            {{
                "raw": "RDE",
                "normalized": "RDE",
                "value": "-0.2→0.5",
                "direction": "up",
                "is_new": true,
                "suggested_category": "direct",
                "suggested_description": "Reserve Demand Elasticity, Fed liquidity sensitivity",
                "suggested_cluster": "Fed_balance_sheet"
            }}
        ],
        "logic_chains": [
            {{
                "steps": [
                    {{"cause": "TGA drawdown", "cause_normalized": "tga", "effect": "bank reserves increase", "effect_normalized": "bank_reserves", "mechanism": "Treasury spending releases TGA funds into banking system", "evidence_quote": "TGA 잔고가 750B로 감소하면서 시스템 유동성이 증가"}},
                    {{"cause": "bank reserves increase", "cause_normalized": "bank_reserves", "effect": "funding conditions ease", "effect_normalized": "funding_conditions", "mechanism": "more reserves reduce repo rate pressure", "evidence_quote": "리저브 증가로 레포 압력 완화 예상"}}
                ]
            }},
            {{
                "steps": [
                    {{"cause": "RDE spike", "cause_normalized": "rde", "effect": "QT pause likely", "effect_normalized": "qt_pause", "mechanism": "high reserve demand elasticity signals system stress", "evidence_quote": "RDE가 0.5까지 급등하면 Fed는 QT를 멈출 수밖에 없다"}}
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
- **CRITICAL: CONCISE OUTPUT** - No full sentences, use short phrases and "metric: value" format
- **CRITICAL: ALL text in ENGLISH** - Translate Korean/other languages
- **ALL fields in English**: source, data_source, asset_class, used_data, what_happened, interpretation
- **Asset class**: Use abbreviations - "JGBs", "UST", "FX" (not full names)
- **Preserve meaning**: Keep all numbers, thresholds, conditions - just remove filler words
- If field doesn't apply, use empty string "" or empty array []
- Messages about same topic sent close together get same opinion_id
- message_index = message number (1, 2, 3...)
- For liquidity_metrics, use mapping table below to normalize metric names

---

{metrics_mapping_text}

---

Return ONLY the JSON array, nothing else."""

    return prompt
