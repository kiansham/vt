import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from datetime import datetime
import os
import glob

st.set_page_config(page_title="Proxy Voting Dashboard", page_icon="📊", layout="wide")

FUND_MAP = {
    "DEFGLITS": "AQR Delphi Global Equity Fund",
    "AQRGLOB": "AQR Global Core Fund",
    "AQREMERGE": "AQR Emerging Markets Fund",
}


def get_name(code):
    return FUND_MAP.get(code, code)


def get_qtr(date_series):
    valid = pd.to_datetime(date_series, errors='coerce').dropna()
    if valid.empty:
        return None
    latest = valid.max()
    return f"Q{(latest.month - 1) // 3 + 1} {latest.year}"


def gen_quarters():
    now = datetime.now()
    q, y = (now.month - 1) // 3 + 1, now.year
    qtrs = []
    for _ in range(6):
        qtrs.append(f"Q{q} {y}")
        q -= 1
        if q == 0:
            q, y = 4, y - 1
    return qtrs


@st.cache_data(ttl=3600)
def scan_funds(data_dir):
    files = glob.glob(os.path.join(data_dir, "*.csv")) + glob.glob(os.path.join(data_dir, "*.CSV"))
    funds = {}
    for f in files:
        base = os.path.basename(f)
        code = base.split('_')[0] if '_' in base else base.split('.')[0]
        funds.setdefault(code, []).append(f)
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
        for col in ['Meeting Date', 'Record Date']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce', format='mixed')
        return df
    except:
        return pd.DataFrame()


def calc_stats(df):
    if df.empty:
        return {
            'meetings': 0, 'ballots': 0, 'proposals': 0, 'dissent': 0, 'dissent_pct': 0,
            'for': 0, 'against': 0, 'abstain': 0, 'withhold': 0,
            'with_mgmt': 0, 'vs_mgmt': 0, 'with_pol': 0, 'vs_pol': 0, 'sh_props': 0
        }
    
    total = len(df)
    meetings = df['Company Name'].nunique() if 'Company Name' in df.columns else 0
    
    stats = {
        'meetings': meetings, 'ballots': meetings, 'proposals': total,
        'for': 0, 'against': 0, 'abstain': 0, 'withhold': 0,
        'with_mgmt': 0, 'vs_mgmt': 0, 'with_pol': 0, 'vs_pol': 0, 'sh_props': 0
    }
    
    if 'Vote Instruction' in df.columns:
        vc = df['Vote Instruction'].value_counts()
        stats['for'] = int(vc.get('For', 0))
        stats['against'] = int(vc.get('Against', 0))
        stats['abstain'] = int(vc.get('Abstain', 0))
        stats['withhold'] = int(vc.get('Withhold', 0))
        
        dissent_votes = df[df['Vote Instruction'].isin(['Against', 'Withhold', 'Abstain'])]
        stats['dissent'] = dissent_votes['Company Name'].nunique() if 'Company Name' in df.columns else 0
    else:
        stats['dissent'] = 0
    
    stats['dissent_pct'] = round(100 * stats['dissent'] / max(meetings, 1), 2)
    
    if 'Vote Against Management' in df.columns:
        stats['with_mgmt'] = int((df['Vote Against Management'] == 'No').sum())
        stats['vs_mgmt'] = int((df['Vote Against Management'] == 'Yes').sum())
    
    if 'Vote Against ISS' in df.columns:
        stats['with_pol'] = int((df['Vote Against ISS'] == 'No').sum())
        stats['vs_pol'] = int((df['Vote Against ISS'] == 'Yes').sum())
    
    if 'Proponent' in df.columns:
        stats['sh_props'] = int((df['Proponent'] == 'Shareholder').sum())
    
    # Calculate percentages
    for k in ['for', 'against', 'abstain', 'withhold', 'with_mgmt', 'vs_mgmt', 'with_pol', 'vs_pol', 'sh_props']:
        stats[f'{k}_pct'] = round(100 * stats[k] / max(total, 1), 2)
    
    return stats


def chart_vote_stats(s):
    cats = ['Meetings', 'Ballots', 'Proposals']
    vals = [s['meetings'], s['ballots'], s['proposals']]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='Votable', y=cats, x=vals, orientation='h',
        marker_color='#34495e', text=vals, textposition='inside'
    ))
    fig.add_trace(go.Bar(
        name='Voted', y=cats, x=vals, orientation='h',
        marker_color='#e74c3c', text=vals, textposition='inside'
    ))
    fig.update_layout(
        barmode='overlay', height=280, margin=dict(t=20, b=20, l=80, r=20),
        legend=dict(orientation="h", y=1.1), xaxis=dict(type='log')
    )
    return fig


def chart_donut(s):
    data = [
        ('For', s['for'], '#34495e'),
        ('Abstain', s['abstain'], '#9b59b6'),
        ('Withhold', s['withhold'], '#a29bfe'),
        ('Against', s['against'], '#dfe6e9')
    ]
    labels, values, colors = zip(*[(l, v, c) for l, v, c in data if v > 0]) if any(d[1] > 0 for d in data) else ([], [], [])
    
    if not values:
        return None
    
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.5, marker_colors=colors,
        textposition='outside', textinfo='label+percent'
    ))
    fig.update_layout(
        height=350, margin=dict(t=20, b=20, l=20, r=100),
        legend=dict(orientation="v", y=0.5, x=1.05)
    )
    return fig


