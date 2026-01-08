import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os, glob
from datetime import datetime

st.set_page_config(page_title="Proxy Voting Dashboard", page_icon=":material/how_to_vote:", layout="wide", initial_sidebar_state="expanded")

C = {"p": "#1E3A5F", "d": "#DC2626", "w": "#F59E0B", "t": "#1c1919"}
FUNDS = {"DEFGLITS": "AQR Delphi Global Equity Fund", "AQRGLOB": "AQR Global Core Fund", "AQREMERGE": "AQR Emerging Markets Fund"}

st.markdown("""<style>
.prog-wrap{margin:1rem 0}.prog-lbl{font-size:0.9rem;font-weight:500;color:#1E3A5F;margin-bottom:0.5rem}
.prog-cont{width:100%;height:24px;background:#e2e8f0;border-radius:6px;overflow:visible;position:relative;margin-bottom:2rem}
.prog-fill{height:100%;border-radius:6px;display:flex;align-items:center;justify-content:flex-end;padding-right:8px;color:white;font-weight:600;font-size:0.85rem}
.prog-ticks{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none}
.prog-tick{position:absolute;height:100%;width:2px;background:rgba(0,0,0,0.15)}
.prog-tick-lbl{position:absolute;top:100%;margin-top:4px;font-size:0.7rem;color:#64748b;transform:translateX(-50%)}
.section-header{font-size:1.1rem;font-weight:600;color:#1E3A5F;border-bottom:2px solid #1E3A5F;padding-bottom:0.5rem;margin:1.5rem 0 1rem 0}
#MainMenu,footer{visibility:hidden}
</style>""", unsafe_allow_html=True)

def pct(v): return f"{int(v)}%" if v == 100.0 else f"{v:.2f}%"

def get_qtr(dates):
    v = pd.to_datetime(dates, errors='coerce', dayfirst=True).dropna()
    return f"Q{(v.max().month-1)//3+1} {v.max().year}" if not v.empty else None

def gen_qtrs(n=6):
    q, y = (datetime.now().month-1)//3+1, datetime.now().year
    out = []
    for _ in range(n):
        out.append(f"Q{q} {y}")
        q -= 1
        if q == 0: q, y = 4, y-1
    return out

@st.cache_data(ttl=3600)
def scan_dir(d):
    funds = {}
    for f in glob.glob(os.path.join(d, "*.[cC][sS][vV]")):
        funds.setdefault(os.path.basename(f).split('_')[0].split('.')[0], []).append(f)
    return funds

@st.cache_data(ttl=3600)
def get_fund_qtrs(files):
    qtrs = {}
    for f in files:
        try:
            # OPTIMIZATION 1: Read only needed column and fewer rows
            df = pd.read_csv(f, nrows=5, usecols=['Meeting Date'])
            if (q := get_qtr(df['Meeting Date'])) and q not in qtrs: qtrs[q] = f
        except: pass
    return qtrs

@st.cache_data(ttl=600)
def load(fp):
    # OPTIMIZATION 2: Parse dates in C-engine during read
    try:
        return pd.read_csv(fp, parse_dates=['Meeting Date', 'Record Date'], dayfirst=True)
    except ValueError:
        return pd.read_csv(fp) # Fallback if cols missing

