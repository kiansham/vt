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
if 'sel_fund' not in st.session_state:
    st.session_state.sel_fund = None
if 'sel_qtr' not in st.session_state:
    st.session_state.sel_qtr = None
if 'data_file' not in st.session_state:
    st.session_state.data_file = None

COLORS = {"primary": "#3498db", "success": "#2ecc71", "warning": "#f39c12", "danger": "#e74c3c"}
CB_PALETTE = ["#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854"]

FUND_MAP = {
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

def get_name(code):
    return FUND_MAP.get(code, code)

def get_qtr(date_series):
    if date_series.empty:
        return None
    valid = pd.to_datetime(date_series, errors='coerce').dropna()
    if valid.empty:
        return None
    latest = valid.max()
    q = (latest.month - 1) // 3 + 1
    return f"Q{q} {latest.year}"

def get_code(filename):
    base = os.path.basename(filename)
    return base.split('_')[0] if '_' in base else base.split('.')[0]

def gen_quarters():
    now = datetime.now()
    qtrs = []
    q = (now.month - 1) // 3 + 1
    y = now.year
    for _ in range(6):
        qtrs.append(f"Q{q} {y}")
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    return qtrs

@st.cache_data(ttl=3600)
def scan_funds(data_dir):
    files = glob.glob(os.path.join(data_dir, "*.csv")) + glob.glob(os.path.join(data_dir, "*.CSV"))
    funds = {}
    for f in files:
        code = get_code(f)
        if code not in funds:
            funds[code] = []
        funds[code].append(f)
    return funds

@st.cache_data(ttl=3600)
def get_qtrs(code, files):
    qtrs = {}
    for f in files:
        try:
            df = pd.read_csv(f, nrows=100)
            if 'Meeting Date' in df.columns and not df.empty:
                q = get_qtr(df['Meeting Date'])
                if q and q not in qtrs:
                    qtrs[q] = f
        except:
            continue
    return qtrs

@st.cache_data(ttl=600)
def load_data(filepath):
    try:
        df = pd.read_csv(filepath)
        if df.empty:
            return pd.DataFrame()
        if 'Meeting Date' in df.columns:
            df['Meeting Date'] = pd.to_datetime(df['Meeting Date'], errors='coerce', format='mixed')
        if 'Record Date' in df.columns:
            df['Record Date'] = pd.to_datetime(df['Record Date'], errors='coerce', format='mixed')
        return df
    except:
        return pd.DataFrame()

def calc_stats(df):
    if df.empty:
        return {}
    stats = {
        "meetings": df['Company Name'].nunique() if 'Company Name' in df.columns else 0,
        "proposals": len(df),
        "countries": df['Country'].nunique() if 'Country' in df.columns else 0,
    }
    if 'Vote Instruction' in df.columns:
        vc = df['Vote Instruction'].value_counts()
        stats["for"] = vc.get('For', 0)
        stats["against"] = vc.get('Against', 0)
        stats["abstain"] = vc.get('Abstain', 0) + vc.get('Withhold', 0)
    if 'Vote Against Management' in df.columns:
        stats["vs_mgmt"] = (df['Vote Against Management'] == 'Yes').sum()
        stats["with_mgmt"] = (df['Vote Against Management'] == 'No').sum()
    return stats

def calc_mtg(df):
    if df.empty:
        return {}
    total = df['Company Name'].nunique() if 'Company Name' in df.columns else 0
    dissent = 0
    if 'Company Name' in df.columns and 'Vote Instruction' in df.columns:
        dis_votes = df[df['Vote Instruction'].isin(['Against', 'Withhold', 'Abstain'])]
        dissent = dis_votes['Company Name'].nunique()
    return {
        'votable': total,
        'voted': total,
        'dissent': dissent,
        'dissent_pct': round(100 * dissent / max(total, 1), 2)
    }

def calc_ballot(df):
    if df.empty:
        return {}
    total = df['Company Name'].nunique() if 'Company Name' in df.columns else 0
    return {'votable': total, 'voted': total}

def calc_props(df):
    if df.empty:
        return {}
    total = len(df)
    stats = {
        'votable': total, 'voted': total,
        'for': 0, 'against': 0, 'abstain': 0, 'withhold': 0,
        'msop_1': 0, 'msop_2': 0, 'msop_3': 0,
        'with_pol': 0, 'vs_pol': 0,
        'with_mgmt': 0, 'vs_mgmt': 0,
        'msop_ex': 0, 'sh_props': 0
    }

    if 'Vote Instruction' in df.columns:
        vc = df['Vote Instruction'].value_counts()
        stats['for'] = int(vc.get('For', 0))
        stats['against'] = int(vc.get('Against', 0))
        stats['abstain'] = int(vc.get('Abstain', 0))
        stats['withhold'] = int(vc.get('Withhold', 0))

    if 'Vote Against Management' in df.columns:
        stats['with_mgmt'] = int((df['Vote Against Management'] == 'No').sum())
        stats['vs_mgmt'] = int((df['Vote Against Management'] == 'Yes').sum())

    if 'Vote Against ISS' in df.columns:
        stats['with_pol'] = int((df['Vote Against ISS'] == 'No').sum())
        stats['vs_pol'] = int((df['Vote Against ISS'] == 'Yes').sum())

    if 'Proponent' in df.columns:
        stats['sh_props'] = int((df['Proponent'] == 'Shareholder').sum())

    for k in list(stats.keys()):
        if k not in ['votable', 'voted', 'msop_1', 'msop_2', 'msop_3', 'msop_ex']:
            stats[k + '_pct'] = round(100 * stats[k] / max(total, 1), 2)

    return stats

def chart_vote_stats(m, b, p):
    cats = ['Meetings', 'Ballots', 'Proposals']
    votable = [m.get('votable', 0), b.get('votable', 0), p.get('votable', 0)]
    voted = [m.get('voted', 0), b.get('voted', 0), p.get('voted', 0)]

    fig = go.Figure()
    fig.add_trace(go.Bar(name='Votable', y=cats, x=votable, orientation='h',
                         marker=dict(color='#34495e'), text=votable,
                         textposition='inside', textfont=dict(color='white')))
    fig.add_trace(go.Bar(name='Voted', y=cats, x=voted, orientation='h',
                         marker=dict(color='#e74c3c'), text=voted,
                         textposition='inside', textfont=dict(color='white')))

    fig.update_layout(barmode='overlay', height=300,
                     margin=dict(t=30, b=30, l=80, r=30),
                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                     legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                     xaxis=dict(type='log', showgrid=True, gridcolor='#ecf0f1'))
    return fig

def chart_donut(p):
    labels, values, colors = [], [], []
    data = [
        ('Votes For', p.get('for', 0), '#34495e'),
        ('Votes Abstain', p.get('abstain', 0), '#9b59b6'),
        ('Votes Withhold', p.get('withhold', 0), '#a29bfe'),
        ('Votes Against', p.get('against', 0), '#dfe6e9'),
        ('Votes MSOP 1 Year', p.get('msop_1', 0), '#e74c3c'),
        ('Votes MSOP 2 Years', p.get('msop_2', 0), '#ff7675'),
        ('Votes MSOP 3 Years', p.get('msop_3', 0), '#fd79a8')
    ]

    for label, value, color in data:
        if value > 0:
            labels.append(label)
            values.append(value)
            colors.append(color)

    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.5,
                                 marker=dict(colors=colors),
                                 textposition='outside', textinfo='label+percent')])

    fig.update_layout(height=400, margin=dict(t=30, b=30, l=30, r=30),
                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                     showlegend=True,
                     legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.1))
    return fig

