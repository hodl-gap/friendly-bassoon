"""
Prompts for Relationship Store Module
"""

# Prompt for extracting trigger conditions from a logic chain
TRIGGER_EXTRACTION_PROMPT = """Given this macro logic chain, extract 1-2 trigger conditions that would activate it.

Chain: {summary}
Cause: {cause} (normalized: {cause_norm})
Terminal effect: {effect}
Mechanism: {mechanism}

Consider the NORMAL volatility range for each variable:
- VIX: 5% weekly change is routine, 20%+ is significant
- DXY: 0.5% weekly change is routine, 2%+ is significant
- us10y/us02y: 5bps weekly change is routine, 15bps+ is significant
- TGA: 3% weekly change is routine, 10%+ is significant
- BTC: 5% weekly change is routine, 15%+ is significant
- Gold: 2% weekly change is routine, 5%+ is significant
- S&P 500: 2% weekly change is routine, 5%+ is significant

Extract trigger conditions that represent MEANINGFUL moves for the cause variable."""
