import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob
from datetime import datetime

st.set_page_config(page_title="Executive Proxy Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

COLORS = {
    "primary": "#0f172a",
    "accent": "#3b82f6",
    "success": "#22c55e",
    "danger": "#ef4444",
    "warning": "#f59e0b",
    "background": "#f8fafc"
}

def inject_css():
    st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 3rem; }
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        }
        div[data-testid="stMetric"] label { font-size: 0.85rem; color: #64748b; }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #0f172a; }
        section[data-testid="stSidebar"] { background-color: #f8fafc; border-right: 1px solid #e2e8f0; }
        h1, h2, h3 { font-family: 'Inter', sans-serif; letter-spacing: -0.5px; }
        h1 { font-weight: 800; color: #0f172a; font-size: 2.2rem; }
        h3 { font-weight: 600; color: #334155; font-size: 1.2rem; margin-top: 1rem; }
        footer { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)

FUND_NAME_MAP = {
    "DEFGLITS": "AQR Delphi Global Equity Fund",
    "AQRGLOB": "AQR Global Core Fund",
    "AQREMERGE": "AQR Emerging Markets Fund",
}

def get_name(code):
    return FUND_NAME_MAP.get(code, code)

def get_quarter(date_series):
    if date_series.empty: return None
    valid_dates = pd.to_datetime(date_series, errors='coerce').dropna()
    if valid_dates.empty: return None
    representative_date = valid_dates.iloc[0]
    quarter = (representative_date.month - 1) // 3 + 1
    return f"Q{quarter} {representative_date.year}"

def get_code(filename):
    base = os.path.basename(filename)
    return base.split('_')[0] if '_' in base else base.split('.')[0]

def get_dropchoices():
    now = datetime.now()
    quarters = []
    current_q = (now.month - 1) // 3 + 1
    current_y = now.year
    for _ in range(6):
        quarters.append(f"Q{current_q} {current_y}")
        current_q -= 1
        if current_q == 0:
            current_q = 4
            current_y -= 1
    return quarters

@st.cache_data(ttl=3600)
def check_data(data_dir):
    if not os.path.exists(data_dir): return {}
    files = glob.glob(os.path.join(data_dir, "*.csv")) + glob.glob(os.path.join(data_dir, "*.CSV"))
    funds = {}
    for f in files:
        fund_code = get_code(f)
        if fund_code not in funds: funds[fund_code] = []
        funds[fund_code].append(f)
    return funds

@st.cache_data(ttl=3600)
def get_fund_quarters(fund_code, file_list):
    quarters = {}
    for f in file_list:
        try:
            df = pd.read_csv(f, nrows=5)
            if 'Meeting Date' in df.columns and not df.empty:
                q = get_quarter(df['Meeting Date'])
                if q and q not in quarters: quarters[q] = f
        except: continue
    return quarters

@st.cache_data(ttl=600)
def load_data(filepath):
    try:
        df = pd.read_csv(filepath)
        if df.empty: return pd.DataFrame()
        if 'Meeting Date' in df.columns:
            df['Meeting Date'] = pd.to_datetime(df['Meeting Date'], errors='coerce')
        return df
    except: return pd.DataFrame()

def calc_kpis(df):
    if df.empty: return None
    stats = {}
    stats['meetings'] = df['Company Name'].nunique() if 'Company Name' in df.columns else 0
    stats['total_votes'] = len(df)
    
    if 'Vote Against Management' in df.columns:
        with_mgmt = (df['Vote Against Management'] == 'No').sum()
        stats['mgmt_alignment_pct'] = (with_mgmt / len(df)) * 100
    else:
        stats['mgmt_alignment_pct'] = 0

    if 'Vote Instruction' in df.columns:
        against_mgmt= df[df['Vote Instruction'].isin(['Against', 'Withhold'])]
        stats['dissent_count'] = len(against_mgmt)
        stats['dissent_pct'] = (len(against_mgmt) / len(df)) * 100
    else:
        stats['dissent_count'] = 0
        stats['dissent_pct'] = 0
    return stats

def render_distribution_chart(df):
    if df.empty or 'Vote Instruction' not in df.columns: return None
    counts = df['Vote Instruction'].value_counts()
    counts = counts[counts > 0]
    
    data = counts.reset_index()
    data.columns = ['Vote', 'Count']
    color_map = {"For": COLORS['success'], "Against": COLORS['danger'], "Abstain": COLORS['warning'], "Withhold": COLORS['primary']}

    fig = px.pie(data, values='Count', names='Vote', hole=0.6, color='Vote', color_discrete_map=color_map)
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=0, b=0), legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5))
    fig.update_traces(textposition='outside', textinfo='percent+label')
    return fig

def main():
    inject_css()
    
    with st.sidebar:
        st.title("⚙️ Control Panel")
        data_dir = "./data"
        if not os.path.exists(data_dir): data_dir = "/mnt/user-data/uploads"
        
        available_funds = check_data(data_dir)
        if not available_funds:
            st.warning(f"No CSV files found in `{data_dir}`.")
            st.stop()
            
        fund_codes = list(available_funds.keys())
        selected_fund = st.selectbox("Select Fund", fund_codes, format_func=lambda x: get_name(x))
        
        fund_quarters = get_fund_quarters(selected_fund, available_funds[selected_fund])
        available_quarters = list(fund_quarters.keys())
        last_6 = get_dropchoices()
        selectable_quarters = [q for q in last_6 if q in available_quarters]
        if not selectable_quarters: selectable_quarters = available_quarters
        selected_quarter = st.selectbox("Select Quarter", selectable_quarters) if selectable_quarters else None
        
        st.markdown("---")
        if selected_fund and selected_quarter:
            data_file = fund_quarters.get(selected_quarter)
            df = load_data(data_file)
        else:
            df = pd.DataFrame()

        if not df.empty:
            st.subheader("export Reports")
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV Data", csv, f"{selected_fund}_{selected_quarter}.csv", "text/csv", use_container_width=True)
            st.caption("Generate PDF via Print > Save as PDF in browser.")

    if df.empty:
        st.markdown("### Please select a Fund and Quarter to begin.")
        st.info("No data loaded or file is empty.")
        st.stop()

    st.title(f"Proxy Voting Dashboard: {selected_quarter}")
    st.caption(f"Fund: {get_name(selected_fund)} | Source: {os.path.basename(data_file)}")
    
    kpis = calc_kpis(df)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Meetings Voted", f"{kpis['meetings']}", delta="100% Complete", delta_color="normal")
    with col2:
        st.metric("Votes Cast", f"{kpis['total_votes']:,}")
    with col3:
        val = kpis['mgmt_alignment_pct']
        st.metric("Mgmt Alignment", f"{val:.1f}%", delta="Target > 90%" if val > 90 else "Below Target", delta_color="normal" if val > 90 else "inverse")
    with col4:
        dissent = kpis['dissent_count']
        st.metric("Dissent / Risk", f"{dissent}", delta=f"{kpis['dissent_pct']:.1f}% of total", delta_color="inverse")

    st.markdown("---")

    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Vote Distribution")
        fig_dist = render_distribution_chart(df)
        if fig_dist: st.plotly_chart(fig_dist, use_container_width=True)
            
    with c2:
        st.subheader("Category Breakdown")
        if 'Proposal Code Category' in df.columns:
            cat_df = df.groupby('Proposal Code Category').agg(
                Total_Proposals=('Proposal Text', 'count'),
                Against_Mgmt=('Vote Against Management', lambda x: (x == 'Yes').sum())
            ).reset_index()
            
            cat_df['Contention Rate'] = cat_df['Against_Mgmt'] / cat_df['Total_Proposals']
            cat_df = cat_df.sort_values('Total_Proposals', ascending=False).head(5)
            
            st.dataframe(
                cat_df,
                use_container_width=True,
                column_config={
                    "Proposal Code Category": st.column_config.TextColumn("Category"),
                    "Total_Proposals": st.column_config.NumberColumn("Volume", format="%d"),
                    "Against_Mgmt": st.column_config.NumberColumn("Dissent Votes"),
                    "Contention Rate": st.column_config.ProgressColumn("Contention Risk", format="%.1f%%", min_value=0, max_value=1)
                },
                hide_index=True
            )
        else:
            st.info("No Category data available.")

    st.markdown("### Detailed Breakdown")
    tab1, tab2 = st.tabs(["📄 All Proposals (Searchable)", "🏢 Meetings List"])
    
    with tab1:
        display_cols = [c for c in ['Company Name', 'Meeting Date', 'Proposal Text', 'Vote Instruction', 'Vote Against Management'] if c in df.columns]
        st.dataframe(
            df[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Meeting Date": st.column_config.DateColumn("Date"),
                "Vote Against Management": st.column_config.TextColumn("Mgmt Alignment", help="Yes = Voted Against Mgmt"),
            }
        )
        
    with tab2:
        if 'Company Name' in df.columns:
            meeting_summary = df.groupby(['Company Name', 'Country']).size().reset_index(name='Proposals')
            if 'Meeting Date' in df.columns:
                dates = df.groupby('Company Name')['Meeting Date'].max().reset_index()
                meeting_summary = pd.merge(meeting_summary, dates, on='Company Name')
            st.dataframe(meeting_summary, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