def chart_cats(df):
    if df.empty or 'Proposal Code Category' not in df.columns:
        return None
    cats = df['Proposal Code Category'].value_counts().head(10).reset_index()
    cats.columns = ['Category', 'Count']
    fig = px.bar(cats, x='Count', y='Category', orientation='h', color='Count',
                 color_continuous_scale=[[0, CB_PALETTE[0]], [1, CB_PALETTE[2]]])
    fig.update_layout(margin=dict(t=30, b=30, l=30, r=30), height=350, showlegend=False,
                     yaxis={'categoryorder': 'total ascending'}, coloraxis_showscale=False,
                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def chart_country(df):
    if df.empty or 'Country' not in df.columns:
        return None
    cc = df.groupby('Country')['Company Name'].nunique().reset_index()
    cc.columns = ['Country', 'Meetings']
    cc = cc.sort_values('Meetings', ascending=False).head(10)
    fig = px.bar(cc, x='Country', y='Meetings', color='Meetings',
                 color_continuous_scale=[[0, CB_PALETTE[0]], [1, CB_PALETTE[2]]])
    fig.update_layout(margin=dict(t=30, b=30, l=30, r=30), height=350, showlegend=False,
                     coloraxis_showscale=False,
                     paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def mtg_table(df):
    if df.empty:
        return None
    cols = ['Company Name', 'Ticker', 'Country', 'Meeting Date', 'Meeting Type']
    avail = [c for c in cols if c in df.columns]
    tbl = df[avail].drop_duplicates()
    if 'Meeting Date' in tbl.columns:
        tbl = tbl.copy()
        tbl['Meeting Date'] = tbl['Meeting Date'].dt.strftime('%d-%b-%Y')
    return tbl

def prop_table(df):
    if df.empty:
        return None
    cols = ['Company Name', 'Ticker', 'Meeting Date', 'Proposal Number', 'Proposal Text',
            'Proponent', 'Management Recommendation', 'ISS Recommendation', 'Vote Instruction',
            'Vote Against Management', 'Vote Against ISS']
    avail = [c for c in cols if c in df.columns]
    tbl = df[avail].copy()
    if 'Meeting Date' in tbl.columns:
        tbl['Meeting Date'] = tbl['Meeting Date'].dt.strftime('%d-%b-%Y')
    return tbl

def render_grid(df, height=400):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, filterable=True, sortable=True, wrapText=True, autoHeight=True)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=15)
    opts = gb.build()
    return AgGrid(df, gridOptions=opts, height=height, theme='streamlit',
                  update_mode=GridUpdateMode.NO_UPDATE, allow_unsafe_jscode=True)

