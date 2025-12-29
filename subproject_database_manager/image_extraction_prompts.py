"""
Image Extraction Prompts

Prompts for extracting information from images in financial research messages.
Used by process_messages_v3.py for vision-based analysis.
"""


def get_image_summary_prompt(message_text: str) -> str:
    """
    Get prompt for brief image summarization (used for categorization).

    Args:
        message_text: Context text from the message

    Returns:
        Prompt string for image summary
    """
    return f"""Briefly summarize what this image shows (1-2 sentences).

Context text: {message_text}

Focus on:
- Type of content (chart, data table, text, announcement, etc.)
- Main topic if visible
- Key data/information if present

Return just the summary, no JSON."""


def get_image_structured_extraction_prompt(message_text: str, message_date: str) -> str:
    """
    Get prompt for structured data extraction from image.

    Args:
        message_text: Context text from the message
        message_date: Date of the message

    Returns:
        Prompt string for structured extraction
    """
    return f"""Analyze this chart/image from a financial research message.

**Context:**
Date: {message_date}
Related text: {message_text[:200]}...

**Extract (ALL FIELDS MUST BE IN ENGLISH):**
1. **source**: Who created this chart? (e.g., Bloomberg, Fed, Hana Securities, Bank of Japan)
2. **data_source**: Where is the data from? (in English)
3. **asset_class**: What asset class? Use English names like "Japanese Government Bonds (JGBs)", "equities", "FX", "US Treasuries", "cryptocurrency", "ETF", "derivatives"
4. **used_data**: What data is displayed? (in English)
5. **what_happened**: What patterns/changes are visible? (in English)
6. **interpretation**: What does it suggest? (in English)

**CRITICAL: All output must be in English. Translate any Korean/Japanese/other language content.**

Return JSON only:
```json
{{
    "source": "...",
    "data_source": "...",
    "asset_class": "...",
    "used_data": "...",
    "what_happened": "...",
    "interpretation": "..."
}}
```"""
