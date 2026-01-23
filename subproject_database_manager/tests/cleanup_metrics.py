"""
Cleanup script for liquidity_metrics_mapping.csv

This script:
1. Merges duplicate metrics into canonical names
2. Flags non-liquidity entries (is_liquidity=false)
3. Standardizes all names to snake_case
4. Merges sources from duplicates
5. Generates migration report
"""

import csv
import os
import re
import shutil
from datetime import datetime
from collections import defaultdict

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CSV_PATH = os.path.join(PROJECT_DIR, 'data', 'processed', 'liquidity_metrics', 'liquidity_metrics_mapping.csv')
BACKUP_DIR = os.path.join(PROJECT_DIR, 'data', 'processed', 'liquidity_metrics', 'backups')

# =============================================================================
# CANONICAL NAME MAPPINGS (Aggressive merge)
# =============================================================================

CANONICAL_MAPPINGS = {
    # CTA net flow variants -> cta_net_flow
    'cta_net_flow': [
        'CTA net flow',
        'CTA net flow (1m model)',
        'CTA flows',
    ],

    # CTA trigger/threshold variants -> cta_trigger_levels
    'cta_trigger_levels': [
        'CTA short-term threshold',
        'CTA mid-term threshold',
        'CTA long-term threshold',
        'CTA model trigger levels',
        'CTA_trigger_and_threshold',
        'CTA trigger level',
        'CTA trigger/threshold',
        'CTA baseline levels',
        'CTA positioning thresholds',
        'S&P short-term trigger level',
        'CTA trigger level',
    ],

    # CTA selling variants -> cta_forced_selling
    'cta_forced_selling': [
        'CTA modeled sell size',
        'CTA modeled selling amount',
        'systemic model sell trigger',
        'systematic_sell_triggers',
        'systematic_flow_triggers',
        '1-month forced-selling magnitude',
        'CTA 1m forced selling',
        'CTA 1w program flow capacity',
        'CTA 1m forced selling',
    ],

    # ETF flow variants -> etf_net_flows
    'etf_net_flows': [
        'ETF_net_inflows_Nov',
        'ETF net flows',
        'ETF flows',
        'ETF inflows',
        'ETF_4day_net_inflows',
        'ETF YTD net flows',
        'ETF_YTD_inflows',
        'ETF flows - VOO',
        'digital asset ETF flows',
        'leveraged ETF flows',
    ],

    # ETF AUM variants -> etf_aum
    'etf_aum': [
        'ETF AUM',
        'ETF aggregate AUM',
        'ETF total holdings',
        'BRRR AUM',
        'BTF AUM',
        'Innovator_AUM',
        'Vanguard_AUM',
    ],

    # Foreign flow variants -> foreign_equity_flows
    'foreign_equity_flows': [
        'foreign_flows',
        'foreign flows',
        'foreign investor flows',
        'intl_flow_US_equities',
        'foreign portfolio flows',
        'Foreign Net Inflows to US',
        'foreign investor net-buy (12m)',
        'foreign investor positioning',
        'foreign basket selling',
    ],

    # KOSPI foreign flows (keep separate - regional)
    'kospi_foreign_flows': [
        'Foreign_net_flow_KOSPI',
        'KOSPI foreign net flow',
    ],

    # KOSDAQ foreign flows (keep separate - regional)
    'kosdaq_foreign_flows': [
        'Foreign_net_flow_KOSDAQ',
        'KOSDAQ foreign net flow',
    ],

    # Fed cut probability variants -> fed_cut_probability
    'fed_cut_probability': [
        'FOMC cut probability',
        'Fed cut probability',
        'Fed funds cut probability (25bp)',
        'market-implied Dec cut prob',
    ],

    # HF leverage variants
    'hf_gross_leverage': [
        'Prime_Gross_Leverage',
        'Gross Leverage',
    ],
    'hf_net_leverage': [
        'Prime_Net_Leverage',
        'Net Leverage',
    ],

    # Fund manager cash variants -> fund_manager_cash
    'fund_manager_cash': [
        'Fund manager cash',
        'fund managers cash',
        'cash %AUM',
        'cash_ratio',
    ],

    # DXY variants -> dxy
    'dxy': [
        'DXY',
        'DXY level',
        'USD index change',
    ],

    # Carry trade variants -> carry_trade_unwind
    'carry_trade_unwind': [
        'carry trade unwind',
        'carry unwind (JPY)',
        'carry trade positions',
        'yen carry-trade unwind',
    ],

    # KOSPI volatility variants
    'kospi_implied_vol': [
        'KOSPI200 implied vol',
        'KOSPI200 IV',
        'KOSPI2_2y_ATM_vol',
    ],

    # VKOSPI variants
    'vkospi': [
        'VKOSPI frequency (15y)',
        'VKOSPI historical exceedances',
    ],

    # VIX curve variants
    'vix_curve': [
        'VIX Curve Inversion',
        'VIX curve steepness',
    ],

    # VOO inflow variants
    'voo_inflows': [
        'VOO_Nov_inflow',
        'ETF flows - VOO',
    ],

    # US term spread variants
    'us_term_spread': [
        'US term spread',
        'US_term_spread',
    ],

    # Policy rate cuts variants
    'policy_rate_cuts': [
        'Fed cuts',
        'Fed cuts count expectation',
        'policy_rate_cuts',
        'global rate cuts',
        'Policy rate cuts YTD',
        'policy_rate_cut_expectations',  # NEW: merge duplicate
    ],

    # NEW: Additional duplicate merges identified in validation
    'carry_trade_unwind': [
        'carry trade unwind',
        'carry unwind (JPY)',
        'carry trade positions',
        'yen carry-trade unwind',
        'carry_trade_unwinding_risk',  # NEW: merge duplicate
    ],

    'eurozone_banks_upside': [
        'eurozone_banks_upside_potential',  # NEW: merge duplicate
    ],

    'ndx_spx_vol_spread': [
        'ndx_spx_vol_spread_3m25d',  # NEW: merge duplicate
    ],

    'corporate_bond_price_yield': [
        'corporate_bond_priceyield_core_weave',  # NEW: merge duplicate
    ],

    'ny_fed_balance_sheet': [
        'ny_fed_balance_sheet_rebalancing',  # NEW: merge duplicate
    ],

    'spx_option_notional': [
        'spx_option_notional_daily',  # NEW: merge duplicate
    ],

    'pension_fund_flows': [
        'pension_fund_net_buy_kospi',  # NEW: merge regional into general
        'pension_fund_net_buy_kosdaq',  # NEW: merge regional into general
    ],
}

