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
                "suggested_description": "Reserve Demand Elasticity"
            }}
        ],
        "logic_chains": [
            {{
                "steps": [
                    {{"cause": "labor market cooling", "effect": "wage pressure easing", "mechanism": "fewer job openings reduce worker bargaining power"}},
                    {{"cause": "wage pressure easing", "effect": "inflation decline", "mechanism": "lower wage growth reduces service inflation"}}
                ]
            }}
        ]
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
- Extract ALL liquidity-related metrics (at message level)
- "raw": Original text
- "normalized": Standardized name from mapping table
- "value": Specific value, empty if none
- "direction": "up" | "down" | "stable" | ""
- "is_new": true if NOT in mapping table
- If is_new: add "suggested_category" and "suggested_description"
- Empty array [] if no liquidity metrics

**logic_chains field:**
- Array of causal chains expressing policy logic (multi-step sequences)
- Each chain represents: cause → effect → next effect
- "steps": Array of ordered steps in the chain
  - Each step has: "cause", "effect", "mechanism"
- Chains should have 2+ steps when the logic continues
- Single-step chains acceptable if no further effects
- Empty array [] if no causal relationships

**Example chain from Fed speech:**
"If inflation falls to 2%, we can normalize rates, which would support housing"
→ Chain: inflation down → rate cuts → housing recovery

Structure as:
- Step 1: cause="inflation falls to 2%", effect="rate cuts", mechanism="target achieved allows policy normalization"
- Step 2: cause="rate cuts", effect="housing recovery", mechanism="lower mortgage rates increase affordability"

---

{metrics_mapping_text}

---

Return ONLY the JSON array, nothing else."""

    return prompt
