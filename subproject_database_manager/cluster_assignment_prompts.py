"""
Prompts for LLM-assisted cluster assignment to liquidity metrics.
"""


def get_cluster_assignment_prompt(metric_info: dict, existing_clusters: list) -> str:
    """
    Prompt for assigning a cluster to a single new metric.

    Args:
        metric_info: Dict with normalized, description, category, sources
        existing_clusters: List of existing cluster names

    Returns:
        Prompt string for LLM
    """
    clusters_context = "\n".join([f"- {c}" for c in existing_clusters]) if existing_clusters else "No existing clusters yet."

    prompt = f"""Assign a cluster to this liquidity metric.

METRIC TO ASSIGN:
- Normalized name: {metric_info.get('normalized', '')}
- Description: {metric_info.get('description', '')}
- Category: {metric_info.get('category', '')}
- Sources: {metric_info.get('sources', '')}

EXISTING CLUSTERS:
{clusters_context}

CLUSTERING RULES:
1. Assign to an EXISTING cluster if the metric fits semantically
2. Create a NEW cluster ONLY if no existing cluster is appropriate
3. Cluster names should be snake_case and descriptive
4. Group by conceptual similarity:
   - CTA_positioning: CTA triggers, thresholds, modeled systematic flows
   - ETF_flows: ETF inflows, outflows, AUM changes
   - Fed_balance_sheet: Fed reserves, RRP, TGA, QT/QE, IORB
   - FX_liquidity: DXY, currency pairs, carry trades, FX funding
   - credit_spreads: CDS spreads, IG/HY spreads, credit stress
   - equity_flows: Buybacks, foreign flows, pension flows, sector rotation
   - volatility_metrics: VIX, implied volatility, realized volatility
   - positioning_leverage: Gross/net leverage, margin, systematic positions
   - rate_expectations: Fed cut probabilities, rate forecasts, policy moves
   - corporate_fundamentals: Revenue, earnings, cash flow, capex
   - macro_indicators: GDP, employment, inflation, ISM data

OUTPUT FORMAT (JSON):
{{
    "cluster": "cluster_name",
    "is_new_cluster": false
}}

Return ONLY the JSON object, nothing else."""

    return prompt


def get_batch_cluster_assignment_prompt(metrics: list, existing_clusters: list) -> str:
    """
    Batch prompt for assigning clusters to multiple metrics at once.
    More efficient for migration of existing metrics.

    Args:
        metrics: List of metric dicts with normalized, description, category
        existing_clusters: List of existing cluster names

    Returns:
        Prompt string for LLM
    """
    clusters_context = "\n".join([f"- {c}" for c in existing_clusters]) if existing_clusters else "No existing clusters yet."

    metrics_list = "\n".join([
        f"{i+1}. {m.get('normalized', '')}: {m.get('description', '')[:100]}"
        for i, m in enumerate(metrics)
    ])

    prompt = f"""Assign clusters to these liquidity metrics.

METRICS TO ASSIGN:
{metrics_list}

EXISTING CLUSTERS:
{clusters_context}

CLUSTERING GUIDELINES:
1. Group semantically similar metrics together
2. Use snake_case for cluster names
3. Standard clusters:
   - CTA_positioning: CTA triggers, thresholds, modeled flows
   - ETF_flows: ETF inflows, outflows, AUM changes
   - Fed_balance_sheet: reserves, RRP, TGA, QT/QE
   - FX_liquidity: DXY, currency pairs, FX funding
   - credit_spreads: CDS, IG/HY spreads, credit stress
   - equity_flows: buybacks, foreign flows, pension flows
   - volatility_metrics: VIX, implied vol, realized vol
   - positioning_leverage: gross/net leverage, margin
   - rate_expectations: Fed cut probabilities, rate forecasts
   - corporate_fundamentals: revenue, earnings, capex
   - macro_indicators: GDP, employment, inflation
   - market_microstructure: bid depth, order book, trading volume
   - option_flows: option notional, gamma, option strategies
   - sovereign_flows: government bond issuance, fiscal deficit

OUTPUT FORMAT (JSON array):
[
    {{"metric_index": 1, "cluster": "cluster_name"}},
    {{"metric_index": 2, "cluster": "cluster_name"}},
    ...
]

Return ONLY the JSON array, nothing else."""

    return prompt
