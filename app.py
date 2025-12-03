import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import glob
from datetime import datetime

st.set_page_config(page_title="Executive Proxy Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

COLORS = {
    "primary": "#7c3aed",  # Purple
    "success": "#22c55e",
    "danger": "#ef4444",
    "warning": "#f59e0b",
    "muted": "#94a3b8",
    "light_bg": "#f8fafc",
    "bar_bg": "#e2e8f0"
}

FUND_NAME_MAP = {
    "DEFGLITS": "AQR Delphi Global Equity Fund",
    "AQRGLOB": "AQR Global Core Fund",
    "AQREMERGE": "AQR Emerging Markets Fund",
}


def inject_css():
    st.markdown("""
    <style>
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            padding: 15px 20px;
            border-radius: 8px;
        }
        footer { visibility: hidden; }

        /* Clean metric cards */
        .metric-card {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
        }

        .metric-value {
            font-size: 3.5rem;
            font-weight: 700;
            color: #7c3aed;
            line-height: 1;
            margin-bottom: 0.5rem;
        }

        .metric-label {
            font-size: 0.95rem;
            color: #64748b;
            font-weight: 500;
            margin-bottom: 1rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .progress-bar-container {
            width: 100%;
            height: 14px;
            background-color: #e2e8f0;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 1rem;
        }

        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #7c3aed 0%, #a78bfa 100%);
            border-radius: 10px;
            transition: width 0.6s ease;
        }

        .section-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: #1e293b;
            margin: 2rem 0 1rem 0;
        }
    </style>
    """, unsafe_allow_html=True)


def get_fund_name(code):
    return FUND_NAME_MAP.get(code, code)


def get_quarter_from_dates(date_series):
    valid = pd.to_datetime(date_series, errors='coerce').dropna()
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
            df[col] = pd.to_datetime(df[col], errors='coerce', format='mixed')
    return df


def calc_statistics(df):
    total = len(df)
    meetings = df['Company Name'].nunique() if 'Company Name' in df.columns else 0

    stats = {
        'meetings': meetings, 'ballots': meetings, 'proposals': total,
        'for': 0, 'against': 0, 'abstain': 0, 'withhold': 0,
        'with_mgmt': 0, 'vs_mgmt': 0, 'with_pol': 0, 'vs_pol': 0, 'sh_props': 0, 'dissent': 0
    }

    if 'Vote Instruction' in df.columns:
        vc = df['Vote Instruction'].value_counts()
        stats['for'] = int(vc.get('For', 0))
        stats['against'] = int(vc.get('Against', 0))
        stats['abstain'] = int(vc.get('Abstain', 0))
        stats['withhold'] = int(vc.get('Withhold', 0))
        dissent_votes = df[df['Vote Instruction'].isin(['Against', 'Withhold', 'Abstain'])]
        stats['dissent'] = dissent_votes['Company Name'].nunique() if 'Company Name' in df.columns else 0

    if 'Vote Against Management' in df.columns:
        stats['with_mgmt'] = int((df['Vote Against Management'] == 'No').sum())
        stats['vs_mgmt'] = int((df['Vote Against Management'] == 'Yes').sum())

    if 'Vote Against ISS' in df.columns:
        stats['with_pol'] = int((df['Vote Against ISS'] == 'No').sum())
        stats['vs_pol'] = int((df['Vote Against ISS'] == 'Yes').sum())

    if 'Proponent' in df.columns:
        stats['sh_props'] = int((df['Proponent'] == 'Shareholder').sum())

    stats['dissent_pct'] = round(100 * stats['dissent'] / max(meetings, 1), 2)
    for k in ['for', 'against', 'abstain', 'withhold', 'with_mgmt', 'vs_mgmt', 'with_pol', 'vs_pol', 'sh_props']:
        stats[f'{k}_pct'] = round(100 * stats[k] / max(total, 1), 2)

    return stats


def render_metric_card(value, label, color="#7c3aed"):
    """Render a clean metric card with large number and progress bar"""
    html = f"""
    <div class="metric-card">
        <div class="metric-value" style="color: {color};">{value:.0f}%</div>
        <div class="metric-label">{label}</div>
        <div class="progress-bar-container">
            <div class="progress-bar-fill" style="width: {value}%; background: linear-gradient(90deg, {color} 0%, {color}88 100%);"></div>
        </div>
    </div>
    """
    return html


def render_vote_stats_chart(stats):
    cats = ['Meetings', 'Ballots', 'Proposals']
    vals = [stats['meetings'], stats['ballots'], stats['proposals']]
    fig = go.Figure()
    fig.add_trace(go.Bar(name='Votable', y=cats, x=vals, orientation='h', marker_color=COLORS['primary'], text=vals, textposition='inside'))
    fig.add_trace(go.Bar(name='Voted', y=cats, x=vals, orientation='h', marker_color=COLORS['danger'], text=vals, textposition='inside'))
    fig.update_layout(barmode='overlay', height=280, xaxis=dict(type='log'))
    return fig


def render_vote_distribution_chart(stats):
    data = [('For', stats['for'], COLORS['success']), ('Against', stats['against'], COLORS['danger']),
            ('Abstain', stats['abstain'], COLORS['warning']), ('Withhold', stats['withhold'], COLORS['muted'])]
    filtered = [(l, v, c) for l, v, c in data if v > 0]
    if not filtered:
        return None
    labels, values, colors = zip(*filtered)
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.6, marker_colors=colors, textposition='outside', textinfo='label+percent'))
    fig.update_layout(height=320)
    return fig


