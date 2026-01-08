#!/usr/bin/env python3
"""
Consolidate multiple voting data files into single files per fund.
Deduplicates and prefers quarterly data over annual data.

Usage: python consolidate_data.py [--data-dir ./data]
"""

import pandas as pd
import glob
import os
import re
from datetime import datetime


def get_file_priority(filename):
    """Return priority score: lower = higher priority (quarterly > annual)"""
    if re.search(r'Q[1-4]', filename, re.IGNORECASE):
        return 1  # Quarterly
    elif re.search(r'ANNUAL', filename, re.IGNORECASE):
        return 2  # Annual
    else:
        return 3  # Unknown/Legacy


def scan_dir(directory):
    """Scan subdirectories for CSV files, grouped by fund folder name"""
    funds = {}

    # Get all subdirectories (each represents a fund)
    for fund_dir in glob.glob(os.path.join(directory, "*/")):
        fund_id = os.path.basename(fund_dir.rstrip('/'))

        # Skip special folders
        if fund_id in ['consolidated', 'archive', '.git']:
            continue

        # Find all CSV files in this fund's directory (excluding archive subfolders)
        csv_files = []
        for f in glob.glob(os.path.join(fund_dir, "*.[cC][sS][vV]")):
            csv_files.append(f)

        if csv_files:
            funds[fund_id] = csv_files

    return funds


def consolidate_fund(fund_id, file_paths, output_dir):
    """Consolidate all files for a fund into single CSV"""
    print(f"Processing {fund_id}: {len(file_paths)} files")

    # Sort by priority (quarterly first)
    file_paths = sorted(file_paths, key=lambda f: (get_file_priority(f), f))

    # Load all files
    dfs = []
    for fp in file_paths:
        try:
            df = pd.read_csv(fp, parse_dates=['Meeting Date', 'Record Date'], dayfirst=True)
            df['_source_file'] = os.path.basename(fp)
            df['_file_priority'] = get_file_priority(fp)
            dfs.append(df)
            print(f"  Loaded: {os.path.basename(fp)} ({len(df)} rows)")
        except Exception as e:
            print(f"  ERROR loading {fp}: {e}")

    if not dfs:
        print(f"  No valid files for {fund_id}, skipping")
        return

    # Concatenate
    combined = pd.concat(dfs, ignore_index=True)
    print(f"  Combined: {len(combined)} total rows")

    # Deduplicate by Meeting ID + Proposal Number (keep first = highest priority)
    if 'Meeting ID' in combined.columns and 'Proposal Number' in combined.columns:
        # Sort by priority then row order
        combined = combined.sort_values('_file_priority')
        before = len(combined)
        combined = combined.drop_duplicates(subset=['Meeting ID', 'Proposal Number'], keep='first')
        after = len(combined)
        print(f"  Deduplicated: {before - after} duplicates removed, {after} rows remaining")

    # Remove helper columns
    combined = combined.drop(columns=['_source_file', '_file_priority'])

    # Sort by date for cleaner output
    if 'Meeting Date' in combined.columns:
        combined = combined.sort_values('Meeting Date')

    # Save to consolidated folder
    consolidated_dir = os.path.join(output_dir, 'consolidated')
    os.makedirs(consolidated_dir, exist_ok=True)
    output_path = os.path.join(consolidated_dir, f"{fund_id}_consolidated.csv")
    combined.to_csv(output_path, index=False)
    print(f"  Saved: {output_path}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Consolidate voting data files')
    parser.add_argument('--data-dir', default='./data', help='Data directory path')
    args = parser.parse_args()

    data_dir = args.data_dir

    print(f"Scanning {data_dir} for CSV files...")
    funds = scan_dir(data_dir)
    print(f"Found {len(funds)} funds: {list(funds.keys())}\n")

    for fund_id, files in funds.items():
        consolidate_fund(fund_id, files, data_dir)

    print(f"Consolidation complete at {datetime.now()}")


if __name__ == '__main__':
    main()