# Build reverse lookup: original_name -> canonical_name
def build_reverse_mapping():
    reverse = {}
    for canonical, variants in CANONICAL_MAPPINGS.items():
        for variant in variants:
            reverse[variant.lower()] = canonical
    return reverse

REVERSE_MAPPING = build_reverse_mapping()

# =============================================================================
# NON-LIQUIDITY PATTERNS (flag as is_liquidity=false)
# =============================================================================

NON_LIQUIDITY_PATTERNS = [
    r'_price_QoQ$',           # Substrate pricing
    r'^ABF_',                 # ABF substrate
    r'^T-glass',              # T-glass materials
    r'_CCL_share',            # PCB market share
    r'_PCB_share',            # PCB market share
    r'_TPU_',                 # TPU metrics
    r'_return$',              # Daily ETF returns
    r'^IPO_',                 # IPO metrics
    r'^revenue',              # Company revenue
    r'^net_loss',             # Company losses
    r'^PSR$',                 # Valuation metric
    r'battery_order',         # Battery metrics
    r'Election probability',  # Political
    r'M&A_Netflix',           # M&A events
    r'headcount_hiring',      # Hiring
    r'^BT_price',             # BT substrate
    r'unmet_orders',          # Supply chain
    r'ABF_shortage',          # Supply chain
    r'ABF_utilization',       # Supply chain
    r'^EMC_',                 # Market share
    r'^TUC_',                 # Market share
    r'^GCE_',                 # Market share
    r'^Google_TPU',           # TPU orders
    r'^META_ASIC',            # ASIC metrics
    r'^DIA_return',           # Daily returns
    r'^SPY_return',           # Daily returns
    r'^QQQ_return',           # Daily returns
    r'^IWM_return',           # Daily returns
    r'^TLT_return',           # Daily returns
    r'^IEF_return',           # Daily returns
    r'^SHY_return',           # Daily returns
    r'^MJ_return',            # Daily returns
    r'^KWEB_return',          # Daily returns
    r'^XLE_return',           # Daily returns
    r'^IBIT_return',          # Daily returns
    r'Reality Labs',          # Company fundamentals
    r'^IPO proceeds',         # IPO
    r'^IPO price',            # IPO
    r'debut price surge',     # IPO
    r'^revenue YTD',          # Fundamentals
    r'^net loss',             # Fundamentals
    r'^PSR$',                 # Valuation
    r'retail subscription',   # IPO
    r'related-stock move',    # Stock move
    r'^chip_performance',     # Chip performance
    r'^service_pricing',      # Service pricing
    r'^Foundry growth',       # Company fundamentals
    r'^OpenAI',               # Company fundamentals
    r'^Anthropic',            # Company fundamentals
    r'^MongoDB',              # Company fundamentals
    r'^company_revenue',      # Fundamentals
    r'^Atlas growth',         # Fundamentals
    r'^headcount',            # Hiring
    r'^funding_valuation',    # Funding
    r'^M&A_value',            # M&A
    r'^asset_sale',           # Asset sales
    r'^Goldman_acquisition',  # M&A
    r'^Uber cumulative',      # Company losses
    r'^historical tech',      # Benchmarks
    r'^data_center_project',  # CapEx
    r'^IPO_net_proceeds',     # IPO
    r'^Nvidia data-center',   # Company revenue
    r'^Capex \(bigtech\)',    # CapEx
    r'^government grant',     # Grants
    r'^large equity stake',   # Equity sales
    r'^crypto market cap',    # Crypto
    r'^silver_price',         # Commodity price
    r'^gold_price',           # Commodity price
    r'^price_change',         # Price change
    r'^Listing Date',         # Listing
    r'^top5_marketcap',       # Market cap
    r'^2035 US data center',  # Forecasts
    r'^New projects added',   # Projects
    r'^AI computing capacity',# Capacity
    r'^Company planned',      # Planned capacity
    r'^M&A_Netflix',          # M&A
    r'^KOSPI operating',      # OP forecasts
    r'^4Q25F OP',             # OP estimates
    r'^2026 OP',              # OP estimates
    # NEW: Additional patterns from validation
    r'_op_krw$',              # Operating profit KRW
    r'_op_yo_y$',             # Operating profit YoY
    r'_opm$',                 # Operating profit margin
    r'_arr$',                 # Annual recurring revenue
    r'^ai_arr',               # AI ARR
    r'^adjusted_opm',         # Adjusted operating margin
    r'^2026_op_',             # 2026 OP estimates
    r'^4q25f_op',             # 4Q25F OP estimates
]