def chart_cats(df):
    if df.empty or 'Proposal Code Category' not in df.columns:
        return None
    cats = df['Proposal Code Category'].value_counts().head(10).reset_index()
    cats.columns = ['Category', 'Count']
    fig = px.bar(cats, x='Count', y='Category', orientation='h', color='Count', color_continuous_scale='teal')
    fig.update_layout(
        margin=dict(t=20, b=20, l=20, r=20), height=320,
        yaxis={'categoryorder': 'total ascending'}, coloraxis_showscale=False
    )
    return fig


def chart_country(df):
    if df.empty or 'Country' not in df.columns:
        return None
    cc = df.groupby('Country')['Company Name'].nunique().reset_index(name='Meetings')
    cc = cc.sort_values('Meetings', ascending=False).head(10)
    fig = px.bar(cc, x='Country', y='Meetings', color='Meetings', color_continuous_scale='teal')
    fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=320, coloraxis_showscale=False)
    return fig


def get_table(df, cols):
    avail = [c for c in cols if c in df.columns]
    tbl = df[avail].drop_duplicates().copy()
    if 'Meeting Date' in tbl.columns:
        tbl['Meeting Date'] = tbl['Meeting Date'].dt.strftime('%d-%b-%Y')
    return tbl


def render_grid(df, height=400):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, filterable=True, sortable=True, wrapText=True, autoHeight=True)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=15)
    return AgGrid(
        df, gridOptions=gb.build(), height=height, theme='streamlit',
        update_mode=GridUpdateMode.NO_UPDATE
    )


