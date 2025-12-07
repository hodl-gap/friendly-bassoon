"""
Prompts for extracting data opinion structure
"""

from metrics_mapping_utils import load_metrics_mapping


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

7. **tags** - Liquidity relevance
   - "direct_liquidity" | "indirect_liquidity" | "irrelevant"

8. **liquidity_metrics** - Array of metrics
   - "raw": Original text as mentioned
   - "normalized": Standardized name from mapping table
   - "value": Specific value (e.g., "750B", "4.5%"), empty if none
   - "direction": "up" | "down" | "stable" | ""
   - "is_new": true if NOT in mapping table
   - If is_new=true:
     - "suggested_category": "direct" | "indirect"
     - "suggested_description": Brief description of what this metric measures
   - Empty array [] if no liquidity metrics

9. **logic_chains** - Array of causal chains (multi-step sequences)
   - Each chain represents a connected sequence: cause → effect → next effect
   - "steps": Array of ordered steps in the chain
     - Each step has: "cause", "effect", "mechanism"
   - Chains should have 2+ steps when the logic continues
   - Single-step chains are acceptable if no further effects
   - Empty array [] if no causal relationships

   **Example of a 3-step chain:**
   Fed rate cuts → real rates down → risk asset valuations up

   **How to structure:**
   - Step 1: cause="Fed rate cuts", effect="real rates down", mechanism="rate cuts reduce yields"
   - Step 2: cause="real rates down", effect="risk asset valuations up", mechanism="lower real yields increase PV of future cash flows"

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
                "suggested_description": "Reserve Demand Elasticity, Fed liquidity sensitivity"
            }}
        ],
        "logic_chains": [
            {{
                "steps": [
                    {{"cause": "TGA drawdown", "effect": "bank reserves increase", "mechanism": "Treasury spending releases TGA funds into banking system"}},
                    {{"cause": "bank reserves increase", "effect": "funding conditions ease", "mechanism": "more reserves reduce repo rate pressure"}}
                ]
            }},
            {{
                "steps": [
                    {{"cause": "RDE spike", "effect": "QT pause likely", "mechanism": "high reserve demand elasticity signals system stress"}}
                ]
            }}
        ]
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