def is_non_liquidity(normalized_name: str) -> bool:
    """Check if metric matches non-liquidity patterns."""
    for pattern in NON_LIQUIDITY_PATTERNS:
        if re.search(pattern, normalized_name, re.IGNORECASE):
            return True
    return False

# =============================================================================
# CATEGORY FIXES (fix category column contamination)
# =============================================================================

CATEGORY_FIXES = {
    'positioning_leverage': 'indirect',
    'rate_expectations': 'indirect',
    'equity_flows': 'indirect',
    'fx_liquidity': 'indirect',
}

def fix_category_contamination(rows: list) -> int:
    """Fix category values that contain cluster names instead of direct/indirect."""
    fixes = 0
    for row in rows:
        cat = row.get('category', '')
        if cat in CATEGORY_FIXES:
            row['category'] = CATEGORY_FIXES[cat]
            fixes += 1
    return fixes

def assign_missing_clusters(rows: list) -> int:
    """Assign clusters to metrics that have is_liquidity=true but no cluster."""
    import sys
    sys.path.append(os.path.dirname(SCRIPT_DIR))
    from metrics_mapping_utils import assign_clusters_batch

    unassigned = [r for r in rows
                  if r.get('is_liquidity') == 'true'
                  and not r.get('cluster', '').strip()]

    if not unassigned:
        print("  No unassigned metrics found")
        return 0

    print(f"  Found {len(unassigned)} metrics without clusters...")

    # Batch assign clusters via LLM
    assignments = assign_clusters_batch(unassigned, batch_size=50)

    # Apply assignments
    assigned_count = 0
    for row in rows:
        if row['normalized'] in assignments:
            row['cluster'] = assignments[row['normalized']]
            assigned_count += 1

    return assigned_count