def render_category_chart(df):
    if 'Proposal Code Category' not in df.columns:
        return None
    cats = df['Proposal Code Category'].value_counts().head(10).reset_index()
    cats.columns = ['Category', 'Count']
    fig = px.bar(cats, x='Count', y='Category', orientation='h', color='Count', color_continuous_scale='teal')
    fig.update_layout(height=320, yaxis={'categoryorder': 'total ascending'}, coloraxis_showscale=False)
    return fig


def render_country_chart(df):
    if 'Country' not in df.columns:
        return None
    cc = df.groupby('Country')['Company Name'].nunique().reset_index(name='Meetings')
    cc = cc.sort_values('Meetings', ascending=False).head(10)
    fig = px.bar(cc, x='Country', y='Meetings', color='Meetings', color_continuous_scale='teal')
    fig.update_layout(height=320, coloraxis_showscale=False)
    return fig


def render_vote_against_rate_chart(df):
    if 'Proposal Code Category' not in df.columns or 'Vote Against Management' not in df.columns:
        return None
    cat_df = df.groupby('Proposal Code Category').agg(
        Total=('Proposal Text', 'count'),
        Against=('Vote Against Management', lambda x: (x == 'Yes').sum())
    ).reset_index()
    cat_df['Vote Against Rate'] = (cat_df['Against'] / cat_df['Total']) * 100
    cat_df = cat_df.sort_values('Vote Against Rate', ascending=True).tail(10)
    fig = px.bar(cat_df, x='Vote Against Rate', y='Proposal Code Category', orientation='h', color='Vote Against Rate', color_continuous_scale='reds')
    fig.update_layout(height=320, coloraxis_showscale=False)
    return fig


def get_table_data(df, cols):
    avail = [c for c in cols if c in df.columns]
    return df[avail].drop_duplicates().copy()