def no_mtgs():
    st.markdown("""
    <div class="no-meetings">
        <span class="material-icons no-meetings-icon">event_busy</span>
        <h2 style="color: #7f8c8d; margin-top: 1rem;">No Meetings During This Period</h2>
        <p style="color: #95a5a6;">There were no proxy voting meetings recorded for the selected fund and time period.</p>
    </div>
    """, unsafe_allow_html=True)

def gen_pdf(df, code, qtr):
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>Proxy Voting Report - {code}</title>
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
            <div><label>Fund</label><span>{code}</span></div>
            <div><label>Period</label><span>{qtr}</span></div>
            <div><label>Generated</label><span>{datetime.now().strftime('%d %b %Y')}</span></div>
        </div>
    </div>"""

    if not df.empty:
        stats = calc_stats(df)
        pct = round(100 * stats.get('with_mgmt', 0) / max(stats.get('proposals', 1), 1), 1)
        html += f"""
        <div class="section">
            <div class="section-title">Summary Statistics</div>
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value">{stats.get('meetings', 0)}</div><div class="stat-label">Total Meetings</div></div>
                <div class="stat-card"><div class="stat-value">{stats.get('proposals', 0)}</div><div class="stat-label">Total Proposals</div></div>
                <div class="stat-card"><div class="stat-value">{stats.get('countries', 0)}</div><div class="stat-label">Countries</div></div>
                <div class="stat-card"><div class="stat-value">{pct}%</div><div class="stat-label">With Management</div></div>
            </div>
        </div>"""

        mtg_df = mtg_table(df)
        if mtg_df is not None and not mtg_df.empty:
            html += '<div class="section"><div class="section-title">Meeting Details</div>'
            html += mtg_df.to_html(index=False, classes='', border=0)
            html += '</div>'

        html += '<div class="page-break"></div>'

        prop_df = prop_table(df)
        if prop_df is not None and not prop_df.empty:
            html += '<div class="section"><div class="section-title">Proposal Details</div>'
            html += prop_df.to_html(index=False, classes='', border=0)
            html += '</div>'

    html += f'<div class="footer">Generated by Proxy Voting Dashboard | {datetime.now().strftime("%d %b %Y %H:%M")}</div></body></html>'
    return html

def landing():
    st.markdown("""
    <div style="text-align: center; padding: 4rem 1rem;">
        <div style="font-size: 5rem; margin-bottom: 1rem;">📊</div>
        <h1 style="color: #2c3e50; margin-bottom: 0.5rem;">Proxy Voting Dashboard</h1>
        <p style="color: #7f8c8d; font-size: 1.1rem; max-width: 600px; margin: 0 auto 2rem auto;">
            Select a fund and period from the sidebar, then click <strong>"Load Dashboard"</strong> to view the proxy voting data.
        </p>
    </div>
    """, unsafe_allow_html=True)

def main():
    inject_css()

    with st.sidebar:
        st.markdown('<p class="sidebar-header"><span class="material-icons" style="font-size:1.8rem;margin-right:8px;">how_to_vote</span>Proxy Voting</p>', unsafe_allow_html=True)
        st.markdown("---")

        data_dir = "./data"

        if not os.path.exists(data_dir):
            st.error(f"Data directory not found: {data_dir}")
            st.stop()

        with st.spinner("Scanning funds..."):
            funds = scan_funds(data_dir)

        if not funds:
            st.warning("No fund data found.")
            st.stop()

        codes = list(funds.keys())
        disp = {c: f"{get_name(c)} ({c})" for c in codes}

        st.markdown('<p style="font-size:0.9rem;margin-bottom:0.5rem;"><span class="material-icons" style="font-size:18px;color:#3498db;">account_balance</span> Select Fund</p>', unsafe_allow_html=True)
        sel_fund = st.selectbox("Fund", codes, format_func=lambda x: disp[x], label_visibility="collapsed")

        qtrs = get_qtrs(sel_fund, funds[sel_fund])
        avail_q = list(qtrs.keys())
        last_6 = gen_quarters()
        select_q = [q for q in last_6 if q in avail_q]

        st.markdown('<p style="font-size:0.9rem;margin-bottom:0.5rem;margin-top:1rem;"><span class="material-icons" style="font-size:18px;color:#3498db;">date_range</span> Select Period</p>', unsafe_allow_html=True)

        sel_qtr = None
        data_file = None

        if select_q:
            sel_qtr = st.selectbox("Quarter", select_q, label_visibility="collapsed")
            data_file = qtrs.get(sel_qtr)
        elif avail_q:
            st.warning("No data for recent quarters")
            sel_qtr = st.selectbox("Quarter (Historical)", avail_q, label_visibility="collapsed")
            data_file = qtrs.get(sel_qtr)
        else:
            st.error("No quarter data available")

        st.markdown("---")

        load_btn = st.button("📂 Load Dashboard", use_container_width=True, type="primary")

        if load_btn and sel_fund and sel_qtr and data_file:
            st.session_state.data_loaded = True
            st.session_state.sel_fund = sel_fund
            st.session_state.sel_qtr = sel_qtr
            st.session_state.data_file = data_file
            st.rerun()

        if st.session_state.data_loaded:
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.data_loaded = False
                st.session_state.sel_fund = None
                st.session_state.sel_qtr = None
                st.session_state.data_file = None
                st.rerun()

        st.markdown("---")
        st.markdown('<p style="font-size:0.85rem;"><span class="material-icons" style="font-size:16px;color:#2ecc71;">info</span> Data Summary</p>', unsafe_allow_html=True)
        st.caption(f"Available Funds: {len(codes)}")

    if not st.session_state.data_loaded:
        landing()
        st.stop()

    sel_fund = st.session_state.sel_fund
    sel_qtr = st.session_state.sel_qtr
    data_file = st.session_state.data_file
    full_name = get_name(sel_fund)

    st.markdown(f'<h1 class="main-header"><span class="material-icons" style="color:#3498db;font-size:2rem;">assessment</span>Proxy Voting Report</h1>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        st.markdown(f'<div class="info-box"><span class="material-icons" style="color:#3498db;font-size:18px;">business</span> <strong>Fund Name:</strong> {full_name}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="info-box"><span class="material-icons" style="color:#3498db;font-size:18px;">event</span> <strong>Reporting Period:</strong> {sel_qtr if sel_qtr else "N/A"}</div>', unsafe_allow_html=True)

    if data_file is None:
        no_mtgs()
        st.stop()

    prog = st.progress(0)
    stat = st.empty()

    stat.text("Loading data...")
    prog.progress(30)
    time.sleep(0.2)

    df = load_data(data_file)
    prog.progress(60)

    if df.empty:
        prog.progress(100)
        stat.empty()
        prog.empty()
        no_mtgs()
        st.stop()

    stat.text("Processing...")
    prog.progress(80)
    time.sleep(0.15)

    stats = calc_stats(df)
    m = calc_mtg(df)
    b = calc_ballot(df)
    p = calc_props(df)

    prog.progress(100)
    time.sleep(0.1)
    stat.empty()
    prog.empty()

    # Two-column layout
    left, right = st.columns([1, 1])

    with left:
        # Meeting Overview
        st.markdown('<h2 style="color: #3498db; font-size: 1.3rem; margin-top: 1rem;">Meeting Overview</h2>', unsafe_allow_html=True)
        m_data = {
            'Category': [
                'Number of votable meetings',
                'Number of meetings voted',
                'Number of meetings with at least 1 vote Against, Withhold or Abstain'
            ],
            'Number': [m.get('votable', 0), m.get('voted', 0), m.get('dissent', 0)],
            'Percentage': ['', '100.00%', f"{m.get('dissent_pct', 0):.2f}%"]
        }
        st.dataframe(pd.DataFrame(m_data), hide_index=True, use_container_width=True)

        # Ballot Overview
        st.markdown('<h2 style="color: #3498db; font-size: 1.3rem; margin-top: 2rem;">Ballot Overview</h2>', unsafe_allow_html=True)
        b_data = {
            'Category': ['Number of votable ballots', 'Number of ballots voted'],
            'Number': [b.get('votable', 0), b.get('voted', 0)],
            'Percentage': ['', '100.00%']
        }
        st.dataframe(pd.DataFrame(b_data), hide_index=True, use_container_width=True)

        # Proposal Overview
        st.markdown('<h2 style="color: #3498db; font-size: 1.3rem; margin-top: 2rem;">Proposal Overview</h2>', unsafe_allow_html=True)
        p_data = {
            'Category': [
                'Number of votable items', 'Number of items voted',
                'Number of votes FOR', 'Number of votes AGAINST',
                'Number of votes ABSTAIN', 'Number of votes WITHHOLD',
                'Number of votes on MSOP Frequency 1 Year',
                'Number of votes on MSOP Frequency 2 Years',
                'Number of votes on MSOP Frequency 3 Years',
                'Number of votes With Policy', 'Number of votes Against Policy',
                'Number of votes With Mgmt', 'Number of votes Against Mgmt',
                'Number of votes on MSOP (exclude frequency)',
                'Number of votes on Shareholder Proposals'
            ],
            'Number': [
                p.get('votable', 0), p.get('voted', 0),
                p.get('for', 0), p.get('against', 0),
                p.get('abstain', 0), p.get('withhold', 0),
                p.get('msop_1', 0), p.get('msop_2', 0), p.get('msop_3', 0),
                p.get('with_pol', 0), p.get('vs_pol', 0),
                p.get('with_mgmt', 0), p.get('vs_mgmt', 0),
                p.get('msop_ex', 0), p.get('sh_props', 0)
            ],
            'Percentage': [
                '', '100.00%',
                f"{p.get('for_pct', 0):.2f}%", f"{p.get('against_pct', 0):.2f}%",
                f"{p.get('abstain_pct', 0):.2f}%", f"{p.get('withhold_pct', 0):.2f}%",
                '0.00%', '0.00%', '0.00%',
                f"{p.get('with_pol_pct', 0):.2f}%", f"{p.get('vs_pol_pct', 0):.2f}%",
                f"{p.get('with_mgmt_pct', 0):.2f}%", f"{p.get('vs_mgmt_pct', 0):.2f}%",
                '0.00%', f"{p.get('sh_props_pct', 0):.2f}%"
            ]
        }
        st.dataframe(pd.DataFrame(p_data), hide_index=True, use_container_width=True, height=600)

    with right:
        st.markdown('<h2 style="color: #3498db; font-size: 1.3rem; margin-top: 1rem;">Voting Statistics</h2>', unsafe_allow_html=True)
        chart = chart_vote_stats(m, b, p)
        if chart:
            st.plotly_chart(chart, use_container_width=True)

        st.markdown('<h2 style="color: #3498db; font-size: 1.3rem; margin-top: 2rem;">Vote Cast Statistics</h2>', unsafe_allow_html=True)
        donut = chart_donut(p)
        if donut:
            st.plotly_chart(donut, use_container_width=True)

    # Additional sections
    st.markdown("---")
    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">category</span>Proposal Categories & Geography</h2>', unsafe_allow_html=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**Top Proposal Categories**")
        cat = chart_cats(df)
        if cat:
            st.plotly_chart(cat, use_container_width=True)
    with c4:
        st.markdown("**Meetings by Country**")
        cntry = chart_country(df)
        if cntry:
            st.plotly_chart(cntry, use_container_width=True)

    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">event</span>Meeting Details</h2>', unsafe_allow_html=True)

    mtg_df = mtg_table(df)
    if mtg_df is not None and not mtg_df.empty:
        render_grid(mtg_df, height=350)

    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">ballot</span>Proposal Details</h2>', unsafe_allow_html=True)

    prop_df = prop_table(df)
    if prop_df is not None and not prop_df.empty:
        with st.expander("Filter Options", expanded=False):
            f1, f2, f3 = st.columns(3)
            with f1:
                prps = ['All'] + list(prop_df['Proponent'].dropna().unique()) if 'Proponent' in prop_df.columns else ['All']
                sel_prp = st.selectbox("Proponent", prps)
            with f2:
                mgmt_f = st.selectbox("Management Alignment", ['All', 'With Management', 'Against Management'])
            with f3:
                comps = ['All'] + sorted(prop_df['Company Name'].dropna().unique().tolist()) if 'Company Name' in prop_df.columns else ['All']
                sel_comp = st.selectbox("Company", comps)

        filt = prop_df.copy()
        if sel_prp != 'All' and 'Proponent' in filt.columns:
            filt = filt[filt['Proponent'] == sel_prp]
        if mgmt_f != 'All' and 'Vote Against Management' in filt.columns:
            val = 'No' if mgmt_f == 'With Management' else 'Yes'
            filt = filt[filt['Vote Against Management'] == val]
        if sel_comp != 'All' and 'Company Name' in filt.columns:
            filt = filt[filt['Company Name'] == sel_comp]

        render_grid(filt, height=500)

    st.markdown("---")
    st.markdown('<h2 class="section-header"><span class="material-icons" style="color:#3498db;">download</span>Export Report</h2>', unsafe_allow_html=True)

    d1, d2 = st.columns(2)
    with d1:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Full Data (CSV)",
            data=csv,
            file_name=f"{sel_fund}_{sel_qtr.replace(' ', '_')}_voting_data.csv",
            mime="text/csv",
            use_container_width=True
        )
    with d2:
        html = gen_pdf(df, sel_fund, sel_qtr)
        st.download_button(
            label="Download Report (HTML/PDF)",
            data=html.encode('utf-8'),
            file_name=f"{sel_fund}_{sel_qtr.replace(' ', '_')}_report.html",
            mime="text/html",
            use_container_width=True,
            help="Open in browser and use Print > Save as PDF"
        )

if __name__ == "__main__":
    main()
