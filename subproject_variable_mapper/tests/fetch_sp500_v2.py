"""
Improved S&P 500 constituent fetcher - uses forward time direction
"""

import pandas as pd
import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import json
from typing import Dict, List, Set
from io import StringIO

def fetch_wikipedia_sp500_data():
    """Fetch current constituents and historical changes from Wikipedia"""

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    print("Fetching S&P 500 data from Wikipedia...")

    try:
        # Set headers to avoid 403 Forbidden error
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # Read tables from Wikipedia with custom headers
        html = requests.get(url, headers=headers).text
        tables = pd.read_html(StringIO(html))

        # First table contains current constituents
        current_constituents = tables[0]
        print(f"Found {len(current_constituents)} current constituents")

        # Second table contains historical changes (has multi-level columns)
        historical_changes = tables[1]

        # Flatten multi-level columns
        if isinstance(historical_changes.columns, pd.MultiIndex):
            historical_changes.columns = ['_'.join(col).strip() for col in historical_changes.columns.values]

        print(f"Found {len(historical_changes)} historical change records")
        print(f"Historical changes columns: {list(historical_changes.columns)}")

        return current_constituents, historical_changes

    except Exception as e:
        print(f"Error fetching Wikipedia data: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def parse_date(date_str):
    """Parse date string from Wikipedia format"""
    if pd.isna(date_str) or date_str == '':
        return None

    try:
        # Try different date formats
        for fmt in ['%B %d, %Y', '%Y-%m-%d', '%m/%d/%Y']:
            try:
                return pd.to_datetime(date_str, format=fmt)
            except:
                continue

        # If no format works, try pandas' default parser
        return pd.to_datetime(date_str)
    except:
        return None

def build_monthly_constituents_v2(current_constituents, historical_changes,
                                   start_date='2020-01-01', end_date='2025-01-01'):
    """
    Build monthly constituent lists using a forward-tracking approach
    """

    print(f"\nBuilding monthly constituent lists from {start_date} to {end_date}...")

    # Get current list of tickers as of today
    current_tickers = set(current_constituents['Symbol'].tolist())
    print(f"Current constituents (as of today): {len(current_tickers)}")

    # Process historical changes into a clean format
    changes_list = []

    for idx, row in historical_changes.iterrows():
        # Try different column name patterns for date
        date_str = None
        for col_name in ['Effective Date_Effective Date', 'Date', 'Effective Date']:
            if col_name in row.index:
                date_str = row.get(col_name, '')
                break

        date = parse_date(date_str)
        if date is None:
            continue

        # Get added and removed tickers
        added_ticker = None
        removed_ticker = None

        # Try to find Added ticker column
        for col_name in ['Added_Ticker', 'Added Ticker', 'Added']:
            if col_name in row.index:
                added = row.get(col_name, '')
                if isinstance(added, str) and added.strip():
                    added_ticker = added.strip().split()[0]
                break

        # Try to find Removed ticker column
        for col_name in ['Removed_Ticker', 'Removed Ticker', 'Removed']:
            if col_name in row.index:
                removed = row.get(col_name, '')
                if isinstance(removed, str) and removed.strip():
                    removed_ticker = removed.strip().split()[0]
                break

        if added_ticker or removed_ticker:
            changes_list.append({
                'date': date,
                'added': added_ticker,
                'removed': removed_ticker
            })

    # Convert to DataFrame and sort by date (oldest first)
    changes_df = pd.DataFrame(changes_list)
    changes_df = changes_df.sort_values('date', ascending=True)

    print(f"Processed {len(changes_df)} historical changes")
    print(f"Changes date range: {changes_df['date'].min()} to {changes_df['date'].max()}")

    # Generate list of month-end dates
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)

    monthly_dates = []
    current_date = start
    while current_date <= end:
        # Get last day of the month
        month_end = current_date + relativedelta(day=31)
        monthly_dates.append(month_end)
        current_date = current_date + relativedelta(months=1)

    # Build constituents for each month
    monthly_constituents = {}

    # Start with current constituents and work backwards
    constituents_now = current_tickers.copy()

    # For each month, going backwards from now
    for month_date in sorted(monthly_dates, reverse=True):
        # Find all changes that happened AFTER this month_date
        future_changes = changes_df[changes_df['date'] > month_date]

        # Apply inverse of these changes
        constituents_at_month = constituents_now.copy()

        for _, change in future_changes.iterrows():
            if change['added']:
                # If ticker was added after this date, remove it
                constituents_at_month.discard(change['added'])
            if change['removed']:
                # If ticker was removed after this date, add it back
                constituents_at_month.add(change['removed'])

        month_key = month_date.strftime('%Y-%m')
        monthly_constituents[month_key] = sorted(list(constituents_at_month))

        print(f"  {month_key}: {len(monthly_constituents[month_key])} constituents")

    # Sort by date (oldest first) for final output
    monthly_constituents = dict(sorted(monthly_constituents.items()))

    return monthly_constituents

def main():
    """Main execution function"""

    print("=" * 60)
    print("S&P 500 Monthly Constituents Fetcher v2")
    print("=" * 60)

    # Fetch data from Wikipedia
    current_constituents, historical_changes = fetch_wikipedia_sp500_data()

    if current_constituents is None or historical_changes is None:
        print("\nFailed to fetch data from Wikipedia.")
        return

    # Build monthly constituent lists
    monthly_data = build_monthly_constituents_v2(
        current_constituents,
        historical_changes,
        start_date='2020-01-01',
        end_date='2025-01-01'
    )

    # Save to JSON file
    output_file = 'snp500_constituents.json'
    with open(output_file, 'w') as f:
        json.dump(monthly_data, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Results saved to: {output_file}")
    print(f"{'=' * 60}")

    # Generate summary
    print("\nSUMMARY:")
    print(f"  Total months: {len(monthly_data)}")
    print(f"  Date range: {min(monthly_data.keys())} to {max(monthly_data.keys())}")

    # Count constituents per month
    constituent_counts = {month: len(tickers) for month, tickers in monthly_data.items()}
    print(f"  Constituents per month range: {min(constituent_counts.values())} to {max(constituent_counts.values())}")

    # Track changes over time
    print("\n  Notable statistics:")
    all_tickers = set()
    for tickers in monthly_data.values():
        all_tickers.update(tickers)
    print(f"    Total unique tickers over period: {len(all_tickers)}")

    # Compare first and last month
    first_month = min(monthly_data.keys())
    last_month = max(monthly_data.keys())
    first_set = set(monthly_data[first_month])
    last_set = set(monthly_data[last_month])

    added_tickers = last_set - first_set
    removed_tickers = first_set - last_set

    print(f"\n    Tickers added between {first_month} and {last_month}: {len(added_tickers)}")
    if len(added_tickers) <= 30:
        print(f"      Added: {', '.join(sorted(added_tickers))}")

    print(f"\n    Tickers removed between {first_month} and {last_month}: {len(removed_tickers)}")
    if len(removed_tickers) <= 30:
        print(f"      Removed: {', '.join(sorted(removed_tickers))}")

    # Show some months with unusual counts
    avg_count = sum(constituent_counts.values()) / len(constituent_counts)
    unusual_months = {month: count for month, count in constituent_counts.items()
                     if abs(count - avg_count) > 2}

    if unusual_months:
        print(f"\n    Months with constituent counts different from average ({avg_count:.1f}):")
        for month in sorted(unusual_months.keys()):
            print(f"      {month}: {unusual_months[month]} constituents")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)

if __name__ == "__main__":
    main()