def calc_stats(df):
    dv = df[df['Votable Proposal']=='Yes'].copy() if 'Votable Proposal' in df.columns else df.copy()
    total_props = len(dv)
    voted_props = len(dv[dv['Voted (Yes, No, Partial)'].isin(['Yes','Partial'])]) if 'Voted (Yes, No, Partial)' in dv.columns else len(dv)
    votable_mtgs = dv['Meeting ID'].nunique() if 'Meeting ID' in dv.columns else 0
    
    # OPTIMIZATION 3: Vectorized calculation instead of O(N^2) loop
    voted_mtgs = votable_mtgs
    if 'Voted (Yes, No, Partial)' in dv.columns and 'Meeting ID' in dv.columns:
        voted_mtgs = dv[dv['Voted (Yes, No, Partial)'].isin(['Yes','Partial'])]['Meeting ID'].nunique()
    
    s = {'votable_mtgs': votable_mtgs, 'voted_mtgs': voted_mtgs, 'mtg_rate': round(100*voted_mtgs/votable_mtgs,2) if votable_mtgs else 0,
         'votable_props': total_props, 'voted_props': voted_props, 'prop_rate': round(100*voted_props/total_props,2) if total_props else 0,
         'for': 0, 'against': 0, 'abstain': 0, 'withhold': 0, 'with_mgmt': 0, 'vs_mgmt': 0, 'with_pol': 0, 'vs_pol': 0,
         'sh_props': 0, 'msop1': 0, 'msop2': 0, 'msop3': 0, 'dissent_mtgs': 0}
    
    if 'Vote Instruction' in dv.columns:
        vc = dv['Vote Instruction'].value_counts()
        s.update({'for': int(vc.get('For',0))+int(vc.get('One Year',0)), 'against': int(vc.get('Against',0)), 'abstain': int(vc.get('Abstain',0)),
                  'withhold': int(vc.get('Withhold',0)), 'msop1': int(vc.get('One Year',0)), 'msop2': int(vc.get('Two Years',0)), 'msop3': int(vc.get('Three Years',0))})
    if 'Vote Against Management' in dv.columns:
        s['with_mgmt'], s['vs_mgmt'] = int((dv['Vote Against Management']=='No').sum()), int((dv['Vote Against Management']=='Yes').sum())
        if 'Meeting ID' in dv.columns: s['dissent_mtgs'] = dv[dv['Vote Against Management']=='Yes']['Meeting ID'].nunique()
    if 'Vote Against Policy' in dv.columns:
        s['with_pol'], s['vs_pol'] = int((dv['Vote Against Policy']=='No').sum()), int((dv['Vote Against Policy']=='Yes').sum())
    if 'Proponent' in dv.columns: s['sh_props'] = int((dv['Proponent']=='Shareholder').sum())
    for k in ['for','against','abstain','withhold','with_mgmt','vs_mgmt','with_pol','vs_pol']: s[k+'_pct'] = round(100*s[k]/total_props,2) if total_props else 0
    s['dissent_pct'] = round(100*s['dissent_mtgs']/votable_mtgs,2) if votable_mtgs else 0
    return s, dv

def prog(v, l):
    ticks = ''.join(f'<div class="prog-tick" style="left:{i}%"><div class="prog-tick-lbl">{i}%</div></div>' for i in range(0,101,20))
    return f'<div class="prog-wrap"><div class="prog-lbl">{l} - {pct(v)}</div><div class="prog-cont"><div class="prog-fill" style="width:{min(v,100)}%;background:{C["p"]}">{pct(v)}</div><div class="prog-ticks">{ticks}</div></div></div>'

