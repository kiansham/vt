import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os, glob
from datetime import datetime

st.set_page_config(
    page_title="Proxy Voting Dashboard",
    page_icon=":material/how_to_vote:",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.html("""
<style>
.section-header{
    font-size:1.1rem;
    font-weight:600;
    color:#1E3A5F;
    border-bottom:2px solid #1E3A5F;
    padding-bottom:0.5rem;
    margin:1.5rem 0 1rem 0
}
[data-testid="stMetric"] [data-testid="stMetricDelta"] svg,
div[data-testid="stDataFrame"] progress {
    color: #1E3A5F !important;
}
div[data-testid="stDataFrame"] progress::-webkit-progress-value {
    background-color: #1E3A5F !important;
}
div[data-testid="stDataFrame"] progress::-moz-progress-bar {
    background-color: #1E3A5F !important;
}
#MainMenu,footer{visibility:hidden}
</style>
""")

C = {"p": "#1E3A5F", "d": "#DC2626", "w": "#F59E0B", "t": "#1c1919"}

@st.cache_data(ttl=3600)
def load_funds():
    try:
        df = pd.read_csv("./data/funds.csv")
        return dict(zip(df['short_name'], df['long_name']))
    except FileNotFoundError:
        st.warning("funds.csv not found in ./data directory, using empty mapping")
        return {}

@st.cache_data(ttl=3600)
def scan_dir(d):
    funds = {}
    consolidated_dir = os.path.join(d, 'consolidated')
    if os.path.exists(consolidated_dir):
        for f in glob.glob(os.path.join(consolidated_dir, "*_consolidated.[cC][sS][vV]")):
            fund_id = os.path.basename(f).split('_consolidated')[0]
            funds[fund_id] = f
    if not funds:
        for fund_dir in glob.glob(os.path.join(d, "*/")):
            fund_id = os.path.basename(fund_dir.rstrip('/'))
            if fund_id in ['consolidated', 'archive', '.git']:
                continue
            csv_files = glob.glob(os.path.join(fund_dir, "*.[cC][sS][vV]"))
            if csv_files:
                funds[fund_id] = csv_files
    return funds

@st.cache_data(ttl=600)
def load(fp):
    try:
        return pd.read_csv(fp, parse_dates=['Meeting Date', 'Record Date'], dayfirst=True)
    except ValueError:
        return pd.read_csv(fp)

def calc_stats(df):
    dv = df[df['Votable Proposal']=='Yes'].copy() if 'Votable Proposal' in df.columns else df.copy()
    total = len(dv)
    voted = len(dv[dv['Voted (Yes, No, Partial)'].isin(['Yes','Partial'])]) if 'Voted (Yes, No, Partial)' in dv.columns else total
    mtgs = dv['Meeting ID'].nunique() if 'Meeting ID' in dv.columns else 0
    voted_mtgs = dv[dv['Voted (Yes, No, Partial)'].isin(['Yes','Partial'])]['Meeting ID'].nunique() if 'Voted (Yes, No, Partial)' in dv.columns and 'Meeting ID' in dv.columns else mtgs

    s = {
        'votable_mtgs': mtgs, 'voted_mtgs': voted_mtgs, 'mtg_rate': round(100*voted_mtgs/mtgs,2) if mtgs else 0,
        'votable_props': total, 'voted_props': voted, 'prop_rate': round(100*voted/total,2) if total else 0,
        'for': 0, 'against': 0, 'abstain': 0, 'withhold': 0, 'with_mgmt': 0, 'vs_mgmt': 0,
        'with_pol': 0, 'vs_pol': 0, 'sh_props': 0, 'msop1': 0, 'msop2': 0, 'msop3': 0, 'dissent_mtgs': 0
    }

    if 'Vote Instruction' in dv.columns:
        vc = dv['Vote Instruction'].value_counts()
        s.update({
            'for': int(vc.get('For',0))+int(vc.get('One Year',0)),
            'against': int(vc.get('Against',0)),
            'abstain': int(vc.get('Abstain',0)),
            'withhold': int(vc.get('Withhold',0)),
            'msop1': int(vc.get('One Year',0)),
            'msop2': int(vc.get('Two Years',0)),
            'msop3': int(vc.get('Three Years',0))
        })
    if 'Vote Against Management' in dv.columns:
        s['with_mgmt'] = int((dv['Vote Against Management']=='No').sum())
        s['vs_mgmt'] = int((dv['Vote Against Management']=='Yes').sum())
        if 'Meeting ID' in dv.columns:
            s['dissent_mtgs'] = dv[dv['Vote Against Management']=='Yes']['Meeting ID'].nunique()
    if 'Vote Against Policy' in dv.columns:
        s['with_pol'] = int((dv['Vote Against Policy']=='No').sum())
        s['vs_pol'] = int((dv['Vote Against Policy']=='Yes').sum())
    if 'Proponent' in dv.columns:
        s['sh_props'] = int((dv['Proponent']=='Shareholder').sum())

    for k in ['for','against','abstain','withhold','with_mgmt','vs_mgmt','with_pol','vs_pol']:
        s[k+'_pct'] = round(100*s[k]/total,2) if total else 0
    s['dissent_pct'] = round(100*s['dissent_mtgs']/mtgs,2) if mtgs else 0
    return s, dv

def donut(w, a, t):
    fig = go.Figure(go.Pie(labels=['Aligned','Divergent'], values=[w,a], hole=0.65, marker_colors=[C['p'],C['d']], textinfo='percent', textposition='outside', showlegend=False))
    fig.add_annotation(text=f"<b>{w:.1f}%</b>", x=0.5, y=0.5, font=dict(size=18, color=C['p']), showarrow=False)
    fig.update_layout(title=dict(text=t, x=0, xanchor='left'), height=220, margin=dict(l=20,r=20,t=45,b=20), paper_bgcolor='rgba(0,0,0,0)')
    return fig

def vote_pie(s):
    data = [(l,s[k],c) for l,k,c in [('For','for',C['p']),('Against','against',C['d']),('Abstain','abstain',C['w']),('Withhold','withhold',C['d'])] if s[k]>0]
    if not data: return None
    lbls, vals, cols = zip(*data)
    fig = go.Figure(go.Pie(labels=lbls, values=vals, hole=0.6, marker_colors=cols, textposition='outside', textinfo='label+percent'))
    fig.add_annotation(text=f"<b>{sum(vals)}</b><br>Votes", x=0.5, y=0.5, font=dict(size=14, color=C['t']), showarrow=False)
    fig.update_layout(height=280, margin=dict(l=20,r=20,t=20,b=20), showlegend=False, paper_bgcolor='rgba(0,0,0,0)')
    return fig

def bar(df, grp, cnt, title, ylab, n=10, use_cnt=False, vertical=False):
    if grp not in df.columns: return None
    data = df[grp].value_counts().head(n).sort_values(ascending=not vertical) if use_cnt else df.groupby(grp)[cnt].nunique().nlargest(n).sort_values(ascending=not vertical)
    if vertical:
        fig = go.Figure(go.Bar(x=data.index, y=data.values, marker_color=C['p'], text=data.values, textposition='outside'))
        fig.update_layout(title=dict(text=title), height=350, margin=dict(l=20,r=20,t=45,b=120),
                          yaxis=dict(title=ylab, showgrid=True, gridcolor='#E2E8F0'), xaxis=dict(tickangle=-45), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    else:
        fig = go.Figure(go.Bar(y=data.index, x=data.values, orientation='h', marker_color=C['p'], text=data.values, textposition='outside'))
        fig.update_layout(title=dict(text=title), height=max(250,len(data)*32), margin=dict(l=20,r=60,t=45,b=30),
                          xaxis=dict(title=ylab, showgrid=True, gridcolor='#E2E8F0'), yaxis_title="", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    return fig

def yes_count(df, col):
    return (df[col]=='Yes').sum() if col in df.columns else 0

def breakdown(df):
    if 'Country' not in df.columns or 'Meeting ID' not in df.columns:
        return pd.DataFrame()
    def calc(g):
        no = g[g['Voted (Yes, No, Partial)']=='No'] if 'Voted (Yes, No, Partial)' in g.columns else pd.DataFrame()
        unvoted = len({m for m in no['Meeting ID'].unique() if not g[g['Meeting ID']==m]['Voted (Yes, No, Partial)'].isin(['Yes','Partial']).any()}) if len(no) else 0
        voted = len(g[g['Voted (Yes, No, Partial)'].isin(['Yes','Partial'])]) if 'Voted (Yes, No, Partial)' in g.columns else len(g)
        return pd.Series({
            'Mtgs Votable': g['Meeting ID'].nunique(),
            'Mtgs Voted': g['Meeting ID'].nunique()-unvoted,
            'Mtgs Dissent': g[g['Vote Against Management']=='Yes']['Meeting ID'].nunique() if 'Vote Against Management' in g.columns else 0,
            'Props Voted': voted,
            'Vs Mgmt': yes_count(g,'Vote Against Management'),
            'Vs Policy': yes_count(g,'Vote Against Policy')
        })
    return df.groupby('Country').apply(calc, include_groups=False).reset_index().sort_values('Mtgs Votable', ascending=False)

def ensure_datetime(df):
    if df.empty or 'Meeting Date' not in df.columns:
        return df
    if not pd.api.types.is_datetime64_any_dtype(df['Meeting Date']):
        df['Meeting Date'] = pd.to_datetime(df['Meeting Date'], errors='coerce', dayfirst=True)
    return df

def date_bounds(df):
    df = ensure_datetime(df)
    today = datetime.now().date()
    if df.empty or 'Meeting Date' not in df.columns:
        return today - pd.Timedelta(days=365), today
    dates = df['Meeting Date'].dropna()
    if dates.empty:
        return today - pd.Timedelta(days=365), today
    min_date = dates.min().date()
    max_raw = dates.max()
    max_date = datetime(max_raw.year, 12, 31).date() if max_raw.month == 12 else (datetime(max_raw.year, max_raw.month + 1, 1) - pd.Timedelta(days=1)).date()
    return min_date, max_date

def filter_dates(df, start, end):
    df = ensure_datetime(df)
    if df.empty or 'Meeting Date' not in df.columns:
        return df
    mask = (df['Meeting Date'] >= pd.to_datetime(start)) & (df['Meeting Date'] <= pd.to_datetime(end))
    return df[mask].copy()

def main():
    funds_map = load_funds()

    with st.sidebar:
        st.title(":material/settings: Control Panel")
        if not os.path.exists("./data"): st.error("Data directory not found"); st.stop()
        funds = scan_dir("./data")
        if not funds: st.warning("No fund data found."); st.stop()

        fund_list = list(funds.keys())
        default_idx = fund_list.index("Firm") if "Firm" in fund_list else 0
        fund = st.selectbox("Select Fund", fund_list, index=default_idx, format_func=lambda x: funds_map.get(x,x))

    fund_data = funds[fund]
    df_full = load(fund_data) if isinstance(fund_data, str) else load(fund_data[0]) if fund_data else pd.DataFrame()
    min_date, max_date = date_bounds(df_full)

    with st.sidebar:
        st.divider()
        st.markdown("**:material/calendar_month: Select Period**")
        default_start = max(min_date, max_date - pd.Timedelta(days=365))
        date_range = st.date_input("Date Range", value=(default_start, max_date), min_value=min_date, max_value=max_date, format="MM/DD/YYYY")

        start, end = date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (date_range[0] if isinstance(date_range, tuple) else date_range, date_range[0] if isinstance(date_range, tuple) else date_range)

        st.divider()
        st.markdown("**:material/download: Export**")

    df = filter_dates(df_full, start, end)

    with st.sidebar:
        if not df.empty:
            date_str = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
            st.download_button(":material/download: Download CSV", df.to_csv(index=False).encode('utf-8'), f"{fund}_{date_str}.csv", "text/csv", use_container_width=True)
        st.divider()
        st.caption(f"Generated: {datetime.now().strftime('%d %b %Y')}")

    if df.empty:
        st.subheader("Proxy Voting Dashboard")
        st.write("No data for selected date range.")
        st.stop()

    st.subheader(":material/how_to_vote: Proxy Voting Dashboard")
    period_str = f"{start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')}"
    c1, c2 = st.columns([1,1.5])
    c1.write(f"**Account:** {funds_map.get(fund,fund)}")
    c2.write(f"**Period:** {period_str}")
    s, dv = calc_stats(df)

    st.markdown('<p class="section-header">Voting Overview</p>', unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("##### :material/groups: Voting Data")
        st.dataframe(
            pd.DataFrame({
                'Meeting Overview':['Votable Meetings','Meetings Voted','Meetings with Dissent'],
                'Number':[s['votable_mtgs'],s['voted_mtgs'],s['dissent_mtgs']],
                'Percentage':[None, s['mtg_rate'], s['dissent_pct']]
            }),
            hide_index=True,
            column_config={"Percentage": st.column_config.ProgressColumn("Percentage", format="%.2f%%", min_value=0, max_value=100)}
        )
        st.dataframe(
            pd.DataFrame({
                'Proposal Overview':['Votable Proposals','Proposals Voted','Votes FOR','Votes AGAINST','Votes ABSTAIN','Votes WITHHOLD','With Management','Against Management','With Policy','Against Policy','Shareholder Proposals','MSOP 1 Year','MSOP 2 Years','MSOP 3 Years'],
                'Number':[s['votable_props'],s['voted_props'],s['for'],s['against'],s['abstain'],s['withhold'],s['with_mgmt'],s['vs_mgmt'],s['with_pol'],s['vs_pol'],s['sh_props'],s['msop1'],s['msop2'],s['msop3']],
                'Percentage':[None, s['prop_rate'],s['for_pct'],s['against_pct'],s['abstain_pct'],s['withhold_pct'],s['with_mgmt_pct'],s['vs_mgmt_pct'],s['with_pol_pct'],s['vs_pol_pct'],
                             round(100*s['sh_props']/s['votable_props'],2) if s['votable_props'] else 0,
                             round(100*s['msop1']/s['votable_props'],2) if s['votable_props'] else 0,
                             round(100*s['msop2']/s['votable_props'],2) if s['votable_props'] else 0,
                             round(100*s['msop3']/s['votable_props'],2) if s['votable_props'] else 0]
            }),
            hide_index=True,
            height=560,
            column_config={
                "Number": st.column_config.NumberColumn("Number", format="%d"),
                "Percentage": st.column_config.ProgressColumn("Percentage", format="%.2f%%", min_value=0, max_value=100)
            }
        )
    with c4:
        st.markdown("##### :material/bar_chart: Vote Distribution")
        if fig := vote_pie(s): st.plotly_chart(fig, use_container_width=True)
        st.markdown("##### :material/done_all: Alignment Analysis")
        ac1, ac2 = st.columns(2)
        ac1.plotly_chart(donut(s['with_mgmt_pct'],s['vs_mgmt_pct'],"Management"), use_container_width=True)
        ac2.plotly_chart(donut(s['with_pol_pct'],s['vs_pol_pct'],"Policy"), use_container_width=True)

    st.divider()
    st.markdown('<p class="section-header">Market Breakdown</p>', unsafe_allow_html=True)
    if not (mkt := breakdown(dv)).empty:
        st.dataframe(
            mkt, use_container_width=True, hide_index=True,
            column_config={
                "Mtgs Votable": st.column_config.NumberColumn("Mtgs Votable", format="%d"),
                "Mtgs Voted": st.column_config.NumberColumn("Mtgs Voted", format="%d"),
                "Mtgs Dissent": st.column_config.NumberColumn("Mtgs Dissent", format="%d"),
                "Props Voted": st.column_config.NumberColumn("Props Voted", format="%d"),
                "Vs Mgmt": st.column_config.NumberColumn("Vs Mgmt", format="%d"),
                "Vs Policy": st.column_config.NumberColumn("Vs Policy", format="%d"),
            }
        )
    if fig := bar(dv, 'Country', 'Meeting ID', "Meeting Activity by Market", "Meetings", vertical=True):
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown('<p class="section-header">Proposal Categories</p>', unsafe_allow_html=True)
    if 'Proposal Code Category' in dv.columns:
        def calc_cat(g):
            voted = len(g[g['Voted (Yes, No, Partial)'].isin(['Yes','Partial'])]) if 'Voted (Yes, No, Partial)' in g.columns else len(g)
            return pd.Series({
                'Props Votable': len(g),
                'Props Voted': voted,
                'Vs Mgmt': yes_count(g,'Vote Against Management'),
                'Vs Policy': yes_count(g,'Vote Against Policy'),
                'SH Props': (g['Proponent']=='Shareholder').sum() if 'Proponent' in g.columns else 0
            })
        cat = dv.groupby('Proposal Code Category').apply(calc_cat, include_groups=False).reset_index().rename(columns={'Proposal Code Category':'Category'})
        st.dataframe(
            cat.sort_values('Props Votable', ascending=False).head(10),
            use_container_width=True, hide_index=True,
            column_config={
                "Props Votable": st.column_config.NumberColumn("Props Votable", format="%d"),
                "Props Voted": st.column_config.NumberColumn("Props Voted", format="%d"),
                "Vs Mgmt": st.column_config.NumberColumn("Vs Mgmt", format="%d"),
                "Vs Policy": st.column_config.NumberColumn("Vs Policy", format="%d"),
                "SH Props": st.column_config.NumberColumn("SH Props", format="%d"),
            }
        )
    if fig := bar(dv, 'Proposal Code Category', 'Proposal Text', "Proposal Activity by Category", "Proposals", use_cnt=True, vertical=True):
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown('<p class="section-header">Detailed Vote Analysis</p>', unsafe_allow_html=True)
    t1, t2 = st.tabs([":material/business: Meetings List", ":material/ballot: All Proposals"])

    with t1:
        mc = [c for c in ['Meeting ID','Company Name','Ticker','Industry Sector','Country','Market Cap (USD)','Meeting Date','Meeting Type','Percentage Votable Shares'] if c in dv.columns]
        mdf = dv.groupby('Meeting ID' if 'Meeting ID' in dv.columns else 'Company Name').agg({
            **{c: 'first' for c in mc if c in dv.columns and c != 'Meeting ID'},
            'Proposal Text': 'size'
        }).reset_index().rename(columns={'Proposal Text': 'Proposals'}) if 'Meeting ID' in dv.columns else dv[mc].drop_duplicates()

        if 'Voted (Yes, No, Partial)' in dv.columns and 'Meeting ID' in dv.columns:
            mdf['Voted'] = mdf['Meeting ID'].map(lambda m: 'Yes' if dv[dv['Meeting ID']==m]['Voted (Yes, No, Partial)'].isin(['Yes','Partial']).any() else 'No')
        if 'Vote Against Management' in dv.columns and 'Meeting ID' in dv.columns:
            mdf['Dissent'] = mdf['Meeting ID'].map(lambda m: 'Yes' if (dv[dv['Meeting ID']==m]['Vote Against Management']=='Yes').any() else 'No')

        display_cols = [c for c in ['Company Name','Ticker','Industry Sector','Country','Market Cap (USD)','Meeting Date','Meeting Type','Percentage Votable Shares','Proposals','Voted','Dissent'] if c in mdf.columns]
        st.dataframe(mdf[display_cols], use_container_width=True, hide_index=True)
        st.caption(f"Total: {len(mdf):,} meetings")

    with t2:
        pc = [c for c in ['Company Name','Ticker','Industry Sector','Meeting Date','Proposal Number','Proposal Text','Proponent','Votable Proposal','Voted (Yes, No, Partial)','Management Recommendation','ISS Recommendation','Vote Instruction','Vote Against Management','Vote Against Policy'] if c in dv.columns]
        pdf = dv[pc].drop_duplicates()
        if not pdf.empty:
            with st.expander(":material/filter_alt: Filters"):
                f1,f2,f3 = st.columns(3)
                cos = ['All']+sorted(pdf['Company Name'].dropna().unique().tolist()) if 'Company Name' in pdf.columns else ['All']
                pros = ['All']+list(pdf['Proponent'].dropna().unique()) if 'Proponent' in pdf.columns else ['All']
                sc, sp, sm = f1.selectbox("Company",cos), f2.selectbox("Proponent",pros), f3.selectbox("Management Alignment",['All','With Management','Against Management'])
            flt = pdf.copy()
            if sc!='All' and 'Company Name' in flt.columns: flt = flt[flt['Company Name']==sc]
            if sp!='All' and 'Proponent' in flt.columns: flt = flt[flt['Proponent']==sp]
            if sm!='All' and 'Vote Against Management' in flt.columns:
                flt = flt[flt['Vote Against Management']==('No' if sm=='With Management' else 'Yes')]
            st.dataframe(flt, use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(flt):,} of {len(pdf):,} proposals")

if __name__ == "__main__":
    main()
