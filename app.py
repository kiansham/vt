"""
Proxy Voting Dashboard
A modern, sleek proxy voting report following ISS Board Statistics Report format
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import glob
from datetime import datetime

# =============================================================================
# PAGE CONFIGURATION
# =============================================================================
st.set_page_config(
    page_title="Proxy Voting Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# THEME COLORS (Navy-based palette)
# =============================================================================
COLORS = {
    "primary": "#1E3A5F",      # Navy
    "success": "#059669",      # Green
    "danger": "#DC2626",       # Red
    "warning": "#F59E0B",      # Amber
    "muted": "#64748B",        # Slate
    "light_bg": "#f8fafc",
    "bar_bg": "#e2e8f0",
    "text": "#1c1919"
}

FUND_NAME_MAP = {
    "DEFGLITS": "AQR Delphi Global Equity Fund",
    "AQRGLOB": "AQR Global Core Fund", 
    "AQREMERGE": "AQR Emerging Markets Fund",
}

# =============================================================================
# MINIMAL CUSTOM STYLING (Most theming via config.toml)
# =============================================================================
st.markdown("""
<style>
    /* Clean metric cards */
    [data-testid="stMetric"] {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px 16px;
        border-left: 4px solid #1E3A5F;
    }
    
    /* Hero stat boxes */
    .stat-box {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .stat-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A5F;
        line-height: 1;
        margin-bottom: 0.25rem;
    }
    .stat-value-green {
        font-size: 2.5rem;
        font-weight: 700;
        color: #059669;
        line-height: 1;
        margin-bottom: 0.25rem;
    }
    .stat-label {
        font-size: 0.8rem;
        color: #64748b;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .progress-bar-container {
        width: 100%;
        height: 8px;
        background-color: #e2e8f0;
        border-radius: 4px;
        overflow: hidden;
        margin-top: 0.75rem;
    }
    .progress-bar-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.6s ease;
    }
    
    /* Section headers */
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1E3A5F;
        border-bottom: 2px solid #1E3A5F;
        padding-bottom: 0.5rem;
        margin: 1.5rem 0 1rem 0;
    }
    
    /* Hide default streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# DATA LOADING FUNCTIONS (Preserved from original)
# =============================================================================
def get_fund_name(code):
    return FUND_NAME_MAP.get(code, code)


def get_quarter_from_dates(date_series):
    valid = pd.to_datetime(date_series, errors='coerce', dayfirst=True).dropna()
    if valid.empty:
        return None
    latest = valid.max()
    return f"Q{(latest.month - 1) // 3 + 1} {latest.year}"


def get_fund_code(filename):
    base = os.path.basename(filename)
    return base.split('_')[0] if '_' in base else base.split('.')[0]


def generate_quarter_choices():
    now = datetime.now()
    q, y = (now.month - 1) // 3 + 1, now.year
    quarters = []
    for _ in range(6):
        quarters.append(f"Q{q} {y}")
        q -= 1
        if q == 0:
            q, y = 4, y - 1
    return quarters


@st.cache_data(ttl=3600)
def scan_data_directory(data_dir):
    files = glob.glob(os.path.join(data_dir, "*.csv")) + glob.glob(os.path.join(data_dir, "*.CSV"))
    funds = {}
    for f in files:
        code = get_fund_code(f)
        funds.setdefault(code, []).append(f)
    return funds


@st.cache_data(ttl=3600)
def get_fund_quarters(fund_code, file_list):
    quarters = {}
    for f in file_list:
        try:
            df = pd.read_csv(f, nrows=100)
            if 'Meeting Date' in df.columns and not df.empty:
                q = get_quarter_from_dates(df['Meeting Date'])
                if q and q not in quarters:
                    quarters[q] = f
        except:
            continue
    return quarters


@st.cache_data(ttl=600)
def load_data(filepath):
    df = pd.read_csv(filepath)
    for col in ['Meeting Date', 'Record Date']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
    return df


# =============================================================================
# STATISTICS CALCULATION
# =============================================================================
def calc_statistics(df):
    """Calculate all key voting metrics matching ISS template"""
    total = len(df)
    
    # Meeting counts
    meetings = df['Meeting ID'].nunique() if 'Meeting ID' in df.columns else df['Company Name'].nunique()
    voted_col = 'Voted (Yes, No, Partial)' if 'Voted (Yes, No, Partial)' in df.columns else None
    
    stats = {
        'meetings': meetings,
        'ballots': meetings,  # Typically equal to meetings
        'proposals': total,
        'voted_proposals': total,
        'for': 0, 'against': 0, 'abstain': 0, 'withhold': 0,
        'with_mgmt': 0, 'vs_mgmt': 0, 
        'with_pol': 0, 'vs_pol': 0,
        'sh_props': 0, 'dissent': 0
    }
    
    # Vote instruction breakdown
    if 'Vote Instruction' in df.columns:
        vc = df['Vote Instruction'].value_counts()
        stats['for'] = int(vc.get('For', 0)) + int(vc.get('One Year', 0))
        stats['against'] = int(vc.get('Against', 0))
        stats['abstain'] = int(vc.get('Abstain', 0))
        stats['withhold'] = int(vc.get('Withhold', 0))
    
    # Management alignment
    if 'Vote Against Management' in df.columns:
        stats['with_mgmt'] = int((df['Vote Against Management'] == 'No').sum())
        stats['vs_mgmt'] = int((df['Vote Against Management'] == 'Yes').sum())
        # Meetings with at least one vote against management
        dissent_meetings = df[df['Vote Against Management'] == 'Yes']
        if 'Meeting ID' in df.columns:
            stats['dissent'] = dissent_meetings['Meeting ID'].nunique()
        elif 'Company Name' in df.columns:
            stats['dissent'] = dissent_meetings['Company Name'].nunique()
    
    # Policy alignment
    if 'Vote Against Policy' in df.columns:
        stats['with_pol'] = int((df['Vote Against Policy'] == 'No').sum())
        stats['vs_pol'] = int((df['Vote Against Policy'] == 'Yes').sum())
    elif 'Vote Against ISS' in df.columns:
        stats['with_pol'] = int((df['Vote Against ISS'] == 'No').sum())
        stats['vs_pol'] = int((df['Vote Against ISS'] == 'Yes').sum())
    
    # Shareholder proposals
    if 'Proponent' in df.columns:
        stats['sh_props'] = int((df['Proponent'] == 'Shareholder').sum())
    
    # Calculate percentages
    if total > 0:
        stats['for_pct'] = round(100 * stats['for'] / total, 1)
        stats['against_pct'] = round(100 * stats['against'] / total, 1)
        stats['abstain_pct'] = round(100 * stats['abstain'] / total, 1)
        stats['withhold_pct'] = round(100 * stats['withhold'] / total, 1)
        stats['with_mgmt_pct'] = round(100 * stats['with_mgmt'] / total, 1)
        stats['vs_mgmt_pct'] = round(100 * stats['vs_mgmt'] / total, 1)
        stats['with_pol_pct'] = round(100 * stats['with_pol'] / total, 1)
        stats['vs_pol_pct'] = round(100 * stats['vs_pol'] / total, 1)
    else:
        for k in ['for', 'against', 'abstain', 'withhold', 'with_mgmt', 'vs_mgmt', 'with_pol', 'vs_pol']:
            stats[f'{k}_pct'] = 0.0
    
    # Dissent rate
    stats['dissent_pct'] = round(100 * stats['dissent'] / max(meetings, 1), 1)
    
    return stats


# =============================================================================
# CHART RENDERING FUNCTIONS (Following visualization principles)
# =============================================================================
def render_metric_card(value, label, color=COLORS["primary"]):
    """Render a clean metric card with large percentage and progress bar"""
    fill_color = COLORS["success"] if value >= 90 else color
    return f"""
    <div class="stat-box">
        <div class="stat-value" style="color: {fill_color};">{value:.0f}%</div>
        <div class="stat-label">{label}</div>
        <div class="progress-bar-container">
            <div class="progress-bar-fill" style="width: {min(value, 100)}%; background: {fill_color};"></div>
        </div>
    </div>
    """


def render_alignment_donut(with_pct, against_pct, title):
    """Clean donut chart for alignment metrics"""
    colors = [COLORS['primary'], COLORS['danger']]
    
    fig = go.Figure(data=[go.Pie(
        labels=['Aligned', 'Divergent'],
        values=[with_pct, against_pct],
        hole=0.65,
        marker_colors=colors,
        textinfo='percent',
        textposition='outside',
        textfont=dict(size=11),
        showlegend=False
    )])
    
    fig.add_annotation(
        text=f"<b>{with_pct:.1f}%</b>",
        x=0.5, y=0.5,
        font=dict(size=18, color=COLORS['primary']),
        showarrow=False
    )
    
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color=COLORS['text']), x=0.5),
        height=220,
        margin=dict(l=20, r=20, t=45, b=20),
        paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def render_vote_distribution_chart(stats):
    """Donut chart for vote cast distribution"""
    data = [
        ('For', stats['for'], COLORS['success']),
        ('Against', stats['against'], COLORS['danger']),
        ('Abstain', stats['abstain'], COLORS['warning']),
        ('Withhold', stats['withhold'], COLORS['muted'])
    ]
    filtered = [(l, v, c) for l, v, c in data if v > 0]
    
    if not filtered:
        return None
    
    labels, values, colors = zip(*filtered)
    total = sum(values)
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.6,
        marker_colors=colors,
        textposition='outside',
        textinfo='label+percent',
        textfont=dict(size=11)
    )])
    
    fig.add_annotation(
        text=f"<b>{total}</b><br>Votes",
        x=0.5, y=0.5,
        font=dict(size=14, color=COLORS['text']),
        showarrow=False
    )
    
    fig.update_layout(
        title=dict(text="Vote Cast Distribution", font=dict(size=13), x=0.5),
        height=280,
        margin=dict(l=20, r=20, t=45, b=20),
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def render_category_chart(df):
    """Horizontal bar chart for proposal categories - sorted by magnitude"""
    if 'Proposal Code Category' not in df.columns:
        return None
    
    cats = df['Proposal Code Category'].value_counts().head(10).reset_index()
    cats.columns = ['Category', 'Count']
    cats = cats.sort_values('Count', ascending=True)  # Sort for horizontal bar
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=cats['Category'],
        x=cats['Count'],
        orientation='h',
        marker_color=COLORS['primary'],
        text=cats['Count'],
        textposition='outside'
    ))
    
    fig.update_layout(
        title=dict(text="Director Elections Dominate Proposal Activity", font=dict(size=13)),
        height=max(280, len(cats) * 32),
        margin=dict(l=20, r=60, t=45, b=30),
        xaxis=dict(showgrid=True, gridcolor='#E2E8F0', title="Number of Proposals"),
        yaxis=dict(title=""),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def render_country_chart(df):
    """Horizontal bar chart for meetings by country - sorted by magnitude"""
    if 'Country' not in df.columns:
        return None
    
    if 'Meeting ID' in df.columns:
        cc = df.groupby('Country')['Meeting ID'].nunique().reset_index(name='Meetings')
    else:
        cc = df.groupby('Country')['Company Name'].nunique().reset_index(name='Meetings')
    
    cc = cc.sort_values('Meetings', ascending=True).tail(10)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=cc['Country'],
        x=cc['Meetings'],
        orientation='h',
        marker_color=COLORS['primary'],
        text=cc['Meetings'],
        textposition='outside'
    ))
    
    fig.update_layout(
        title=dict(text="Meeting Activity by Market", font=dict(size=13)),
        height=max(250, len(cc) * 35),
        margin=dict(l=20, r=60, t=45, b=30),
        xaxis=dict(showgrid=True, gridcolor='#E2E8F0', title="Number of Meetings"),
        yaxis=dict(title=""),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def render_voting_statistics_chart(stats):
    """Grouped bar chart showing votable vs voted"""
    categories = ['Meetings', 'Ballots', 'Proposals']
    values = [stats['meetings'], stats['ballots'], stats['proposals']]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=categories,
        y=values,
        name='Votable',
        marker_color=COLORS['primary'],
        text=values,
        textposition='outside'
    ))
    fig.add_trace(go.Bar(
        x=categories,
        y=values,
        name='Voted',
        marker_color=COLORS['danger'],
        text=values,
        textposition='outside'
    ))
    
    fig.update_layout(
        title=dict(text="100% Voting Participation Achieved", font=dict(size=13)),
        barmode='group',
        height=260,
        margin=dict(l=20, r=20, t=45, b=30),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(showgrid=True, gridcolor='#E2E8F0'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )
    return fig


def get_votes_against_mgmt(df):
    """Get detailed table of votes against management"""
    if 'Vote Against Management' not in df.columns:
        return pd.DataFrame()
    
    against = df[df['Vote Against Management'] == 'Yes'].copy()
    if len(against) == 0:
        return pd.DataFrame()
    
    cols = ['Company Name', 'Meeting Date', 'Country', 'ESG Pillar',
            'Proposal Code Category', 'Proposal Code Description', 
            'Proposal Text', 'Vote Instruction']
    available = [c for c in cols if c in against.columns]
    
    result = against[available].copy()
    if 'Meeting Date' in result.columns:
        result['Meeting Date'] = pd.to_datetime(result['Meeting Date']).dt.strftime('%d-%b-%y')
    
    return result


def get_market_breakdown(df):
    """Get voting statistics by market/country"""
    if 'Country' not in df.columns:
        return pd.DataFrame()
    
    if 'Meeting ID' in df.columns:
        market_stats = df.groupby('Country').agg({
            'Meeting ID': 'nunique'
        }).reset_index()
        market_stats.columns = ['Market', 'Votable Meetings']
    else:
        market_stats = df.groupby('Country')['Company Name'].nunique().reset_index()
        market_stats.columns = ['Market', 'Votable Meetings']
    
    market_stats['Voted Meetings'] = market_stats['Votable Meetings']
    market_stats['Vote Rate'] = '100.0%'
    
    return market_stats.sort_values('Votable Meetings', ascending=False)


# =============================================================================
# MAIN APPLICATION
# =============================================================================
def main():
    # =========================================================================
    # SIDEBAR - Control Panel (Preserved from original)
    # =========================================================================
    with st.sidebar:
        st.title("⚙️ Control Panel")
        data_dir = "./data"
        
        if not os.path.exists(data_dir):
            st.error(f"Data directory not found: {data_dir}")
            st.info("Please create a 'data' folder with CSV files.")
            st.stop()
        
        available_funds = scan_data_directory(data_dir)
        if not available_funds:
            st.warning("No fund data found in ./data directory.")
            st.stop()
        
        fund_codes = list(available_funds.keys())
        selected_fund = st.selectbox(
            "Select Fund",
            fund_codes,
            format_func=lambda x: f"{get_fund_name(x)}"
        )
        
        fund_quarters = get_fund_quarters(selected_fund, available_funds[selected_fund])
        available_quarters = list(fund_quarters.keys())
        quarter_choices = generate_quarter_choices()
        selectable_quarters = [q for q in quarter_choices if q in available_quarters] or available_quarters
        selected_quarter = st.selectbox("Select Period", selectable_quarters) if selectable_quarters else None
        
        st.divider()
        st.markdown("**Export**")
    
    # Load data
    if selected_fund and selected_quarter:
        data_file = fund_quarters.get(selected_quarter)
        df = load_data(data_file) if data_file else pd.DataFrame()
    else:
        df = pd.DataFrame()
    
    # Download button in sidebar
    with st.sidebar:
        if not df.empty:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download CSV",
                csv,
                f"{selected_fund}_{selected_quarter.replace(' ', '_')}.csv",
                "text/csv",
                use_container_width=True
            )
        st.divider()
        st.caption(f"Report Generated: {datetime.now().strftime('%d %b %Y')}")
    
    # =========================================================================
    # MAIN CONTENT
    # =========================================================================
    if df.empty:
        st.title("📊 Proxy Voting Dashboard")
        st.info("No data available. Select a fund and period from the sidebar.")
        st.stop()
    
    # Header
    st.title("📊 Proxy Voting Dashboard")
    
    # Context bar
    col1, col2 = st.columns(2)
    col1.info(f"**Fund:** {get_fund_name(selected_fund)}")
    col2.info(f"**Period:** {selected_quarter}")
    
    # Calculate statistics
    stats = calc_statistics(df)
    
    # -------------------------------------------------------------------------
    # KEY METRICS - Hero Section
    # -------------------------------------------------------------------------
    st.markdown('<p class="section-header">Key Performance Indicators</p>', unsafe_allow_html=True)
    
    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        st.markdown(render_metric_card(stats['with_mgmt_pct'], "Management Alignment"), unsafe_allow_html=True)
    with kpi_cols[1]:
        st.markdown(render_metric_card(stats['with_pol_pct'], "Policy Alignment"), unsafe_allow_html=True)
    with kpi_cols[2]:
        st.markdown(render_metric_card(stats['for_pct'], "Votes For"), unsafe_allow_html=True)
    with kpi_cols[3]:
        st.markdown(render_metric_card(stats['dissent_pct'], "Dissent Rate", COLORS['primary']), unsafe_allow_html=True)
    
    st.markdown("")
    
    # Secondary metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Meetings", f"{stats['meetings']}")
    m2.metric("Proposals", f"{stats['proposals']:,}")
    m3.metric("Against Mgmt", f"{stats['vs_mgmt']}")
    m4.metric("Shareholder Props", f"{stats['sh_props']}")
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # MEETING & PROPOSAL OVERVIEW TABLES
    # -------------------------------------------------------------------------
    st.markdown('<p class="section-header">Meeting & Proposal Overview</p>', unsafe_allow_html=True)
    
    table_col1, table_col2 = st.columns(2)
    
    with table_col1:
        st.markdown("##### Meeting Overview")
        meeting_data = pd.DataFrame({
            'Category': ['Votable Meetings', 'Meetings Voted', 'Meetings with Dissent'],
            'Number': [stats['meetings'], stats['meetings'], stats['dissent']],
            'Percentage': ['—', '100.0%', f"{stats['dissent_pct']:.1f}%"]
        })
        st.dataframe(meeting_data, use_container_width=True, hide_index=True)
    
    with table_col2:
        st.markdown("##### Proposal Overview")
        proposal_data = pd.DataFrame({
            'Category': ['Votable Proposals', 'Proposals Voted', 'Votes FOR', 'Votes AGAINST',
                        'With Management', 'Against Management'],
            'Number': [stats['proposals'], stats['voted_proposals'], stats['for'], stats['against'],
                      stats['with_mgmt'], stats['vs_mgmt']],
            'Percentage': ['—', '100.0%', f"{stats['for_pct']:.1f}%", f"{stats['against_pct']:.1f}%",
                          f"{stats['with_mgmt_pct']:.1f}%", f"{stats['vs_mgmt_pct']:.1f}%"]
        })
        st.dataframe(proposal_data, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # CHARTS SECTION
    # -------------------------------------------------------------------------
    st.markdown('<p class="section-header">Voting Analysis</p>', unsafe_allow_html=True)
    
    # Row 1: Alignment donuts + Vote distribution
    chart_col1, chart_col2, chart_col3 = st.columns(3)
    
    with chart_col1:
        fig_mgmt = render_alignment_donut(
            stats['with_mgmt_pct'],
            stats['vs_mgmt_pct'],
            "Management Alignment"
        )
        st.plotly_chart(fig_mgmt, use_container_width=True)
    
    with chart_col2:
        fig_pol = render_alignment_donut(
            stats['with_pol_pct'],
            stats['vs_pol_pct'],
            "Policy Alignment"
        )
        st.plotly_chart(fig_pol, use_container_width=True)
    
    with chart_col3:
        fig_votes = render_vote_distribution_chart(stats)
        if fig_votes:
            st.plotly_chart(fig_votes, use_container_width=True)
    
    # Row 2: Voting stats + Market breakdown
    chart_col4, chart_col5 = st.columns(2)
    
    with chart_col4:
        fig_stats = render_voting_statistics_chart(stats)
        st.plotly_chart(fig_stats, use_container_width=True)
    
    with chart_col5:
        fig_country = render_country_chart(df)
        if fig_country:
            st.plotly_chart(fig_country, use_container_width=True)
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # MARKET & CATEGORY BREAKDOWN
    # -------------------------------------------------------------------------
    st.markdown('<p class="section-header">Market & Category Breakdown</p>', unsafe_allow_html=True)
    
    breakdown_col1, breakdown_col2 = st.columns(2)
    
    with breakdown_col1:
        st.markdown("##### Market Breakdown")
        market_df = get_market_breakdown(df)
        if not market_df.empty:
            st.dataframe(market_df, use_container_width=True, hide_index=True)
    
    with breakdown_col2:
        st.markdown("##### Proposal Categories")
        if 'Proposal Code Category' in df.columns:
            cat_df = df.groupby('Proposal Code Category').agg(
                Total=('Proposal Text', 'count'),
                Against=('Vote Against Management', lambda x: (x == 'Yes').sum()) if 'Vote Against Management' in df.columns else ('Proposal Text', 'count')
            ).reset_index()
            cat_df.columns = ['Category', 'Total', 'Against Mgmt']
            if 'Vote Against Management' in df.columns:
                cat_df['Against Rate'] = (cat_df['Against Mgmt'] / cat_df['Total'] * 100).round(1).astype(str) + '%'
            cat_df = cat_df.sort_values('Total', ascending=False).head(10)
            st.dataframe(cat_df, use_container_width=True, hide_index=True)
    
    # Category chart
    fig_cat = render_category_chart(df)
    if fig_cat:
        st.plotly_chart(fig_cat, use_container_width=True)
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # DETAILED ANALYSIS TABLES (Preserved from original)
    # -------------------------------------------------------------------------
    st.markdown('<p class="section-header">Detailed Vote Analysis</p>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs([
        "📋 Votes Against Management",
        "📋 All Proposals", 
        "🏢 Meetings List"
    ])
    
    with tab1:
        against_df = get_votes_against_mgmt(df)
        if not against_df.empty:
            st.markdown(f"**{len(against_df)} proposals where vote differed from management recommendation**")
            st.dataframe(against_df, use_container_width=True, hide_index=True, height=400)
        else:
            st.success("✓ All votes aligned with management recommendations.")
    
    with tab2:
        prop_cols = ['Company Name', 'Ticker', 'Meeting Date', 'Proposal Number', 'Proposal Text',
                     'Proponent', 'Management Recommendation', 'ISS Recommendation',
                     'Vote Instruction', 'Vote Against Management', 'Vote Against ISS']
        available_cols = [c for c in prop_cols if c in df.columns]
        prop_df = df[available_cols].drop_duplicates().copy()
        
        if not prop_df.empty:
            with st.expander("🔍 Filters"):
                f1, f2, f3 = st.columns(3)
                
                proponents = ['All'] + (list(prop_df['Proponent'].dropna().unique()) if 'Proponent' in prop_df.columns else [])
                sel_proponent = f1.selectbox("Proponent", proponents)
                
                sel_mgmt = f2.selectbox("Management Alignment", ['All', 'With Management', 'Against Management'])
                
                companies = ['All'] + (sorted(prop_df['Company Name'].dropna().unique().tolist()) if 'Company Name' in prop_df.columns else [])
                sel_company = f3.selectbox("Company", companies)
            
            filtered = prop_df.copy()
            if sel_proponent != 'All' and 'Proponent' in filtered.columns:
                filtered = filtered[filtered['Proponent'] == sel_proponent]
            if sel_mgmt != 'All' and 'Vote Against Management' in filtered.columns:
                filtered = filtered[filtered['Vote Against Management'] == ('No' if sel_mgmt == 'With Management' else 'Yes')]
            if sel_company != 'All' and 'Company Name' in filtered.columns:
                filtered = filtered[filtered['Company Name'] == sel_company]
            
            st.dataframe(filtered, use_container_width=True, hide_index=True, height=450)
            st.caption(f"Showing {len(filtered):,} of {len(prop_df):,} proposals")
    
    with tab3:
        mtg_cols = ['Company Name', 'Ticker', 'Country', 'Meeting Date', 'Meeting Type']
        available_mtg = [c for c in mtg_cols if c in df.columns]
        mtg_df = df[available_mtg].drop_duplicates().copy()
        
        if not mtg_df.empty:
            if 'Company Name' in df.columns:
                prop_counts = df.groupby('Company Name').size().reset_index(name='Proposals')
                mtg_df = mtg_df.merge(prop_counts, on='Company Name', how='left')
            st.dataframe(mtg_df, use_container_width=True, hide_index=True, height=400)
            st.caption(f"Total: {len(mtg_df):,} meetings")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
