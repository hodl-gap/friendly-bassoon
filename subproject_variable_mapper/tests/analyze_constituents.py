#!/usr/bin/env python3
import json

# Load the data
with open('snp500_constituents.json', 'r') as f:
    data = json.load(f)

print("=" * 80)
print("S&P 500 CONSTITUENTS ANALYSIS (2020-01 to 2025-01)")
print("=" * 80)
print()

# Basic stats
print(f"Total months of data: {len(data)}")
print(f"Date range: {min(data.keys())} to {max(data.keys())}")
print()

# Count changes by year
months = sorted(data.keys())
changes_by_year = {}

for i in range(1, len(months)):
    prev_month = months[i-1]
    curr_month = months[i]
    
    prev_set = set(data[prev_month])
    curr_set = set(data[curr_month])
    
    added = curr_set - prev_set
    removed = prev_set - curr_set
    
    if added or removed:
        year = curr_month[:4]
        if year not in changes_by_year:
            changes_by_year[year] = {'added': [], 'removed': [], 'months': []}
        
        changes_by_year[year]['added'].extend(list(added))
        changes_by_year[year]['removed'].extend(list(removed))
        changes_by_year[year]['months'].append(curr_month)

print("CHANGES BY YEAR:")
print("-" * 80)
for year in sorted(changes_by_year.keys()):
    stats = changes_by_year[year]
    print(f"\n{year}:")
    print(f"  Total additions: {len(stats['added'])}")
    print(f"  Total removals: {len(stats['removed'])}")
    print(f"  Months with changes: {len(stats['months'])}")
    print(f"  Added: {', '.join(sorted(stats['added']))}")
    print(f"  Removed: {', '.join(sorted(stats['removed']))}")

print()
print("=" * 80)
print("COMPANIES THROUGHOUT THE ENTIRE PERIOD")
print("=" * 80)

# Find companies that were in all months
all_months_sets = [set(data[month]) for month in months]
always_present = set.intersection(*all_months_sets)

print(f"\nCompanies present in ALL {len(months)} months: {len(always_present)}")
print(f"Sample (first 20): {', '.join(sorted(list(always_present))[:20])}")

# Find companies added and never removed
first_month = set(data[months[0]])
last_month = set(data[months[-1]])

new_entries = last_month - first_month
removed_entries = first_month - last_month

print(f"\nNet new entries (in 2025-01 but not in 2020-01): {len(new_entries)}")
if new_entries:
    print(f"  {', '.join(sorted(new_entries))}")

print(f"\nNet removed entries (in 2020-01 but not in 2025-01): {len(removed_entries)}")
if removed_entries:
    print(f"  {', '.join(sorted(removed_entries))}")

print()
