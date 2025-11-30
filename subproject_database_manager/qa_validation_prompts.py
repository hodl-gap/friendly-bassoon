"""
Prompts for QA validation of structured extractions

This module contains prompts for the QA agent that validates the quality
of structured outputs across three dimensions:
1. Retrievability - Multiple semantic entry points
2. Completeness - If-then logic preservation
3. Answerability - Specific, quantitative information
"""

import json


def get_qa_validation_prompt(extracted_data, raw_text, category):
    """
    Generate QA validation prompt for evaluating extraction quality

    Args:
        extracted_data: Dict or JSON string of extracted structured data
        raw_text: Original message text
        category: Message category (data_opinion/interview_meeting)

    Returns:
        str: Formatted prompt for QA validation
    """

    # Convert to dict if JSON string
    if isinstance(extracted_data, str):
        try:
            extracted_data = json.loads(extracted_data)
        except json.JSONDecodeError:
            extracted_data = {"error": "Failed to parse JSON"}

    prompt = f"""You are a QA agent validating structured data extraction quality for a financial research retrieval system.

**Category**: {category}

**Raw Message:**
{raw_text}

**Extracted Data:**
{json.dumps(extracted_data, indent=2, ensure_ascii=False)}

---

**Your Task:**
Evaluate this extraction across THREE dimensions and provide detailed feedback with Chain of Thought reasoning.

**NOTE on Output Format:**
The extraction should use concise, retrieval-friendly format:
- GOOD: "RDE: -0.2→0.5, TGA: $750B" (data points only)
- BAD: "RDE jumped from -0.2 to 0.5" (unnecessary verbs/filler)

However, for complex phenomena, longer explanations are acceptable if they preserve important meaning.
Do NOT penalize length if the complexity warrants it.

**DIMENSION 1: Retrievability**
Question: Can someone find this insight through multiple semantic entry points?

Example: If the insight mentions "USDKRW affects liquidity," can it be found by searching:
  - "currency", "liquidity", "Korea", "Fed policy", "FX"

Check:
- Are there enough semantic tags/keywords for various search paths?
- Would different domain experts (macro, rates, FX) be able to find this?
- Are technical terms AND plain language terms both present?
- **liquidity_metrics field**: Are specific liquidity metrics extracted with normalized names?
  - If the message mentions liquidity-related data (TGA, RRP, Fed balance sheet, etc.),
    these should be captured in the liquidity_metrics array
  - Empty liquidity_metrics when tags != "irrelevant" is a red flag

**DIMENSION 2: Completeness of Context**
Question: Is the if-then logic preserved with sufficient context?

NOT GOOD: "USDKRW down = bad"
GOOD: "USDKRW down = bad WHEN below 1300 BECAUSE of trade deficit implications"

Check for:
- **Thresholds**: Specific numbers/levels (e.g., "below 1300", "above 4%")
- **Conditions**: When/if statements
- **Causality**: Because/due to/driven by relationships
- **Context dependencies**: What makes this significant?
- **metric_relationships field** (data_opinion only): Are causal chains between metrics captured?
  - Example: "TGA decline → bank_reserves increase → repo_rate pressure"

**DIMENSION 3: Answerability**
Question: Can this extraction answer real financial research questions?

Example questions this type of data should answer:
- "What level indicates stress?" → needs threshold numbers, not just "high" or "low"
- "Why does this matter?" → needs interpretation with reasoning
- "What data supports this?" → needs specific data points
- "What changed?" → needs before/after or trends

Check:
- Specific, quantitative information present?
- Actionable insights (not just vague observations)?
- Clear linkage between data and interpretation?

---

**Output Format (JSON only):**
```json
{{
    "overall_verdict": "PASS" | "FAIL",
    "confidence_score": 0.0-1.0,
    "chain_of_thought": "Step-by-step reasoning for your assessment. Walk through each dimension.",

    "dimension_scores": {{
        "retrievability": {{
            "score": 0.0-1.0,
            "analysis": "Detailed analysis of semantic entry points",
            "broken_paths": ["Searching 'credit conditions' won't find this"],
            "available_paths": ["Can be found via 'liquidity' search"],
            "liquidity_metrics_quality": "Assessment of liquidity_metrics array"
        }},
        "completeness": {{
            "score": 0.0-1.0,
            "analysis": "Analysis of if-then logic and context",
            "missing_pieces": ["No threshold value specified", "Causality unclear"],
            "metric_relationships_quality": "Assessment of metric_relationships array (data_opinion only)"
        }},
        "answerability": {{
            "score": 0.0-1.0,
            "analysis": "Analysis of question-answering capability",
            "unanswerable_questions": ["What level indicates stress?"]
        }}
    }},

    "suggested_fixes": [
        "Add 'monetary policy' as semantic tag",
        "Specify threshold value: 'below 1300' instead of just 'low'",
        "Include specific data point values"
    ]
}}
```

**Scoring Guidelines:**
- **1.0**: Excellent - Multiple entry points, complete context, highly answerable
- **0.8-0.9**: Good - Most dimensions covered, minor gaps
- **0.6-0.7**: Acceptable - Core information present, some context missing
- **0.4-0.5**: Poor - Significant gaps, limited usefulness
- **0.0-0.3**: Fail - Missing critical information

**Overall Verdict:**
- PASS: Overall quality score ≥ 0.6 (average of 3 dimensions)
- FAIL: Overall quality score < 0.6

**Important:**
- Be specific and actionable in your feedback
- Focus on what would make this data MORE useful for retrieval and analysis
- Consider the use case: Financial researchers searching for specific insights
- Balance: Don't require perfection, but ensure minimum quality for practical use

Return ONLY the JSON, nothing else."""

    return prompt