def main():
    inject_css()

    with st.sidebar:
        st.title("⚙️ Control Panel")
        data_dir = "./data"

        if not os.path.exists(data_dir):
            st.error(f"Data directory not found: {data_dir}")
            st.stop()

        available_funds = scan_data_directory(data_dir)
        if not available_funds:
            st.warning("No fund data found.")
            st.stop()

        fund_codes = list(available_funds.keys())
        selected_fund = st.selectbox("Select Fund", fund_codes, format_func=lambda x: f"{get_fund_name(x)} ({x})")

        fund_quarters = get_fund_quarters(selected_fund, available_funds[selected_fund])
        available_quarters = list(fund_quarters.keys())
        quarter_choices = generate_quarter_choices()
        selectable_quarters = [q for q in quarter_choices if q in available_quarters] or available_quarters
        selected_quarter = st.selectbox("Select Period", selectable_quarters) if selectable_quarters else None

        st.markdown("---")
        st.subheader("Export")

    if selected_fund and selected_quarter:
        data_file = fund_quarters.get(selected_quarter)
        df = load_data(data_file) if data_file else pd.DataFrame()
    else:
        df = pd.DataFrame()

    with st.sidebar:
        if not df.empty:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", csv, f"{selected_fund}_{selected_quarter.replace(' ', '_')}.csv", "text/csv", use_container_width=True)

    if df.empty:
        st.title("📊 Proxy Voting Dashboard")
        st.info("No data available. Select a fund and period.")
        st.stop()

    st.title("📊 Proxy Voting Dashboard")
    c1, c2 = st.columns(2)
    c1.info(f"**Fund:** {get_fund_name(selected_fund)}")
    c2.info(f"**Period:** {selected_quarter}")

    stats = calc_statistics(df)

    st.markdown("<div class='section-title'>Key Metrics</div>", unsafe_allow_html=True)

    # Display large metrics with progress bars
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(render_metric_card(stats['with_mgmt_pct'], "Management Alignment", COLORS['primary']), unsafe_allow_html=True)

    with col2:
        st.markdown(render_metric_card(stats['with_pol_pct'], "Policy Alignment", COLORS['primary']), unsafe_allow_html=True)

    with col3:
        st.markdown(render_metric_card(stats['for_pct'], "Votes For", COLORS['primary']), unsafe_allow_html=True)

    st.markdown("")

    # Summary metrics in a cleaner format
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Meetings", f"{stats['meetings']}")
    m2.metric("Proposals", f"{stats['proposals']:,}")
    m3.metric("Against Mgmt", f"{stats['vs_mgmt']}")
    m4.metric("Dissent Rate", f"{stats['dissent_pct']:.1f}%")

    st.markdown("---")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("<div class='section-title'>Vote Distribution</div>", unsafe_allow_html=True)
        donut = render_vote_distribution_chart(stats)
        if donut:
            st.plotly_chart(donut, use_container_width=True)

        st.markdown("<div class='section-title'>Meeting Overview</div>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({
            'Category': ['Total Meetings', 'Meetings Voted', 'Meetings with Dissent'],
            'Count': [stats['meetings'], stats['meetings'], stats['dissent']],
            'Rate': ['—', '100%', f"{stats['dissent_pct']:.1f}%"]
        }), hide_index=True, use_container_width=True)

    with right:
        st.markdown("<div class='section-title'>Proposal Breakdown</div>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({
            'Category': ['Total Proposals', 'Votes FOR', 'Votes AGAINST', 'Votes ABSTAIN',
                        'With Mgmt', 'Against Mgmt', 'With Policy', 'Against Policy'],
            'Count': [stats['proposals'], stats['for'], stats['against'], stats['abstain'],
                      stats['with_mgmt'], stats['vs_mgmt'], stats['with_pol'], stats['vs_pol']],
            'Percentage': ['—', f"{stats['for_pct']:.1f}%", f"{stats['against_pct']:.1f}%", f"{stats['abstain_pct']:.1f}%",
                          f"{stats['with_mgmt_pct']:.1f}%", f"{stats['vs_mgmt_pct']:.1f}%",
                          f"{stats['with_pol_pct']:.1f}%", f"{stats['vs_pol_pct']:.1f}%"]
        }), hide_index=True, use_container_width=True)

    st.markdown("---")
    st.markdown("<div class='section-title'>Analytics</div>", unsafe_allow_html=True)
    c3, c4 = st.columns(2)

    with c3:
        st.markdown("**Proposals by Category**")
        cat_chart = render_category_chart(df)
        if cat_chart:
            st.plotly_chart(cat_chart, use_container_width=True)

    with c4:
        st.markdown("**Meetings by Country**")
        country_chart = render_country_chart(df)
        if country_chart:
            st.plotly_chart(country_chart, use_container_width=True)

    st.markdown("**Vote Against Rate by Category**")
    c5, c6 = st.columns([2, 1])

    with c5:
        var_chart = render_vote_against_rate_chart(df)
        if var_chart:
            st.plotly_chart(var_chart, use_container_width=True)

    with c6:
        if 'Proposal Code Category' in df.columns and 'Vote Against Management' in df.columns:
            cat_df = df.groupby('Proposal Code Category').agg(
                Total_Proposals=('Proposal Text', 'count'),
                Against_Mgmt=('Vote Against Management', lambda x: (x == 'Yes').sum())
            ).reset_index()
            cat_df['Vote Against Rate'] = cat_df['Against_Mgmt'] / cat_df['Total_Proposals']
            cat_df = cat_df.sort_values('Total_Proposals', ascending=False).head(8)
            st.dataframe(cat_df, use_container_width=True, column_config={
                "Proposal Code Category": st.column_config.TextColumn("Category"),
                "Total_Proposals": st.column_config.NumberColumn("Volume"),
                "Against_Mgmt": st.column_config.NumberColumn("Against"),
                "Vote Against Rate": st.column_config.ProgressColumn("Vote Against Rate", format="%.1f%%", min_value=0, max_value=1)
            }, hide_index=True)

    st.markdown("---")
    st.markdown("<div class='section-title'>Detailed Breakdown</div>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["📄 All Proposals", "🏢 Meetings List"])

    with tab1:
        prop_cols = ['Company Name', 'Ticker', 'Meeting Date', 'Proposal Number', 'Proposal Text',
                     'Proponent', 'Management Recommendation', 'ISS Recommendation',
                     'Vote Instruction', 'Vote Against Management', 'Vote Against ISS']
        prop_df = get_table_data(df, prop_cols)

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

    with tab2:
        mtg_cols = ['Company Name', 'Ticker', 'Country', 'Meeting Date', 'Meeting Type']
        mtg_df = get_table_data(df, mtg_cols)
        if not mtg_df.empty:
            if 'Company Name' in df.columns:
                prop_counts = df.groupby('Company Name').size().reset_index(name='Proposals')
                mtg_df = mtg_df.merge(prop_counts, on='Company Name', how='left')
            st.dataframe(mtg_df, use_container_width=True, hide_index=True, height=400)
            st.caption(f"Total: {len(mtg_df):,} meetings")


if __name__ == "__main__":
    main()
