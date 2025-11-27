import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from datetime import datetime
import os
import glob
import time

st.set_page_config(page_title="Proxy Voting Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'selected_fund' not in st.session_state:
    st.session_state.selected_fund = None
if 'selected_quarter' not in st.session_state:
    st.session_state.selected_quarter = None
if 'data_file' not in st.session_state:
    st.session_state.data_file = None

COLORS = {"primary": "#3498db", "success": "#2ecc71", "warning": "#f39c12", "danger": "#e74c3c"}
CB_SAFE_PALETTE = ["#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854"]

FUND_NAME_MAP = {
    "DEFGLITS": "AQR Delphi Global Equity Fund",
    "AQRGLOB": "AQR Global Core Fund",
    "AQREMERGE": "AQR Emerging Markets Fund",
}

def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/icon?family=Material+Icons');
    .material-icons { font-family: 'Material Icons'; font-size: 24px; vertical-align: middle; }
    .main-header { font-size: 2rem; font-weight: 700; color: #2c3e50; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }
    .sub-header { font-size: 1rem; color: #7f8c8d; margin-bottom: 1.5rem; }
    .section-header { font-size: 1.3rem; font-weight: 600; color: #2c3e50; margin: 1.5rem 0 1rem 0; display: flex; align-items: center; gap: 0.5rem; }
    .info-box { background: #f8f9fa; border-left: 4px solid #3498db; padding: 1rem; border-radius: 0 8px 8px 0; margin: 1rem 0; }
    .stProgress > div > div > div > div { background: linear-gradient(90deg, #3498db, #2ecc71); }
    div[data-testid="stSidebar"] { background: linear-gradient(180deg, #2c3e50 0%, #34495e 100%); }
    div[data-testid="stSidebar"] .stSelectbox label { color: white !important; }
    div[data-testid="stSidebar"] p, div[data-testid="stSidebar"] span { color: white !important; }
    .no-meetings { text-align: center; padding: 3rem; background: #f8f9fa; border-radius: 12px; margin: 2rem 0; }
    .no-meetings-icon { font-size: 4rem; color: #bdc3c7; }
    .metric-container { background: white; padding: 1rem; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }
    .sidebar-header { color: white; font-size: 1.5rem; font-weight: 600; margin-bottom: 1rem; }
    </style>
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    """, unsafe_allow_html=True)

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
        if 'Record Date' in df.columns:
            df['Record Date'] = pd.to_datetime(df['Record Date'], errors='coerce')
        return df
    except:
        return pd.DataFrame()

def create_summary_stats(df):
    if df.empty:
        return {}
    stats = {
        "total_meetings": df['Company Name'].nunique() if 'Company Name' in df.columns else 0,
        "total_proposals": len(df),
        "countries": df['Country'].nunique() if 'Country' in df.columns else 0,
    }
    if 'Vote Instruction' in df.columns:
        vote_counts = df['Vote Instruction'].value_counts()
        stats["votes_for"] = vote_counts.get('For', 0)
        stats["votes_against"] = vote_counts.get('Against', 0)
        stats["votes_abstain"] = vote_counts.get('Abstain', 0) + vote_counts.get('Withhold', 0)
    if 'Vote Against Management' in df.columns:
        stats["against_mgmt"] = (df['Vote Against Management'] == 'Yes').sum()
        stats["with_mgmt"] = (df['Vote Against Management'] == 'No').sum()
    return stats

def create_vote_summary_chart(df):
    if df.empty or 'Vote Instruction' not in df.columns:
        return None
    vote_counts = df['Vote Instruction'].value_counts().reset_index()
    vote_counts.columns = ['Vote', 'Count']
    fig = px.pie(vote_counts, values='Count', names='Vote', color='Vote',
                 color_discrete_sequence=CB_SAFE_PALETTE, hole=0.4)
    fig.update_layout(margin=dict(t=30, b=30, l=30, r=30), height=300,
                     legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig

def create_mgmt_alignment_chart(df):
    if df.empty or 'Vote Against Management' not in df.columns:
        return None
    mgmt_counts = df['Vote Against Management'].value_counts().reset_index()
    mgmt_counts.columns = ['Alignment', 'Count']
    mgmt_counts['Alignment'] = mgmt_counts['Alignment'].map({'Yes': 'Against Management', 'No': 'With Management'})
    fig = px.pie(mgmt_counts, values='Count', names='Alignment', color='Alignment',
                 color_discrete_map={'With Management': CB_SAFE_PALETTE[0], 'Against Management': CB_SAFE_PALETTE[1]},
                 hole=0.4)
    fig.update_layout(margin=dict(t=30, b=30, l=30, r=30), height=300,
                     legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig

def create_proposal_category_chart(df):
    if df.empty or 'Proposal Code Category' not in df.columns:
        return None
    cat_counts = df['Proposal Code Category'].value_counts().head(10).reset_index()
    cat_counts.columns = ['Category', 'Count']
    fig = px.bar(cat_counts, x='Count', y='Category', orientation='h', color='Count',
                 color_continuous_scale=[[0, CB_SAFE_PALETTE[0]], [1, CB_SAFE_PALETTE[2]]])
    fig.update_layout(margin=dict(t=30, b=30, l=30, r=30), height=350, showlegend=False,
                     yaxis={'categoryorder': 'total ascending'}, coloraxis_showscale=False,
                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def create_country_chart(df):
    if df.empty or 'Country' not in df.columns:
        return None
    country_counts = df.groupby('Country')['Company Name'].nunique().reset_index()
    country_counts.columns = ['Country', 'Meetings']
    country_counts = country_counts.sort_values('Meetings', ascending=False).head(10)
    fig = px.bar(country_counts, x='Country', y='Meetings', color='Meetings',
                 color_continuous_scale=[[0, CB_SAFE_PALETTE[0]], [1, CB_SAFE_PALETTE[2]]])
    fig.update_layout(margin=dict(t=30, b=30, l=30, r=30), height=350, showlegend=False, coloraxis_showscale=False,
                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def create_meeting_table(df):
    if df.empty:
        return None
    meeting_cols = ['Company Name', 'Ticker', 'Country', 'Meeting Date', 'Meeting Type']
    available_cols = [c for c in meeting_cols if c in df.columns]
    meeting_df = df[available_cols].drop_duplicates()
    if 'Meeting Date' in meeting_df.columns:
        meeting_df = meeting_df.copy()
        meeting_df['Meeting Date'] = meeting_df['Meeting Date'].dt.strftime('%d-%b-%Y')
    return meeting_df

def create_proposal_table(df):
    if df.empty:
        return None
    prop_cols = ['Company Name', 'Ticker', 'Meeting Date', 'Proposal Number', 'Proposal Text', 
                 'Proponent', 'Management Recommendation', 'ISS Recommendation', 'Vote Instruction', 
                 'Vote Against Management', 'Vote Against ISS']
    available_cols = [c for c in prop_cols if c in df.columns]
    prop_df = df[available_cols].copy()
    if 'Meeting Date' in prop_df.columns:
        prop_df['Meeting Date'] = prop_df['Meeting Date'].dt.strftime('%d-%b-%Y')
    return prop_df

def render_aggrid(df, height=400):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, filterable=True, sortable=True, wrapText=True, autoHeight=True)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=15)
    grid_options = gb.build()
    return AgGrid(df, gridOptions=grid_options, height=height, theme='streamlit',
                  update_mode=GridUpdateMode.NO_UPDATE, allow_unsafe_jscode=True)

def render_no_meetings():
    st.markdown("""
    <div class="no-meetings">
        <span class="material-icons no-meetings-icon">event_busy</span>
        <h2 style="color: #7f8c8d; margin-top: 1rem;">No Meetings During This Period</h2>
        <p style="color: #95a5a6;">There were no proxy voting meetings recorded for the selected fund and time period.</p>
    </div>
    """, unsafe_allow_html=True)

def generate_pdf_html(df, fund_name, quarter):
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>Proxy Voting Report - {fund_name}</title>
    <style>
    @media print {{ @page {{ size: A4 landscape; margin: 15mm; }} }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; color: #2c3e50; }}
    .header {{ background: linear-gradient(135deg, #3498db, #2c3e50); color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; }}
    .header h1 {{ margin: 0 0 10px 0; font-size: 28px; }}
    .header-info {{ display: flex; gap: 40px; margin-top: 15px; }}
    .header-info div {{ background: rgba(255,255,255,0.15); padding: 10px 20px; border-radius: 6px; }}
    .header-info label {{ font-size: 12px; opacity: 0.8; display: block; }}
    .header-info span {{ font-size: 16px; font-weight: 600; }}
    .section {{ margin: 25px 0; }}
    .section-title {{ font-size: 18px; font-weight: 600; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-bottom: 15px; }}
    .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }}
    .stat-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #3498db; }}
    .stat-value {{ font-size: 28px; font-weight: 700; color: #3498db; }}
    .stat-label {{ font-size: 12px; color: #7f8c8d; margin-top: 5px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 10px; }}
    th {{ background: #3498db; color: white; padding: 10px 8px; text-align: left; font-weight: 600; }}
    td {{ padding: 8px; border-bottom: 1px solid #ecf0f1; }}
    tr:nth-child(even) {{ background: #f8f9fa; }}
    tr:hover {{ background: #e8f4f8; }}
    .page-break {{ page-break-before: always; }}
    .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ecf0f1; font-size: 11px; color: #95a5a6; text-align: center; }}
    </style></head><body>
    <div class="header">
        <h1>Proxy Voting Report</h1>
        <div class="header-info">
            <div><label>Fund Name</label><span>{fund_name}</span></div>
            <div><label>Reporting Period</label><span>{quarter}</span></div>
            <div><label>Generated</label><span>{datetime.now().strftime('%d %b %Y')}</span></div>
        </div>
    </div>"""
    
    if not df.empty:
        stats = create_summary_stats(df)
        pct_with = round(100 * stats.get('with_mgmt', 0) / max(stats.get('total_proposals', 1), 1), 1)
        html += f"""
        <div class="section">
            <div class="section-title">Summary Statistics</div>
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value">{stats.get('total_meetings', 0)}</div><div class="stat-label">Total Meetings</div></div>
                <div class="stat-card"><div class="stat-value">{stats.get('total_proposals', 0)}</div><div class="stat-label">Total Proposals</div></div>
                <div class="stat-card"><div class="stat-value">{stats.get('countries', 0)}</div><div class="stat-label">Countries</div></div>
                <div class="stat-card"><div class="stat-value">{pct_with}%</div><div class="stat-label">With Management</div></div>
            </div>
        </div>"""
        
        meeting_df = create_meeting_table(df)
        if meeting_df is not None and not meeting_df.empty:
            html += '<div class="section"><div class="section-title">Meeting Details</div>'
            html += meeting_df.to_html(index=False, classes='', border=0)
            html += '</div>'
        
        html += '<div class="page-break"></div>'
        
        prop_df = create_proposal_table(df)
        if prop_df is not None and not prop_df.empty:
            html += '<div class="section"><div class="section-title">Proposal Details</div>'
            html += prop_df.to_html(index=False, classes='', border=0)
            html += '</div>'
    
    html += f'<div class="footer">Generated by Proxy Voting Dashboard | {datetime.now().strftime("%d %b %Y %H:%M")}</div></body></html>'
    return html

def render_landing_page():
    st.markdown("""
    <div style="text-align: center; padding: 4rem 1rem;">
        <div style="font-size: 5rem; margin-bottom: 1rem;">📊</div>
        <h1 style="color: #2c3e50; margin-bottom: 0.5rem;">Proxy Voting Dashboard</h1>
        <p style="color: #7f8c8d; font-size: 1.1rem; max-width: 600px; margin: 0 auto 2rem auto;">
            Select a fund and reporting period from the sidebar, then click <strong>"Load Dashboard"</strong> to view the proxy voting data.
        </p>
    </div>
    """, unsafe_allow_html=True)

def main():
    inject_css()
    
    with st.sidebar:
        st.markdown('<p class="sidebar-header"><span class="material-icons" style="font-size:1.8rem;margin-right:8px;">how_to_vote</span>Proxy Voting</p>', unsafe_allow_html=True)
        st.markdown("---")
        
        data_dir = "/mnt/user-data/uploads"
        
        with st.spinner("Scanning funds..."):
            available_funds = scan_available_funds(data_dir)
        
        if not available_funds:
            st.warning("No fund data found.")
            st.stop()
        
        fund_codes = list(available_funds.keys())
        fund_display = {code: f"{get_fund_display_name(code)} ({code})" for code in fund_codes}
        
        st.markdown('<p style="font-size:0.9rem;margin-bottom:0.5rem;"><span class="material-icons" style="font-size:18px;color:#3498db;">account_balance</span> Select Fund</p>', unsafe_allow_html=True)
        selected_fund = st.selectbox("Fund", fund_codes, format_func=lambda x: fund_display[x], label_visibility="collapsed")
        
        fund_quarters = get_quarters_for_fund(selected_fund, available_funds[selected_fund])
        available_quarters = list(fund_quarters.keys())
        last_6 = generate_last_6_quarters()
        selectable_quarters = [q for q in last_6 if q in available_quarters]
        
        st.markdown('<p style="font-size:0.9rem;margin-bottom:0.5rem;margin-top:1rem;"><span class="material-icons" style="font-size:18px;color:#3498db;">date_range</span> Select Period</p>', unsafe_allow_html=True)
        
        selected_quarter = None
        data_file = None
        
        if selectable_quarters:
            selected_quarter = st.selectbox("Quarter", selectable_quarters, label_visibility="collapsed")
            data_file = fund_quarters.get(selected_quarter)
        elif available_quarters:
            st.warning("No data for recent quarters")
            selected_quarter = st.selectbox("Quarter (Historical)", available_quarters, label_visibility="collapsed")
            data_file = fund_quarters.get(selected_quarter)
        else:
            st.error("No quarter data available")
        
        st.markdown("---")
        
        load_clicked = st.button("📂 Load Dashboard", use_container_width=True, type="primary")
        
        if load_clicked and selected_fund and selected_quarter and data_file:
            st.session_state.data_loaded = True
            st.session_state.selected_fund = selected_fund
            st.session_state.selected_quarter = selected_quarter
            st.session_state.data_file = data_file
            st.rerun()
        
        if st.session_state.data_loaded:
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.data_loaded = False
                st.session_state.selected_fund = None
                st.session_state.selected_quarter = None
                st.session_state.data_file = None
                st.rerun()
        
        st.markdown("---")
        st.markdown('<p style="font-size:0.85rem;"><span class="material-icons" style="font-size:16px;color:#2ecc71;">info</span> Data Summary</p>', unsafe_allow_html=True)
        st.caption(f"Available Funds: {len(fund_codes)}")
        st.caption(f"Quarters for {selected_fund}: {len(available_quarters)}")
        if available_quarters:
            st.caption(f"Available: {', '.join(available_quarters)}")
    
    if not st.session_state.data_loaded:
        render_landing_page()
        st.stop()
    
    selected_fund = st.session_state.selected_fund
    selected_quarter = st.session_state.selected_quarter
    data_file = st.session_state.data_file
    fund_display_name = get_fund_display_name(selected_fund)
    
    st.markdown(f'<h1 class="main-header"><span class="material-icons" style="color:#3498db;font-size:2rem;">assessment</span>Proxy Voting Report</h1>', unsafe_allow_html=True)
    
    col_info1, col_info2, col_info3 = st.columns([2, 2, 1])
    with col_info1:
        st.markdown(f'<div class="info-box"><span class="material-icons" style="color:#3498db;font-size:18px;">business</span> <strong>Fund Name:</strong> {fund_display_name}</div>', unsafe_allow_html=True)
    with col_info2:
        st.markdown(f'<div class="info-box"><span class="material-icons" style="color:#3498db;font-size:18px;">event</span> <strong>Reporting Period:</strong> {selected_quarter if selected_quarter else "N/A"}</div>', unsafe_allow_html=True)
    
    if data_file is None:
        render_no_meetings()
        st.stop()
    
    progress = st.progress(0)
    status = st.empty()
    
    status.text("Loading data...")
    progress.progress(30)
    time.sleep(0.2)
    
    df = load_data(data_file)
    progress.progress(60)
    
    if df.empty:
        progress.progress(100)
        status.empty()
        progress.empty()
        render_no_meetings()
        st.stop()
    
    status.text("Processing statistics...")
    progress.progress(80)
    time.sleep(0.15)
    
    stats = create_summary_stats(df)
    progress.progress(100)
    time.sleep(0.1)
    status.empty()
    progress.empty()
    
    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">analytics</span>Summary Statistics</h2>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Total Meetings", value=stats.get('total_meetings', 0))
    with col2:
        st.metric(label="Total Proposals", value=stats.get('total_proposals', 0))
    with col3:
        st.metric(label="Countries", value=stats.get('countries', 0))
    with col4:
        pct_with = round(100 * stats.get('with_mgmt', 0) / max(stats.get('total_proposals', 1), 1), 1)
        st.metric(label="With Management", value=f"{pct_with}%")
    
    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">pie_chart</span>Vote Distribution</h2>', unsafe_allow_html=True)
    
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("**Vote Instructions**")
        vote_chart = create_vote_summary_chart(df)
        if vote_chart:
            st.plotly_chart(vote_chart, use_container_width=True)
    with chart_col2:
        st.markdown("**Management Alignment**")
        mgmt_chart = create_mgmt_alignment_chart(df)
        if mgmt_chart:
            st.plotly_chart(mgmt_chart, use_container_width=True)
    
    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">category</span>Proposal Categories & Geography</h2>', unsafe_allow_html=True)
    
    chart_col3, chart_col4 = st.columns(2)
    with chart_col3:
        st.markdown("**Top Proposal Categories**")
        cat_chart = create_proposal_category_chart(df)
        if cat_chart:
            st.plotly_chart(cat_chart, use_container_width=True)
    with chart_col4:
        st.markdown("**Meetings by Country**")
        country_chart = create_country_chart(df)
        if country_chart:
            st.plotly_chart(country_chart, use_container_width=True)
    
    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">event</span>Meeting Details</h2>', unsafe_allow_html=True)
    
    meeting_df = create_meeting_table(df)
    if meeting_df is not None and not meeting_df.empty:
        render_aggrid(meeting_df, height=350)
    
    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">ballot</span>Proposal Details</h2>', unsafe_allow_html=True)
    
    prop_df = create_proposal_table(df)
    if prop_df is not None and not prop_df.empty:
        with st.expander("Filter Options", expanded=False):
            filter_col1, filter_col2, filter_col3 = st.columns(3)
            with filter_col1:
                proponents = ['All'] + list(prop_df['Proponent'].dropna().unique()) if 'Proponent' in prop_df.columns else ['All']
                sel_proponent = st.selectbox("Proponent", proponents)
            with filter_col2:
                mgmt_filter = st.selectbox("Management Alignment", ['All', 'With Management', 'Against Management'])
            with filter_col3:
                companies = ['All'] + sorted(prop_df['Company Name'].dropna().unique().tolist()) if 'Company Name' in prop_df.columns else ['All']
                sel_company = st.selectbox("Company", companies)
        
        filtered_df = prop_df.copy()
        if sel_proponent != 'All' and 'Proponent' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Proponent'] == sel_proponent]
        if mgmt_filter != 'All' and 'Vote Against Management' in filtered_df.columns:
            val = 'No' if mgmt_filter == 'With Management' else 'Yes'
            filtered_df = filtered_df[filtered_df['Vote Against Management'] == val]
        if sel_company != 'All' and 'Company Name' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Company Name'] == sel_company]
        
        render_aggrid(filtered_df, height=500)
    
    st.markdown("---")
    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">download</span>Export Report</h2>', unsafe_allow_html=True)
    
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Full Data (CSV)",
            data=csv_data,
            file_name=f"{selected_fund}_{selected_quarter.replace(' ', '_')}_voting_data.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col_dl2:
        html_content = generate_pdf_html(df, fund_display_name, selected_quarter)
        st.download_button(
            label="Download Report (HTML/PDF)",
            data=html_content.encode('utf-8'),
            file_name=f"{selected_fund}_{selected_quarter.replace(' ', '_')}_report.html",
            mime="text/html",
            use_container_width=True,
            help="Open in browser and use Print > Save as PDF"
        )

if __name__ == "__main__":
    main()
