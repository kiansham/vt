import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import glob
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Executive Proxy Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Brand Palette
COLORS = {
    "primary": "#0f172a",    # Dark Navy
    "accent": "#3b82f6",     # Bright Blue
    "success": "#22c55e",    # Green
    "danger": "#ef4444",     # Red
    "warning": "#f59e0b",    # Orange
    "background": "#f8fafc"  # Light Grey
}

def inject_css():
    st.markdown("""
    <style>
        /* Modern Clean Look */
        .block-container { padding-top: 1rem; padding-bottom: 3rem; }
        
        /* Metric Cards Styling */
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        }
        div[data-testid="stMetric"] label { font-size: 0.85rem; color: #64748b; }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #0f172a; }
        
        /* Sidebar Styling */
        section[data-testid="stSidebar"] { background-color: #f8fafc; border-right: 1px solid #e2e8f0; }
        
        /* Headers */
        h1, h2, h3 { font-family: 'Inter', sans-serif; letter-spacing: -0.5px; }
        h1 { font-weight: 800; color: #0f172a; font-size: 2.2rem; }
        h3 { font-weight: 600; color: #334155; font-size: 1.2rem; margin-top: 1rem; }
        
        /* Remove default footer */
        footer { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. DATA LOADING LOGIC (PRESERVED)
# -----------------------------------------------------------------------------
FUND_NAME_MAP = {
    "DEFGLITS": "AQR Delphi Global Equity Fund",
    "AQRGLOB": "AQR Global Core Fund",
    "AQREMERGE": "AQR Emerging Markets Fund",
}

def get_fund_display_name(fund_code):
    return FUND_NAME_MAP.get(fund_code, fund_code)

def get_quarter_from_date(date_series):
    if date_series.empty:
        return None
    valid_dates = pd.to_datetime(date_series, errors='coerce').dropna()
    if valid_dates.empty:
        return None
    most_recent = valid_dates.max()
    quarter = (most_recent.month - 1) // 3 + 1
    return f"Q{quarter} {most_recent.year}"

def extract_fund_code(filename):
    base = os.path.basename(filename)
    return base.split('_')[0] if '_' in base else base.split('.')[0]

def generate_last_6_quarters():
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
def scan_available_funds(data_dir):
    # Ensure directory exists to prevent crash
    if not os.path.exists(data_dir):
        return {}
    
    files = glob.glob(os.path.join(data_dir, "*.csv")) + glob.glob(os.path.join(data_dir, "*.CSV"))
    funds = {}
    for f in files:
        fund_code = extract_fund_code(f)
        if fund_code not in funds:
            funds[fund_code] = []
        funds[fund_code].append(f)
    return funds

@st.cache_data(ttl=3600)
def get_quarters_for_fund(fund_code, file_list):
    quarters = {}
    for f in file_list:
        try:
            df = pd.read_csv(f, nrows=100)
            if 'Meeting Date' in df.columns and not df.empty:
                q = get_quarter_from_date(df['Meeting Date'])
                if q and q not in quarters:
                    quarters[q] = f
        except:
            continue
    return quarters

@st.cache_data(ttl=600)
def load_data(filepath):
    try:
        df = pd.read_csv(filepath)
        if df.empty or len(df) == 0:
            return pd.DataFrame()
        if 'Meeting Date' in df.columns:
            df['Meeting Date'] = pd.to_datetime(df['Meeting Date'], errors='coerce')
        return df
    except:
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# 3. KPI & CHART LOGIC (REFACTORED)
# -----------------------------------------------------------------------------
def calculate_kpis(df):
    """Generates metrics for the 'Golden Corner'."""
    if df.empty:
        return None
        
    stats = {}
    
    # 1. Meetings Voted
    stats['meetings'] = df['Company Name'].nunique() if 'Company Name' in df.columns else 0
    
    # 2. Total Votes Cast
    stats['total_votes'] = len(df)
    
    # 3. Management Alignment
    if 'Vote Against Management' in df.columns:
        # Assuming 'No' means aligned with management (i.e. did not vote against)
        with_mgmt = (df['Vote Against Management'] == 'No').sum()
        stats['mgmt_alignment_pct'] = (with_mgmt / len(df)) * 100
    else:
        stats['mgmt_alignment_pct'] = 0

    # 4. Dissent/Risk (Against or Withhold)
    if 'Vote Instruction' in df.columns:
        dissent_votes = df[df['Vote Instruction'].isin(['Against', 'Withhold', 'Do Not Vote'])]
        stats['dissent_count'] = len(dissent_votes)
        stats['dissent_pct'] = (len(dissent_votes) / len(df)) * 100
    else:
        stats['dissent_count'] = 0
        stats['dissent_pct'] = 0
        
    return stats

def render_smart_distribution_chart(df):
    """
    Switches between Donut and Stacked Bar based on data skew.
    """
    if df.empty or 'Vote Instruction' not in df.columns:
        return None

    counts = df['Vote Instruction'].value_counts()
    # Filter out zeros
    counts = counts[counts > 0]
    
    total = counts.sum()
    for_votes = counts.get('For', 0)
    for_pct = (for_votes / total) * 100 if total > 0 else 0
    
    data = counts.reset_index()
    data.columns = ['Vote', 'Count']

    # Color mapping
    color_map = {
        "For": COLORS['success'], 
        "Against": COLORS['danger'], 
        "Abstain": COLORS['warning'], 
        "Withhold": COLORS['primary']
    }

    # LOGIC: If > 95% is "For", use a horizontal stacked bar to save vertical space
    if for_pct > 95:
        fig = px.bar(
            data, x='Count', y='Vote', orientation='h', 
            text='Count', color='Vote', 
            color_discrete_map=color_map,
            title=f"Distribution (Strongly 'For': {for_pct:.1f}%)"
        )
        fig.update_layout(showlegend=False, height=250, margin=dict(l=0, r=0, t=40, b=0))
    else:
        # Otherwise use a clean Donut chart
        fig = px.pie(
            data, values='Count', names='Vote', hole=0.6,
            color='Vote', color_discrete_map=color_map,
        )
        fig.update_layout(
            height=300, 
            margin=dict(l=20, r=20, t=0, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
        )
        fig.update_traces(textposition='outside', textinfo='percent+label')
        
    return fig

# -----------------------------------------------------------------------------
# 4. MAIN APP LAYOUT
# -----------------------------------------------------------------------------
def main():
    inject_css()
    
    # --- Sidebar: Data Selection & Export ---
    with st.sidebar:
        st.title("⚙️ Control Panel")
        
        # Path configuration (Fallback to ./data if absolute path fails)
        data_dir = "./data"
        if not os.path.exists(data_dir):
            # Try the prompt's path if local data doesn't exist
            data_dir = "/mnt/user-data/uploads"
            
        # Scan Logic
        available_funds = scan_available_funds(data_dir)
        
        if not available_funds:
            st.warning(f"No CSV files found in `{data_dir}`.")
            st.stop()
            
        fund_codes = list(available_funds.keys())
        fund_display = {code: f"{get_fund_display_name(code)}" for code in fund_codes}
        
        selected_fund = st.selectbox(
            "Select Fund", 
            fund_codes, 
            format_func=lambda x: fund_display[x]
        )
        
        # Quarter Logic
        fund_quarters = get_quarters_for_fund(selected_fund, available_funds[selected_fund])
        available_quarters = list(fund_quarters.keys())
        last_6 = generate_last_6_quarters()
        selectable_quarters = [q for q in last_6 if q in available_quarters]
        
        # Fallback if no recent data
        if not selectable_quarters:
            selectable_quarters = available_quarters
            
        selected_quarter = st.selectbox("Select Quarter", selectable_quarters) if selectable_quarters else None
        
        st.markdown("---")
        
        # Load Logic
        if selected_fund and selected_quarter:
            data_file = fund_quarters.get(selected_quarter)
            df = load_data(data_file)
        else:
            df = pd.DataFrame()

        # Export Buttons moved to Sidebar
        if not df.empty:
            st.subheader("📥 Export Reports")
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "Download CSV Data",
                csv,
                f"{selected_fund}_{selected_quarter}.csv",
                "text/csv",
                use_container_width=True
            )
            st.caption("Generate PDF via Print > Save as PDF in browser.")

    # --- Main Canvas ---
    
    # 1. Header
    if df.empty:
        st.markdown("### 👈 Please select a Fund and Quarter to begin.")
        st.info("No data loaded or file is empty.")
        st.stop()

    st.title(f"Proxy Voting Dashboard: {selected_quarter}")
    st.caption(f"Fund: {get_fund_display_name(selected_fund)} | Source: {os.path.basename(data_file)}")
    
    # 2. The "Golden Corner" (KPI Row)
    kpis = calculate_kpis(df)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Meetings Voted", 
            f"{kpis['meetings']}", 
            delta="100% Complete",
            delta_color="normal"
        )
    with col2:
        st.metric(
            "Votes Cast", 
            f"{kpis['total_votes']:,}"
        )
    with col3:
        # Green if alignment > 90%
        val = kpis['mgmt_alignment_pct']
        st.metric(
            "Mgmt Alignment", 
            f"{val:.1f}%", 
            delta="Target > 90%" if val > 90 else "Below Target",
            delta_color="normal" if val > 90 else "inverse"
        )
    with col4:
        # Red if dissent > 0
        dissent = kpis['dissent_count']
        st.metric(
            "Dissent / Risk", 
            f"{dissent}", 
            delta=f"{kpis['dissent_pct']:.1f}% of total",
            delta_color="inverse"
        )

    st.markdown("---")

    # 3. Visualization Row
    c1, c2 = st.columns([1, 2])
    
    with c1:
        st.subheader("Vote Distribution")
        fig_dist = render_smart_distribution_chart(df)
        if fig_dist:
            st.plotly_chart(fig_dist, use_container_width=True)
            
    with c2:
        st.subheader("Category Breakdown")
        if 'Proposal Code Category' in df.columns:
            # Create a summary dataframe for the visualization
            cat_df = df.groupby('Proposal Code Category').agg(
                Total_Proposals=('Proposal Text', 'count'),
                Against_Mgmt=('Vote Against Management', lambda x: (x == 'Yes').sum())
            ).reset_index()
            
            # Calculate % for the progress bar
            cat_df['Contention Rate'] = cat_df['Against_Mgmt'] / cat_df['Total_Proposals']
            cat_df = cat_df.sort_values('Total_Proposals', ascending=False).head(5)
            
            st.dataframe(
                cat_df,
                use_container_width=True,
                column_config={
                    "Proposal Code Category": st.column_config.TextColumn("Category"),
                    "Total_Proposals": st.column_config.NumberColumn("Volume", format="%d"),
                    "Against_Mgmt": st.column_config.NumberColumn("Dissent Votes"),
                    "Contention Rate": st.column_config.ProgressColumn(
                        "Contention Risk",
                        format="%.1f%%",
                        min_value=0,
                        max_value=1,
                    )
                },
                hide_index=True
            )
        else:
            st.info("No Category data available.")

    # 4. Detailed Breakdown (Tabs)
    st.markdown("### Detailed Breakdown")
    
    tab1, tab2 = st.tabs(["📄 All Proposals (Searchable)", "🏢 Meetings List"])
    
    with tab1:
        # Prepare clean dataframe for display
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
        # Group by Meeting
        if 'Company Name' in df.columns:
            meeting_summary = df.groupby(['Company Name', 'Country']).size().reset_index(name='Proposals')
            if 'Meeting Date' in df.columns:
                dates = df.groupby('Company Name')['Meeting Date'].max().reset_index()
                meeting_summary = pd.merge(meeting_summary, dates, on='Company Name')
                
            st.dataframe(
                meeting_summary, 
                use_container_width=True,
                hide_index=True
            )

if __name__ == "__main__":
    main()
