import pandas as pd
import glob, os, shutil
from datetime import datetime

def extract_metadata(df):
    period, fund = None, None
    for i in range(len(df)):
        val = str(df.iloc[i, 0])
        if 'Reporting Period:' in val: period = val.split('Reporting Period:')[1].strip()
        elif 'Institution Account(s):' in val: fund = val.split('Institution Account(s):')[1].strip()
    return period, fund

def parse_period(s):
    parts = s.split(' to ')
    return datetime.strptime(parts[0].strip(), '%d-%b-%y'), datetime.strptime(parts[1].strip(), '%d-%b-%y')

def extract_display_name(name):
    return 'Firm' if name == 'All Institution Accounts' else (name.split(' - ')[-1] if ' - ' in name else name)

def update_funds_csv(long_name, start, end, path='./data/funds.csv'):
    display = extract_display_name(long_name)
    s_str, e_str = start.strftime('%m/%d/%y'), end.strftime('%m/%d/%y')
    df = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=['short_name', 'long_name', 'display_name', 'start_date', 'end_date'])
    mask = df['long_name'] == long_name
    if not mask.any():
        df = pd.concat([df, pd.DataFrame([{'short_name': 'TBD', 'long_name': long_name, 'display_name': display, 'start_date': s_str, 'end_date': e_str}])], ignore_index=True)
    else:
        idx = df[mask].index[0]
        row = df.loc[idx]
        if pd.isna(row['start_date']) or not row['start_date']:
            df.loc[idx, ['start_date', 'end_date', 'display_name']] = [s_str, e_str, display]
        else:
            es, ee = datetime.strptime(str(row['start_date']), '%m/%d/%y'), datetime.strptime(str(row['end_date']), '%m/%d/%y')
            df.loc[idx, ['start_date', 'end_date']] = [s_str if start < es else row['start_date'], e_str if end > ee else row['end_date']]
            if pd.isna(row['display_name']) or not row['display_name']: df.loc[idx, 'display_name'] = display
    df.to_csv(path, index=False)
    return display

def process_file(filepath):
    print(f"Processing: {os.path.basename(filepath)}")
    raw = pd.read_excel(filepath, header=None)
    has_data = not (len(raw) > 1 and 'Sorry - the criteria selected did not match any results.' in str(raw.iloc[1, 0]))
    if not has_data: print("  No data available")
    params_row = next((i for i in range(len(raw)) if str(raw.iloc[i, 0]) == 'Parameters'), None)
    if params_row is None: print("  ERROR: No 'Parameters' row found"); return
    period_str, fund_name = extract_metadata(raw)
    if not period_str or not fund_name: print("  ERROR: Missing metadata"); return
    display = update_funds_csv(fund_name, *parse_period(period_str))
    data_df = raw.iloc[1:params_row].copy() if has_data and params_row > 1 else pd.DataFrame(columns=raw.iloc[0])
    if has_data and params_row > 1: data_df.columns = raw.iloc[0]
    for d in ['./data/processed', './data/archive']: os.makedirs(d, exist_ok=True)
    output = f"./data/processed/{display}_{period_str.replace(' to ', '_').replace('-', '')}.csv"
    data_df.to_csv(output, index=False)
    print(f"  Saved: {os.path.basename(output)}")
    shutil.move(filepath, f"./data/archive/{os.path.basename(filepath)}")
    print(f"  Archived: {os.path.basename(filepath)}")

def consolidate_processed():
    files = glob.glob('./data/processed/*.csv')
    if not files: print("No processed files found"); return
    funds = {}
    for f in files:
        parts = os.path.basename(f).replace('.csv', '').split('_')
        funds.setdefault('_'.join(parts[:-2]) if len(parts) > 2 else parts[0], []).append(f)
    print(f"\nConsolidating {len(funds)} funds:\n")
    os.makedirs('./data/consolidated', exist_ok=True)
    for name, flist in funds.items():
        print(f"{name}: {len(flist)} file(s)")
        dfs = [pd.read_csv(f) for f in sorted(flist)]
        for f, d in zip(sorted(flist), dfs): print(f"  Loaded: {os.path.basename(f)} ({len(d)} rows)")
        combined = pd.concat(dfs, ignore_index=True)
        print(f"  Combined: {len(combined)} rows")
        if len(combined) == 0: print("  No data available")
        elif 'Meeting ID' in combined.columns and 'ItemOnAgendaID' in combined.columns:
            before = len(combined)
            dups = combined[combined.duplicated(subset=['Meeting ID', 'ItemOnAgendaID'], keep='first')]
            if len(dups) > 0:
                os.makedirs('./data/duplicates', exist_ok=True)
                dups.to_csv(f'./data/duplicates/{name}_duplicates.csv', index=False)
                print(f"  Duplicates saved")
            combined = combined.drop_duplicates(subset=['Meeting ID', 'ItemOnAgendaID'], keep='first')
            print(f"  Deduplicated: {before - len(combined)} removed")
        if len(combined) > 0 and 'Meeting Date' in combined.columns:
            combined['Meeting Date'] = pd.to_datetime(combined['Meeting Date'], errors='coerce')
            combined = combined.sort_values('Meeting Date')
        combined.to_csv(f'./data/consolidated/{name}_consolidated.csv', index=False)
        print(f"  Saved: {name}_consolidated.csv\n")

def main():
    files = glob.glob('./data/*.XLSX') + glob.glob('./data/*.xlsx')
    if not files: print("No XLSX files found, running consolidation..."); consolidate_processed(); return
    print(f"Found {len(files)} files\n")
    for f in files:
        try: process_file(f); print()
        except Exception as e: print(f"  ERROR: {e}\n")
    consolidate_processed()

if __name__ == '__main__': 
    main()