def gen_report(df, code, qtr):
    stats = calc_stats(df)
    pct = round(100 * stats['with_mgmt'] / max(stats['proposals'], 1), 1)
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Proxy Voting Report - {code}</title>
    <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    h1 {{ font-size: 24px; }}
    h2 {{ font-size: 18px; margin-top: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th {{ background: #333; color: white; padding: 8px; text-align: left; }}
    td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
    </style>
</head>
<body>
    <h1>Proxy Voting Report</h1>
    <p><strong>Fund:</strong> {code} | <strong>Period:</strong> {qtr} | <strong>Generated:</strong> {datetime.now().strftime('%d %b %Y')}</p>
    <h2>Summary</h2>
    <p>Meetings: {stats['meetings']} | Proposals: {stats['proposals']} | With Management: {pct}%</p>"""
    
    mtg_cols = ['Company Name', 'Ticker', 'Country', 'Meeting Date', 'Meeting Type']
    mtg_df = get_table(df, mtg_cols)
    if not mtg_df.empty:
        html += '<h2>Meetings</h2>' + mtg_df.to_html(index=False, border=0)
    
    prop_cols = [
        'Company Name', 'Ticker', 'Meeting Date', 'Proposal Number', 'Proposal Text',
        'Proponent', 'Management Recommendation', 'Vote Instruction', 'Vote Against Management'
    ]
    prop_df = get_table(df, prop_cols)
    if not prop_df.empty:
        html += '<h2>Proposals</h2>' + prop_df.to_html(index=False, border=0)
    
    html += '</body></html>'
    return html


def main():
    # Sidebar
    with st.sidebar:
        st.header("🗳️ Proxy Voting")
        data_dir = "./data"
        
        if not os.path.exists(data_dir):
            st.error(f"Data directory not found: {data_dir}")
            st.stop()
        
        funds = scan_funds(data_dir)
        if not funds:
            st.warning("No fund data found.")
            st.stop()
        
        codes = list(funds.keys())
        sel_fund = st.selectbox("Fund", codes, format_func=lambda x: f"{get_name(x)} ({x})")
        
        qtrs = get_qtrs(sel_fund, funds[sel_fund])
        avail_q = list(qtrs.keys())
        select_q = [q for q in gen_quarters() if q in avail_q] or avail_q
        sel_qtr = st.selectbox("Period", select_q) if select_q else None
        data_file = qtrs.get(sel_qtr) if sel_qtr else None
        
        load_btn = st.button("Load Dashboard", use_container_width=True, type="primary")
        
        if load_btn and data_file:
            st.session_state.update({'loaded': True, 'fund': sel_fund, 'qtr': sel_qtr, 'file': data_file})
            st.rerun()
        
        if st.session_state.get('loaded') and st.button("Reset", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    # Main content
    if not st.session_state.get('loaded'):
        st.title("📊 Proxy Voting Dashboard")
        st.write("Select a fund and period from the sidebar, then click **Load Dashboard**.")
        st.stop()
    
    sel_fund, sel_qtr, data_file = st.session_state['fund'], st.session_state['qtr'], st.session_state['file']
    
    st.title("📊 Proxy Voting Report")
    c1, c2 = st.columns(2)
    c1.info(f"**Fund:** {get_name(sel_fund)}")
    c2.info(f"**Period:** {sel_qtr}")
    
    df = load_data(data_file)
    if df.empty:
        st.info("📅 No meetings during this period.")
        st.stop()
    
    stats = calc_stats(df)
    
    # Overview tables and charts
    left, right = st.columns(2)
    
    with left:
        st.subheader("Meeting Overview")
        st.dataframe(pd.DataFrame({
            'Category': ['Votable meetings', 'Meetings voted', 'Meetings with dissent'],
            'Number': [stats['meetings'], stats['meetings'], stats['dissent']],
            'Percentage': ['', '100.00%', f"{stats['dissent_pct']:.2f}%"]
        }), hide_index=True, use_container_width=True)
        
        st.subheader("Proposal Overview")
        st.dataframe(pd.DataFrame({
            'Category': [
                'Votable items', 'Items voted', 'Votes FOR', 'Votes AGAINST', 'Votes ABSTAIN',
                'Votes WITHHOLD', 'With Policy', 'Against Policy', 'With Mgmt', 'Against Mgmt',
                'Shareholder Proposals'
            ],
            'Number': [
                stats['proposals'], stats['proposals'], stats['for'], stats['against'],
                stats['abstain'], stats['withhold'], stats['with_pol'], stats['vs_pol'],
                stats['with_mgmt'], stats['vs_mgmt'], stats['sh_props']
            ],
            'Percentage': [
                '', '100.00%', f"{stats['for_pct']:.2f}%", f"{stats['against_pct']:.2f}%",
                f"{stats['abstain_pct']:.2f}%", f"{stats['withhold_pct']:.2f}%",
                f"{stats['with_pol_pct']:.2f}%", f"{stats['vs_pol_pct']:.2f}%",
                f"{stats['with_mgmt_pct']:.2f}%", f"{stats['vs_mgmt_pct']:.2f}%",
                f"{stats['sh_props_pct']:.2f}%"
            ]
        }), hide_index=True, use_container_width=True, height=450)
    
    with right:
        st.subheader("Voting Statistics")
        st.plotly_chart(chart_vote_stats(stats), use_container_width=True)
        
        st.subheader("Vote Distribution")
        donut = chart_donut(stats)
        if donut:
            st.plotly_chart(donut, use_container_width=True)
    
    # Categories and Geography
    st.subheader("Categories & Geography")
    c3, c4 = st.columns(2)
    with c3:
        cat_chart = chart_cats(df)
        if cat_chart:
            st.plotly_chart(cat_chart, use_container_width=True)
    with c4:
        country_chart = chart_country(df)
        if country_chart:
            st.plotly_chart(country_chart, use_container_width=True)
    
    # Meeting Details
    st.subheader("Meeting Details")
    mtg_df = get_table(df, ['Company Name', 'Ticker', 'Country', 'Meeting Date', 'Meeting Type'])
    if not mtg_df.empty:
        render_grid(mtg_df, height=300)
    
    # Proposal Details with filters
    st.subheader("Proposal Details")
    prop_cols = [
        'Company Name', 'Ticker', 'Meeting Date', 'Proposal Number', 'Proposal Text',
        'Proponent', 'Management Recommendation', 'ISS Recommendation', 'Vote Instruction',
        'Vote Against Management', 'Vote Against ISS'
    ]
    prop_df = get_table(df, prop_cols)
    
    if not prop_df.empty:
        with st.expander("Filters"):
            f1, f2, f3 = st.columns(3)
            prps = ['All'] + (list(prop_df['Proponent'].dropna().unique()) if 'Proponent' in prop_df.columns else [])
            sel_prp = f1.selectbox("Proponent", prps)
            mgmt_f = f2.selectbox("Management Alignment", ['All', 'With Management', 'Against Management'])
            comps = ['All'] + (sorted(prop_df['Company Name'].dropna().unique().tolist()) if 'Company Name' in prop_df.columns else [])
            sel_comp = f3.selectbox("Company", comps)
        
        filt = prop_df.copy()
        if sel_prp != 'All' and 'Proponent' in filt.columns:
            filt = filt[filt['Proponent'] == sel_prp]
        if mgmt_f != 'All' and 'Vote Against Management' in filt.columns:
            filt = filt[filt['Vote Against Management'] == ('No' if mgmt_f == 'With Management' else 'Yes')]
        if sel_comp != 'All' and 'Company Name' in filt.columns:
            filt = filt[filt['Company Name'] == sel_comp]
        
        render_grid(filt, height=450)
    
    # Export
    st.subheader("Export")
    d1, d2 = st.columns(2)
    d1.download_button(
        "Download CSV", df.to_csv(index=False).encode('utf-8'),
        f"{sel_fund}_{sel_qtr.replace(' ', '_')}.csv", "text/csv", use_container_width=True
    )
    d2.download_button(
        "Download Report (HTML)", gen_report(df, sel_fund, sel_qtr).encode('utf-8'),
        f"{sel_fund}_{sel_qtr.replace(' ', '_')}_report.html", "text/html", use_container_width=True
    )


if __name__ == "__main__":
    main()
