"""Risk Intelligence Module - Analyze macro event impact on risk assets."""

from .insight_orchestrator import run_impact_analysis, run_multi_asset_analysis

# Backward-compatible alias
run_btc_impact_analysis = run_impact_analysis

__all__ = ["run_impact_analysis", "run_btc_impact_analysis", "run_multi_asset_analysis"]
