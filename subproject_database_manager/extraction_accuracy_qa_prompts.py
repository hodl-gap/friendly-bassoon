"""
Prompts for Extraction Accuracy QA

Verifies that extracted values are CORRECT (not just well-structured).
"""


def get_accuracy_verification_prompt(raw_text: str, extracted_data: dict) -> str:
    """
    Generate prompt to verify extraction accuracy against source text.

    The verifier checks if extracted values match what's in the source.
    """

    import json

    # Format extracted data for verification
    liquidity_metrics = extracted_data.get('liquidity_metrics', [])
    logic_chains = extracted_data.get('logic_chains', [])

    prompt = f"""You are a fact-checker verifying if extracted data matches the source text.

**SOURCE TEXT:**
{raw_text}

**EXTRACTED DATA TO VERIFY:**

## Liquidity Metrics:
{json.dumps(liquidity_metrics, indent=2, ensure_ascii=False) if liquidity_metrics else "None extracted"}

## Logic Chains:
{json.dumps(logic_chains, indent=2, ensure_ascii=False) if logic_chains else "None extracted"}

---

**YOUR TASK:**
Verify EACH extracted field against the source text. Check for:

1. **Variable names**: Does the normalized name match what's mentioned?
   - "TGA" → "tga" ✓
   - "재무부 일반계정" → "tga" ✓
   - "RRP" extracted when text says "TGA" ✗

2. **Values**: Are numbers/amounts correct?
   - Text says "750B" → extracted "750B" ✓
   - Text says "750B" → extracted "800B" ✗

3. **Directions**: Is up/down/stable correct?
   - Text says "증가/rise/up" → direction "up" ✓
   - Text says "증가" → direction "down" ✗

4. **Logic chain accuracy**:
   - Does the cause actually appear in the text?
   - Does the effect actually appear in the text?
   - Is the mechanism a reasonable interpretation?
   - Does evidence_quote match verbatim text?

**OUTPUT FORMAT (JSON):**
```json
{{
  "verification_results": [
    {{
      "field": "liquidity_metrics[0].normalized",
      "extracted_value": "tga",
      "source_evidence": "TGA 잔고가",
      "is_correct": true,
      "error_type": null
    }},
    {{
      "field": "liquidity_metrics[0].direction",
      "extracted_value": "down",
      "source_evidence": "증가 (means increase)",
      "is_correct": false,
      "error_type": "direction_wrong",
      "correction": "up"
    }}
  ],
  "summary": {{
    "total_fields_checked": 5,
    "correct": 4,
    "errors": 1,
    "error_rate": 0.20,
    "error_types": ["direction_wrong"]
  }}
}}
```

**ERROR TYPES:**
- `variable_wrong`: Wrong variable identified
- `value_wrong`: Incorrect number/amount
- `direction_wrong`: Up/down/stable incorrect
- `cause_wrong`: Logic chain cause not in text
- `effect_wrong`: Logic chain effect not in text
- `evidence_mismatch`: evidence_quote doesn't match source
- `hallucination`: Extracted something not in source at all

**IMPORTANT:**
- Be strict but fair
- If the source is ambiguous, mark as correct
- Only flag clear errors
- Return ONLY the JSON, no other text"""

    return prompt