# =============================================================================
# NAME STANDARDIZATION
# =============================================================================

def to_snake_case(name: str) -> str:
    """Convert metric name to snake_case."""
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    name = name.replace('-', '_')

    # Handle camelCase -> snake_case
    name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)

    # Remove special characters except underscores
    name = re.sub(r'[^\w_]', '', name)

    # Convert to lowercase
    name = name.lower()

    # Remove consecutive underscores
    name = re.sub(r'_+', '_', name)

    # Remove leading/trailing underscores
    name = name.strip('_')

    # Truncate to 40 chars
    if len(name) > 40:
        name = name[:40]

    return name

# =============================================================================
# MAIN CLEANUP LOGIC
# =============================================================================

def load_csv():
    """Load the metrics CSV."""
    rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows

def backup_csv():
    """Create a backup of the current CSV."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'liquidity_metrics_mapping_{timestamp}.csv')

    if os.path.exists(CSV_PATH):
        shutil.copy2(CSV_PATH, backup_path)
        print(f"Backup created: {backup_path}")

    return backup_path

def merge_sources(sources_list: list) -> str:
    """Merge multiple source strings, deduplicating."""
    all_sources = set()
    for sources_str in sources_list:
        if sources_str:
            for src in sources_str.split('|'):
                src = src.strip()
                if src:
                    all_sources.add(src)
    return ' | '.join(sorted(all_sources))

def merge_variants(variants_list: list) -> str:
    """Merge multiple variant strings, deduplicating."""
    all_variants = set()
    for variants_str in variants_list:
        if variants_str:
            for var in variants_str.split('|'):
                var = var.strip()
                if var:
                    all_variants.add(var)
    return ' | '.join(sorted(all_variants))

def cleanup_metrics(rows: list) -> tuple:
    """
    Main cleanup function.
    Returns: (cleaned_rows, migration_report)
    """
    # Track metrics by canonical name for merging
    canonical_metrics = defaultdict(lambda: {
        'variants': [],
        'categories': [],
        'descriptions': [],
        'sources': [],
        'clusters': [],
        'raw_data_sources': [],
        'original_names': [],
    })

    # Track non-liquidity metrics
    non_liquidity_metrics = []

    # Track metrics that don't match any canonical mapping
    unmapped_metrics = []

    # Process each row
    for row in rows:
        normalized = row.get('normalized', '')
        normalized_lower = normalized.lower()

        # Check if it maps to a canonical name
        if normalized_lower in REVERSE_MAPPING:
            canonical = REVERSE_MAPPING[normalized_lower]
        else:
            # Keep original name, just standardize to snake_case
            canonical = to_snake_case(normalized)
            unmapped_metrics.append(normalized)

        # Collect data for merging
        canonical_metrics[canonical]['original_names'].append(normalized)
        canonical_metrics[canonical]['variants'].append(row.get('variants', ''))
        canonical_metrics[canonical]['categories'].append(row.get('category', ''))
        canonical_metrics[canonical]['descriptions'].append(row.get('description', ''))
        canonical_metrics[canonical]['sources'].append(row.get('sources', ''))
        canonical_metrics[canonical]['clusters'].append(row.get('cluster', ''))
        canonical_metrics[canonical]['raw_data_sources'].append(row.get('raw_data_source', ''))

    # Build cleaned rows
    cleaned_rows = []
    merge_count = 0

    for canonical, data in canonical_metrics.items():
        # Determine is_liquidity flag
        is_liquidity = not is_non_liquidity(canonical)

        if not is_liquidity:
            non_liquidity_metrics.append(canonical)

        # Count merges
        if len(data['original_names']) > 1:
            merge_count += len(data['original_names']) - 1

        # Merge all variants (including original names)
        all_variants = set(data['original_names'])
        for v in data['variants']:
            if v:
                for part in v.split('|'):
                    part = part.strip()
                    if part:
                        all_variants.add(part)

        # Pick most common category (or first non-empty)
        categories = [c for c in data['categories'] if c]
        category = max(set(categories), key=categories.count) if categories else ''

        # Pick longest description
        descriptions = [d for d in data['descriptions'] if d]
        description = max(descriptions, key=len) if descriptions else ''

        # Merge sources
        sources = merge_sources(data['sources'])

        # Pick most common cluster (or first non-empty)
        clusters = [c for c in data['clusters'] if c]
        cluster = max(set(clusters), key=clusters.count) if clusters else ''

        # Merge raw_data_sources
        raw_sources = [r for r in data['raw_data_sources'] if r]
        raw_data_source = ' | '.join(sorted(set(raw_sources))) if raw_sources else ''

        cleaned_rows.append({
            'normalized': canonical,
            'variants': ' | '.join(sorted(all_variants - {canonical})),
            'category': category,
            'description': description,
            'sources': sources,
            'cluster': cluster,
            'raw_data_source': raw_data_source,
            'is_liquidity': 'true' if is_liquidity else 'false',
        })

    # Sort by normalized name
    cleaned_rows.sort(key=lambda x: x['normalized'])

    # Apply category fixes (fix contamination with cluster names)
    category_fixes = fix_category_contamination(cleaned_rows)

    # Build migration report
    report = {
        'original_count': len(rows),
        'cleaned_count': len(cleaned_rows),
        'merged_count': merge_count,
        'non_liquidity_count': len(non_liquidity_metrics),
        'liquidity_count': len(cleaned_rows) - len(non_liquidity_metrics),
        'unmapped_count': len(set(unmapped_metrics)),
        'non_liquidity_metrics': non_liquidity_metrics,
        'canonical_mappings_applied': list(CANONICAL_MAPPINGS.keys()),
        'category_fixes': category_fixes,
    }

    return cleaned_rows, report

def write_csv(rows: list):
    """Write cleaned CSV with lifecycle columns."""
    fieldnames = [
        'normalized', 'variants', 'category', 'description', 'sources',
        'cluster', 'raw_data_source', 'is_liquidity',
        'first_seen', 'last_seen', 'deprecated', 'superseded_by'  # Lifecycle columns
    ]

    # Ensure all rows have lifecycle columns
    for row in rows:
        if 'first_seen' not in row:
            row['first_seen'] = ''
        if 'last_seen' not in row:
            row['last_seen'] = ''
        if 'deprecated' not in row:
            row['deprecated'] = 'false'
        if 'superseded_by' not in row:
            row['superseded_by'] = ''

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Cleaned CSV written: {CSV_PATH}")

def print_report(report: dict):
    """Print migration report."""
    print("\n" + "=" * 60)
    print("MIGRATION REPORT")
    print("=" * 60)
    print(f"Original entries:      {report['original_count']}")
    print(f"After cleanup:         {report['cleaned_count']}")
    print(f"Entries merged:        {report['merged_count']}")
    print(f"Liquidity metrics:     {report['liquidity_count']}")
    print(f"Non-liquidity (flagged): {report['non_liquidity_count']}")
    print(f"Unmapped (kept as-is): {report['unmapped_count']}")
    print(f"Category fixes:        {report.get('category_fixes', 0)}")
    if 'clusters_assigned' in report:
        print(f"Clusters assigned:     {report['clusters_assigned']}")
    print("=" * 60)

    if report['non_liquidity_metrics']:
        print("\nNon-liquidity metrics (is_liquidity=false):")
        for m in sorted(report['non_liquidity_metrics'])[:20]:
            print(f"  - {m}")
        if len(report['non_liquidity_metrics']) > 20:
            print(f"  ... and {len(report['non_liquidity_metrics']) - 20} more")

    print("\nCanonical mappings applied:")
    for canonical in sorted(report['canonical_mappings_applied']):
        variants = CANONICAL_MAPPINGS[canonical]
        print(f"  {canonical} <- {len(variants)} variants")

# =============================================================================
# LIFECYCLE / DEPRECATION UTILITIES (Issue 4: Metrics Governance)
# =============================================================================

def deprecate_metric(normalized_name: str, superseded_by: str = '') -> bool:
    """
    Mark a metric as deprecated, optionally with a replacement.

    Args:
        normalized_name: The normalized name of the metric to deprecate
        superseded_by: The normalized name of the replacement metric (optional)

    Returns:
        True if metric was found and deprecated, False otherwise
    """
    rows = load_csv()

    found = False
    for row in rows:
        if row['normalized'].lower() == normalized_name.lower():
            row['deprecated'] = 'true'
            row['superseded_by'] = superseded_by
            found = True
            break

    if found:
        write_csv(rows)
        print(f"Deprecated metric: {normalized_name}")
        if superseded_by:
            print(f"  Superseded by: {superseded_by}")
    else:
        print(f"Metric not found: {normalized_name}")

    return found


def find_stale_metrics(days_threshold: int = 180) -> list:
    """
    Find metrics not seen in the last N days.

    Args:
        days_threshold: Number of days to consider a metric stale

    Returns:
        List of dicts with normalized name and last_seen date
    """
    from datetime import datetime, timedelta

    rows = load_csv()
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    stale_metrics = []

    for row in rows:
        last_seen = row.get('last_seen', '')
        if not last_seen:
            # Legacy metric with no last_seen - skip (can't determine staleness)
            continue

        try:
            last_seen_date = datetime.fromisoformat(last_seen)
            if last_seen_date < cutoff_date:
                stale_metrics.append({
                    'normalized': row['normalized'],
                    'last_seen': last_seen,
                    'days_since_seen': (datetime.now() - last_seen_date).days,
                    'is_liquidity': row.get('is_liquidity', 'true'),
                    'deprecated': row.get('deprecated', 'false'),
                })
        except ValueError:
            # Invalid date format - skip
            continue

    # Sort by days_since_seen descending
    stale_metrics.sort(key=lambda x: x['days_since_seen'], reverse=True)

    return stale_metrics


def list_deprecated_metrics() -> list:
    """
    List all deprecated metrics.

    Returns:
        List of dicts with normalized name and superseded_by
    """
    rows = load_csv()
    deprecated = []

    for row in rows:
        if row.get('deprecated', 'false') == 'true':
            deprecated.append({
                'normalized': row['normalized'],
                'superseded_by': row.get('superseded_by', ''),
                'is_liquidity': row.get('is_liquidity', 'true'),
            })

    return deprecated


def main(dry_run: bool = False):
    """Main entry point."""
    print("Loading CSV...")
    rows = load_csv()
    print(f"Loaded {len(rows)} entries")

    if not dry_run:
        print("\nCreating backup...")
        backup_csv()

    print("\nRunning cleanup...")
    cleaned_rows, report = cleanup_metrics(rows)

    if dry_run:
        print_report(report)
        print("\n[DRY RUN] No changes written to disk.")
        print("Run with --execute to apply changes.")
    else:
        # Assign clusters to unassigned metrics (requires LLM calls)
        print("\nAssigning clusters to unassigned metrics...")
        clusters_assigned = assign_missing_clusters(cleaned_rows)
        report['clusters_assigned'] = clusters_assigned

        print_report(report)

        print("\nWriting cleaned CSV...")
        write_csv(cleaned_rows)
        print("\nCleanup complete!")

if __name__ == '__main__':
    import sys

    dry_run = '--execute' not in sys.argv

    if dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be made")
        print("Run with --execute to apply changes")
        print("=" * 60)

    main(dry_run=dry_run)