def donut(w, a, t):
    fig = go.Figure(go.Pie(labels=['Aligned','Divergent'], values=[w,a], hole=0.65, marker_colors=[C['p'],C['d']], textinfo='percent', textposition='outside', showlegend=False))
    fig.add_annotation(text=f"<b>{w:.1f}%</b>", x=0.5, y=0.5, font=dict(size=18, color=C['p']), showarrow=False)
    fig.update_layout(title=dict(text=t, x=0.5), height=220, margin=dict(l=20,r=20,t=45,b=20), paper_bgcolor='rgba(0,0,0,0)')
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
        fig.update_layout(title=dict(text=title), height=350, margin=dict(l=20,r=20,t=45,b=100),
                          yaxis=dict(title=ylab, showgrid=True, gridcolor='#E2E8F0'), xaxis=dict(tickangle=-45), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    else:
        fig = go.Figure(go.Bar(y=data.index, x=data.values, orientation='h', marker_color=C['p'], text=data.values, textposition='outside'))
        fig.update_layout(title=dict(text=title), height=max(250,len(data)*32), margin=dict(l=20,r=60,t=45,b=30),
                          xaxis=dict(title=ylab, showgrid=True, gridcolor='#E2E8F0'), yaxis_title="", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    return fig

def cnt_yes(df, col): return (df[col]=='Yes').sum() if col in df.columns else 0

def mkt_breakdown(df):
    if 'Country' not in df.columns or 'Meeting ID' not in df.columns: return pd.DataFrame()
    def calc(g):
        no = g[g['Voted (Yes, No, Partial)']=='No'] if 'Voted (Yes, No, Partial)' in g.columns else pd.DataFrame()
        unvoted = len({m for m in no['Meeting ID'].unique() if not g[g['Meeting ID']==m]['Voted (Yes, No, Partial)'].isin(['Yes','Partial']).any()}) if len(no) else 0
        voted = len(g[g['Voted (Yes, No, Partial)'].isin(['Yes','Partial'])]) if 'Voted (Yes, No, Partial)' in g.columns else len(g)
        return pd.Series({'Mtgs Votable': g['Meeting ID'].nunique(), 'Mtgs Voted': g['Meeting ID'].nunique()-unvoted,
            'Mtgs Dissent': g[g['Vote Against Management']=='Yes']['Meeting ID'].nunique() if 'Vote Against Management' in g.columns else 0,
            'Props Voted': voted, 'Vs Mgmt': cnt_yes(g,'Vote Against Management'), 'Vs Policy': cnt_yes(g,'Vote Against Policy')})
    return df.groupby('Country').apply(calc, include_groups=False).reset_index().sort_values('Mtgs Votable', ascending=False)

def main():
    with st.sidebar:
        st.title("⚙️ Control Panel")
        if not os.path.exists("./data"): st.error("Data directory not found"); st.stop()
        funds = scan_dir("./data")
        if not funds: st.warning("No fund data found."); st.stop()
        fund = st.selectbox("Select Fund", list(funds.keys()), format_func=lambda x: FUNDS.get(x,x))
        qtrs = get_fund_qtrs(funds[fund])
        sel_qtrs = [q for q in gen_qtrs() if q in qtrs] or list(qtrs.keys())
        qtr_sel = st.selectbox("Select Period", sel_qtrs) if sel_qtrs else None
        st.divider(); st.markdown("**Export**")
    
    df = load(qtrs[qtr_sel]) if fund and qtr_sel and qtr_sel in qtrs else pd.DataFrame()
    with st.sidebar:
        if not df.empty: st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), f"{fund}_{qtr_sel.replace(' ','_')}.csv", "text/csv", use_container_width=True)
        st.divider(); st.caption(f"Generated: {datetime.now().strftime('%d %b %Y')}")
    
    if df.empty: st.subheader("Proxy Voting Dashboard"); st.write("No data. Select fund/period."); st.stop()
    
    st.subheader("Proxy Voting Dashboard")
    c1, c2 = st.columns([1,1.5]); c1.write(f"**Account:** {FUNDS.get(fund,fund)}"); c2.write(f"**Period:** {qtr_sel}")
    s, dv = calc_stats(df)
    
    st.markdown('<p class="section-header">Voting Overview</p>', unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("##### Voting Data")
        st.dataframe(pd.DataFrame({'Meeting Overview':['Votable Meetings','Meetings Voted','Meetings with Dissent'],'Number':[s['votable_mtgs'],s['voted_mtgs'],s['dissent_mtgs']],'Percentage':['—',pct(s['mtg_rate']),pct(s['dissent_pct'])]}), hide_index=True)
        st.dataframe(pd.DataFrame({
            'Proposal Overview':['Votable Proposals','Proposals Voted','Votes FOR','Votes AGAINST','Votes ABSTAIN','Votes WITHHOLD','With Management','Against Management','With Policy','Against Policy','Shareholder Proposals','MSOP 1 Year','MSOP 2 Years','MSOP 3 Years'],
            'Number':[s['votable_props'],s['voted_props'],s['for'],s['against'],s['abstain'],s['withhold'],s['with_mgmt'],s['vs_mgmt'],s['with_pol'],s['vs_pol'],s['sh_props'],s['msop1'],s['msop2'],s['msop3']],
            'Percentage':['—',pct(s['prop_rate']),pct(s['for_pct']),pct(s['against_pct']),pct(s['abstain_pct']),pct(s['withhold_pct']),pct(s['with_mgmt_pct']),pct(s['vs_mgmt_pct']),pct(s['with_pol_pct']),pct(s['vs_pol_pct'])]+['—']*4
        }), hide_index=True, height=560)
    with c4:
        st.markdown("##### Voting Statistics"); st.markdown(prog(s['mtg_rate'],"Meetings Voted"), unsafe_allow_html=True); st.markdown(prog(s['prop_rate'],"Proposals Voted"), unsafe_allow_html=True)
        st.markdown("##### Vote Distribution")
        if fig := vote_pie(s): st.plotly_chart(fig, use_container_width=True)
        st.markdown("##### Alignment Analysis")
        ac1, ac2 = st.columns(2); ac1.plotly_chart(donut(s['with_mgmt_pct'],s['vs_mgmt_pct'],"Management"), use_container_width=True); ac2.plotly_chart(donut(s['with_pol_pct'],s['vs_pol_pct'],"Policy"), use_container_width=True)
    
    st.divider()
    st.markdown('<p class="section-header">Market & Category Breakdown</p>', unsafe_allow_html=True)
    st.markdown("##### Market Breakdown")
    if not (mkt := mkt_breakdown(dv)).empty: st.dataframe(mkt, use_container_width=True, hide_index=True)
    if fig := bar(dv, 'Country', 'Meeting ID', "Meeting Activity by Market", "Meetings", vertical=True): st.plotly_chart(fig, use_container_width=True)
    st.markdown("##### Proposal Categories")
    if 'Proposal Code Category' in dv.columns:
        def calc_cat(g):
            voted = len(g[g['Voted (Yes, No, Partial)'].isin(['Yes','Partial'])]) if 'Voted (Yes, No, Partial)' in g.columns else len(g)
            return pd.Series({'Props Votable': len(g), 'Props Voted': voted, 'Vs Mgmt': cnt_yes(g,'Vote Against Management'),
                'Vs Policy': cnt_yes(g,'Vote Against Policy'), 'SH Props': (g['Proponent']=='Shareholder').sum() if 'Proponent' in g.columns else 0})
        cat = dv.groupby('Proposal Code Category').apply(calc_cat, include_groups=False).reset_index().rename(columns={'Proposal Code Category':'Category'})
        st.dataframe(cat.sort_values('Props Votable', ascending=False).head(10), use_container_width=True, hide_index=True)
    if fig := bar(dv, 'Proposal Code Category', 'Proposal Text', "Proposal Activity by Category", "Proposals", use_cnt=True, vertical=True): st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    st.markdown('<p class="section-header">Detailed Vote Analysis</p>', unsafe_allow_html=True)
    t1, t2 = st.tabs(["🏢 Meetings List", "📋 All Proposals"])
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
        st.dataframe(mdf[display_cols], use_container_width=True, hide_index=True); st.caption(f"Total: {len(mdf):,} meetings")
    with t2:
        pc = [c for c in ['Company Name','Ticker','Industry Sector','Meeting Date','Proposal Number','Proposal Text','Proponent',
                          'Votable Proposal','Voted (Yes, No, Partial)','Management Recommendation','ISS Recommendation',
                          'Vote Instruction','Vote Against Management','Vote Against Policy'] if c in dv.columns]
        pdf = dv[pc].drop_duplicates()
        if not pdf.empty:
            with st.expander("🔍 Filters"):
                f1,f2,f3 = st.columns(3)
                cos = ['All']+sorted(pdf['Company Name'].dropna().unique().tolist()) if 'Company Name' in pdf.columns else ['All']
                pros = ['All']+list(pdf['Proponent'].dropna().unique()) if 'Proponent' in pdf.columns else ['All']
                sc, sp, sm = f1.selectbox("Company",cos), f2.selectbox("Proponent",pros), f3.selectbox("Management Alignment",['All','With Management','Against Management'])
            flt = pdf.copy()
            if sc!='All' and 'Company Name' in flt.columns: flt = flt[flt['Company Name']==sc]
            if sp!='All' and 'Proponent' in flt.columns: flt = flt[flt['Proponent']==sp]
            if sm!='All' and 'Vote Against Management' in flt.columns: flt = flt[flt['Vote Against Management']==('No' if sm=='With Management' else 'Yes')]
            st.dataframe(flt, use_container_width=True, hide_index=True); st.caption(f"Showing {len(flt):,} of {len(pdf):,} proposals")

if __name__ == "__main__": main()
