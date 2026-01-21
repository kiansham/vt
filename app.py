import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import pycountry_convert as pc
import os
from datetime import datetime

st.set_page_config(page_title="Proxy Voting Dashboard", page_icon=":material/how_to_vote:", layout="wide", initial_sidebar_state="expanded")
st.html("<style>#MainMenu,footer{visibility:hidden}</style>")

CLR = {"pri": "#3498db", "danger": "#e74c3c", "warn": "#f39c12", "success": "#2ecc71", "text": "#1c1919", "gray": "#6B7280"}
COUNTRY_NAME_MAP = {"Marshall Isl": "Marshall Islands", "Virgin Isl (UK)": "British Virgin Islands", "Faroe Islands": "Faroe Islands", "Curacao": "Curaçao", "Isle of Man": "Isle of Man", "Guernsey": "Guernsey", "Jersey": "Jersey", "Gibraltar": "Gibraltar"}
COUNTRY_REGIONS = {"USA": "North America", "Canada": "North America", "Mexico": "North America", "Brazil": "South America", "Argentina": "South America", "Chile": "South America", "Colombia": "South America", "Peru": "South America", "United Kingdom": "Europe", "Germany": "Europe", "France": "Europe", "Italy": "Europe", "Spain": "Europe", "Netherlands": "Europe", "Switzerland": "Europe", "Sweden": "Europe", "Norway": "Europe", "Denmark": "Europe", "Finland": "Europe", "Belgium": "Europe", "Austria": "Europe", "Ireland": "Europe", "Poland": "Europe", "Portugal": "Europe", "Luxembourg": "Europe", "Guernsey": "Europe", "Jersey": "Europe", "Gibraltar": "Europe", "Isle of Man": "Europe", "Hungary": "Europe", "Japan": "Asia", "China": "Asia", "Hong Kong": "Asia", "Taiwan": "Asia", "South Korea": "Asia", "India": "Asia", "Singapore": "Asia", "Malaysia": "Asia", "Indonesia": "Asia", "Philippines": "Asia", "Thailand": "Asia", "Saudi Arabia": "Asia", "United Arab Emirates": "Asia", "Israel": "Asia", "Kuwait": "Asia", "Turkey": "Asia", "South Africa": "Africa", "Egypt": "Africa", "Australia": "Oceania", "New Zealand": "Oceania", "Cayman Islands": "North America", "Bermuda": "North America", "Bahamas": "North America", "Puerto Rico": "North America", "Virgin Isl (UK)": "North America", "Curacao": "South America", "Panama": "North America"}

@st.cache_data(ttl=3600)
def load_funds():
    try:
        df = pd.read_csv("./data/funds.csv")
        return {row['display_name']: f"./data/consolidated/{row['display_name']}_consolidated.csv"
                for _, row in df.iterrows()
                if os.path.exists(f"./data/consolidated/{row['display_name']}_consolidated.csv")}
    except:
        return {}

@st.cache_data(ttl=600)
def load(filepath):
    if not filepath or not os.path.exists(filepath):
        return pd.DataFrame()
    try:
        return pd.read_csv(filepath, parse_dates=['Meeting Date', 'Record Date'])
    except:
        return pd.read_csv(filepath)

@st.cache_data
def get_voting_policy(filepath):
    if not filepath or not os.path.exists(filepath):
        return "N/A"
    try:
        df = pd.read_csv(filepath, nrows=1)
        return df['Voting Policy'].iloc[0] if 'Voting Policy' in df.columns else "N/A"
    except:
        return "N/A"

@st.cache_data
def _convert_to_iso(countries: tuple) -> list:
    results = []
    for country in countries:
        try:
            results.append(pc.country_name_to_country_alpha3(COUNTRY_NAME_MAP.get(country, country)))
        except:
            results.append('not found')
    return results

def ensure_datetime(df):
    if df.empty or 'Meeting Date' not in df.columns:
        return df
    if not pd.api.types.is_datetime64_any_dtype(df['Meeting Date']):
        df['Meeting Date'] = pd.to_datetime(df['Meeting Date'], errors='coerce')
    return df

def date_bounds(df):
    df = ensure_datetime(df)
    if df.empty or 'Meeting Date' not in df.columns:
        return datetime.now().date() - pd.Timedelta(days=365), datetime.now().date()
    dates = df['Meeting Date'].dropna()
    if dates.empty:
        return datetime.now().date() - pd.Timedelta(days=365), datetime.now().date()
    min_date, max_date = dates.min().date(), dates.max().date()
    min_date = min_date.replace(day=1) if min_date.day <= 5 else min_date
    next_month = max_date.replace(day=28) + pd.Timedelta(days=4)
    last_day = (next_month - pd.Timedelta(days=next_month.day)).day
    max_date = max_date.replace(day=last_day) if max_date.day >= last_day - 4 else max_date
    return min_date, max_date

def filter_dates(df, start, end):
    df = ensure_datetime(df)
    if df.empty or 'Meeting Date' not in df.columns:
        return df
    return df[(df['Meeting Date'] >= pd.to_datetime(start)) & (df['Meeting Date'] <= pd.to_datetime(end))].copy()

def apply_filters(df, filters):
    for col, vals in filters.items():
        if vals and col in df.columns:
            df = df[df[col].isin(vals)]
    return df

def apply_esg_filter(df, esg_selection):
    if not esg_selection or 'ESG Pillar' not in df.columns:
        return df
    mask = pd.Series([False] * len(df), index=df.index)
    for esg in esg_selection:
        mask |= df['ESG Pillar'].str.contains(esg, case=False, na=False)
    return df[mask]

def apply_vote_filters(df, vs_mgmt, vs_iss, vs_pol):
    if vs_mgmt and 'Vote Against Management' in df.columns:
        df = df[df['Vote Against Management'] == 'Yes']
    if vs_iss and 'Vote Against ISS' in df.columns:
        df = df[df['Vote Against ISS'] == 'Yes']
    if vs_pol and 'Vote Against Policy' in df.columns:
        df = df[df['Vote Against Policy'] == 'Yes']
    return df

def has_col(df, col):
    return col in df.columns

def col_sum(df, col, val):
    return (df[col] == val).sum() if has_col(df, col) else 0

def format_pct(val):
    return f"{int(val)}%" if val == int(val) else f"{val:.1f}%"

def format_tbl_pct(val):
    if val is None or val == '':
        return ""
    return f"{round(val):.0f}%" if round(val, 2) in (0, 100) else f"{val:.2f}%"

def calc_stats(df):
    votable_df = df[df['Votable Proposal'] == 'Yes'].copy() if has_col(df, 'Votable Proposal') else df.copy()
    total_props = len(votable_df)
    num_meetings = votable_df['Meeting ID'].nunique() if has_col(votable_df, 'Meeting ID') else 0
    voted_mask = votable_df['Voted (Yes, No, Partial)'].isin(['Yes', 'Partial']) if has_col(votable_df, 'Voted (Yes, No, Partial)') else pd.Series([True] * len(votable_df))
    num_voted = voted_mask.sum()
    num_voted_meetings = votable_df.loc[voted_mask, 'Meeting ID'].nunique() if has_col(votable_df, 'Meeting ID') else num_meetings

    stats = {
        'votable_mtgs': num_meetings, 'voted_mtgs': num_voted_meetings,
        'mtg_rate': 100 * num_voted_meetings / num_meetings if num_meetings else 0,
        'votable_props': total_props, 'voted_props': num_voted,
        'prop_rate': 100 * num_voted / total_props if total_props else 0,
        'dissent_mtgs': 0, 'dissent_pct': 0
    }
    for key in ['for', 'against', 'abstain', 'withhold', 'with_mgmt', 'vs_mgmt', 'with_iss', 'vs_iss', 'with_pol', 'vs_pol', 'sh_props', 'msop1', 'msop2', 'msop3']:
        stats[key] = 0

    if has_col(votable_df, 'Vote Instruction'):
        vote_counts = votable_df['Vote Instruction'].value_counts()
        for key, label in [('for', 'For'), ('against', 'Against'), ('abstain', 'Abstain'), ('withhold', 'Withhold'), ('msop1', 'One Year'), ('msop2', 'Two Years'), ('msop3', 'Three Years')]:
            stats[key] = int(vote_counts.get(label, 0))
        stats['for'] += int(vote_counts.get('One Year', 0))

    voted_df = votable_df[voted_mask] if has_col(votable_df, 'Voted (Yes, No, Partial)') else votable_df

    if has_col(votable_df, 'Vote Against Management'):
        stats['with_mgmt'] = int(col_sum(voted_df, 'Vote Against Management', 'No'))
        stats['vs_mgmt'] = int(col_sum(voted_df, 'Vote Against Management', 'Yes'))
        if has_col(votable_df, 'Meeting ID'):
            stats['dissent_mtgs'] = voted_df[voted_df['Vote Against Management'] == 'Yes']['Meeting ID'].nunique()
        stats['dissent_pct'] = round(100 * stats['dissent_mtgs'] / num_meetings, 2) if num_meetings else 0

    if has_col(votable_df, 'Vote Against ISS'):
        stats['with_iss'] = int(col_sum(voted_df, 'Vote Against ISS', 'No'))
        stats['vs_iss'] = int(col_sum(voted_df, 'Vote Against ISS', 'Yes'))

    if has_col(votable_df, 'Vote Against Policy'):
        stats['with_pol'] = int(col_sum(voted_df, 'Vote Against Policy', 'No'))
        stats['vs_pol'] = int(col_sum(voted_df, 'Vote Against Policy', 'Yes'))

    if has_col(votable_df, 'Proponent'):
        shareholder_mask = votable_df['Proponent'] == 'Shareholder'
        stats['sh_props'] = int((shareholder_mask & voted_mask).sum()) if has_col(votable_df, 'Voted (Yes, No, Partial)') else int(shareholder_mask.sum())

    for key in ['for', 'against', 'abstain', 'withhold', 'with_mgmt', 'vs_mgmt', 'with_iss', 'vs_iss', 'with_pol', 'vs_pol', 'sh_props', 'msop1', 'msop2', 'msop3']:
        stats[key + '_pct'] = round(100 * stats[key] / num_voted, 2) if num_voted else 0

    return stats, votable_df

def market_breakdown(df):
    if not has_col(df, 'Country') or not has_col(df, 'Meeting ID'):
        return pd.DataFrame()

    def calc_market(group):
        voted_mask = group['Voted (Yes, No, Partial)'].isin(['Yes', 'Partial']) if has_col(group, 'Voted (Yes, No, Partial)') else pd.Series([True] * len(group))
        unvoted_meetings = group.loc[~voted_mask, 'Meeting ID'].unique()
        actually_unvoted = len([mtg for mtg in unvoted_meetings if not voted_mask[group['Meeting ID'] == mtg].any()])
        return pd.Series({
            'Meetings Votable': group['Meeting ID'].nunique(),
            'Meetings Voted': group['Meeting ID'].nunique() - actually_unvoted,
            'Meetings with at least one vote against mgmt': group[group['Vote Against Management'] == 'Yes']['Meeting ID'].nunique() if has_col(group, 'Vote Against Management') else 0,
            'Proposals Voted': voted_mask.sum(),
            'Vote Against Mgmt': col_sum(group, 'Vote Against Management', 'Yes'),
            'Vote Against ISS': col_sum(group, 'Vote Against ISS', 'Yes'),
            'Vote Against Policy': col_sum(group, 'Vote Against Policy', 'Yes')
        })

    return df.groupby('Country').apply(calc_market, include_groups=False).reset_index().sort_values('Meetings Votable', ascending=False)

def calc_category_stats(group):
    num_voted = (group['Voted (Yes, No, Partial)'].isin(['Yes', 'Partial'])).sum() if has_col(group, 'Voted (Yes, No, Partial)') else len(group)
    vote_counts = group['Vote Instruction'].value_counts() if has_col(group, 'Vote Instruction') else pd.Series()
    for_count = int(vote_counts.get('For', 0))
    against_count = int(vote_counts.get('Against', 0))
    abstain_count = int(vote_counts.get('Abstain', 0))
    for_against_total = for_count + against_count
    total_votes = for_count + against_count + abstain_count
    return pd.Series({
        'Proposals Votable': len(group),
        'Proposals Voted': num_voted,
        '% For': format_tbl_pct(100 * for_count / for_against_total) if for_against_total else None,
        '% Against': format_tbl_pct(100 * against_count / for_against_total) if for_against_total else None,
        '% Abstain': format_tbl_pct(100 * abstain_count / total_votes) if total_votes else None,
        'Vote Against Mgmt': col_sum(group, 'Vote Against Management', 'Yes'),
        'Vote Against ISS': col_sum(group, 'Vote Against ISS', 'Yes'),
        'Vote Against Policy': col_sum(group, 'Vote Against Policy', 'Yes'),
        'Shareholder Proposals': col_sum(group, 'Proponent', 'Shareholder')
    })

def plot_donut(labels, values, colors, center_text, title=None, text_color=None, show_legend=False, show_pct_in_legend=False, reserve_legend_space=False, height=220):
    total = sum(values) if values else 1
    if show_pct_in_legend:
        labels = [f"{label} - {100 * val / total:.1f}%" for label, val in zip(labels, values)]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.6, marker_colors=colors,
        textinfo='none', showlegend=show_legend,
        hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>"
    ))
    fig.add_annotation(text=center_text, x=0.5, y=0.5, font=dict(size=16, color=text_color or CLR['text']), showarrow=False)
    margin = dict(l=20, r=80 if show_legend or reserve_legend_space else 20, t=40 if title else 20, b=20)
    layout = dict(height=height, margin=margin, paper_bgcolor='rgba(0,0,0,0)')
    if title:
        layout['title'] = dict(text=title, x=0, xanchor='left', font=dict(size=14))
    if show_legend:
        layout['legend'] = dict(yanchor="middle", y=0.5, xanchor="left", x=0.85)
    fig.update_layout(**layout)
    return fig

@st.cache_data
def prepare_map_data(geo_df_json: str) -> tuple:
    geo_df = pd.read_json(geo_df_json)
    if geo_df.empty or "Country" not in geo_df.columns:
        return None, None
    df = geo_df.groupby("Country")["Meeting ID"].nunique().reset_index(name="count")
    df['iso_code'] = _convert_to_iso(tuple(df['Country']))
    df = df[df['iso_code'] != 'not found']
    if df.empty:
        return None, None
    return df.to_json(), df['count'].max()

def render_map(geo_df: pd.DataFrame, region: str):
    if geo_df.empty or "Country" not in geo_df.columns or geo_df["Country"].dropna().empty:
        st.info("No geographic data available for selected region.")
        return
    map_data_json, max_count = prepare_map_data(geo_df[['Country', 'Meeting ID']].to_json())
    if map_data_json is None:
        st.warning("No valid geographic data to display on the map.")
        return
    df = pd.read_json(map_data_json)
    SCOPES = {"Global": "world", "North America": "north america", "South America": "south america", "Europe": "europe", "Asia": "asia", "Africa": "africa"}
    BBOXES = {"Oceania": {"lon": [110, 180], "lat": [-50, 10]}, "South America": {"lon": [-82, -34], "lat": [-56, 13]}, "Africa": {"lon": [-20, 55], "lat": [-35, 38]}, "North America": {"lon": [-170, -50], "lat": [5, 75]}}

    fig = px.choropleth(df, locations="iso_code", color="count", hover_name="Country", color_continuous_scale="teal", range_color=[0, max_count or 1])

    if region in BBOXES:
        geo_args = {"scope": "world", "fitbounds": False, "lonaxis_range": BBOXES[region]["lon"], "lataxis_range": BBOXES[region]["lat"]}
    else:
        geo_args = {"scope": SCOPES.get(region, "world"), "fitbounds": False if region == "Global" else "locations"}

    fig.update_geos(**geo_args)
    fig.update_layout(
        title=dict(text='Meetings by Country', x=0, xanchor='left', font=dict(size=14)),
        geo=dict(bgcolor='rgba(0,0,0,0)', showframe=False, showcoastlines=False, showcountries=True, showland=False, showocean=False, showlakes=False),
        height=400, margin=dict(l=10, r=40, t=40, b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', uirevision='constant'
    )
    fig.update_coloraxes(colorbar=dict(thickness=4, len=0.6, x=0.95, xpad=3, y=0.5))
    fig.update_traces(hovertemplate="<b>%{hovertext}</b><br>Meetings: %{z}<extra></extra>")
    st.plotly_chart(fig, use_container_width=True, key=f"map_{region}")

def plot_category_bar(df, col_name, top_n=10, title=None):
    if df.empty or col_name not in df.columns:
        return None
    counts = df[col_name].value_counts()
    total = counts.sum()
    if total == 0:
        return None
    top_cats = counts.head(top_n)
    other_count = counts.iloc[top_n:].sum() if len(counts) > top_n else 0
    if other_count > 0:
        top_cats = pd.concat([top_cats, pd.Series({'Other': other_count})])
    pct_data = (top_cats / total * 100).round(1)

    fig = go.Figure(go.Bar(
        x=pct_data.index, y=pct_data.values, orientation='v',
        marker_color=CLR['pri'], text=[f"{v:.1f}%" for v in pct_data.values], textposition='outside'
    ))
    fig.update_layout(
        height=300, margin=dict(l=10, r=10, t=40, b=80),
        xaxis=dict(tickangle=-45), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
    )
    if title:
        fig.update_layout(title=dict(text=title, x=0, xanchor='left', font=dict(size=14)))
    fig.update_yaxes(range=[0, max(pct_data.values) * 1.15])
    return fig

def num_col():
    return st.column_config.NumberColumn(format="localized")

def usd_mil_col():
    return st.column_config.NumberColumn(format="$ %.1fM")

def pct_col():
    return st.column_config.NumberColumn(format="%.2f %%")

def date_col():
    return st.column_config.DateColumn(format="MMM DD, YYYY")

def render_market_table(market_data):
    if not market_data.empty:
        st.dataframe(market_data, hide_index=True, column_config={
            'Meetings Votable': num_col(), 'Meetings Voted': num_col(),
            'Meetings with at least one vote against mgmt': num_col(),
            'Proposals Voted': num_col(), 'Vote Against Mgmt': num_col(),
            'Vote Against ISS': num_col(), 'Vote Against Policy': num_col()
        })

EMPTY_MARKET = pd.DataFrame({
    'Country': [], 'Meetings Votable': [], 'Meetings Voted': [],
    'Meetings with at least one vote against mgmt': [], 'Proposals Voted': [],
    'Vote Against Mgmt': [], 'Vote Against ISS': [], 'Vote Against Policy': []
})

def main():
    funds = load_funds()
    if 'selected_dates' not in st.session_state:
        st.session_state.selected_dates = None
    if 'prev_fund' not in st.session_state:
        st.session_state.prev_fund = None

    with st.sidebar:
        st.title(":material/settings: Control Panel")
        if not os.path.exists("./data"):
            st.error("Data directory not found")
            st.stop()
        if not funds:
            st.warning("No funds found in funds.csv.")
            st.stop()
        fund_list = list(funds.keys())
        fund = st.selectbox("Select Fund", fund_list, index=fund_list.index("Firm") if "Firm" in fund_list else 0)

    df_full = load(funds[fund])
    voting_policy = get_voting_policy(funds[fund])
    min_date, max_date = date_bounds(df_full)

    if st.session_state.selected_dates is not None:
        prev_start, prev_end = st.session_state.selected_dates
        clamped_start = max(min_date, min(prev_start, max_date))
        clamped_end = min(max_date, max(prev_end, min_date))
        initial_dates = (clamped_start, clamped_end) if clamped_start <= clamped_end else ()
    else:
        initial_dates = ()

    with st.sidebar:
        st.markdown("**:material/calendar_month: Select Period**")
        date_range = st.date_input("", value=initial_dates, min_value=min_date, max_value=max_date, format="MM/DD/YYYY", label_visibility="collapsed")
        has_dates = isinstance(date_range, tuple) and len(date_range) == 2
        if has_dates:
            start, end = date_range
            st.session_state.selected_dates = (start, end)
        else:
            start, end = min_date, max_date

        today = datetime.now().date()
        current_quarter = (today.month - 1) // 3
        if current_quarter == 0:
            quarter_end = datetime(today.year - 1, 12, 31).date()
            quarter_start = datetime(today.year - 1, 10, 1).date()
        else:
            quarter_end = datetime(today.year, current_quarter * 3, 1).date() - pd.Timedelta(days=1)
            quarter_start = datetime(today.year, (current_quarter - 1) * 3 + 1, 1).date()
        year_start = datetime(today.year - 1, 1, 1).date()
        year_end = datetime(today.year - 1, 12, 31).date()

        period_pill = st.pills("Quick Select", options=[":material/date_range: Last Quarter", ":material/calendar_today: Last Year"], key="period_pills", label_visibility="collapsed")
        if period_pill == ":material/date_range: Last Quarter":
            q_start_clamped = max(min_date, quarter_start)
            q_end_clamped = min(max_date, quarter_end)
            if q_start_clamped <= q_end_clamped and st.session_state.selected_dates != (q_start_clamped, q_end_clamped):
                st.session_state.selected_dates = (q_start_clamped, q_end_clamped)
                st.rerun()
        elif period_pill == ":material/calendar_today: Last Year":
            y_start_clamped = max(min_date, year_start)
            y_end_clamped = min(max_date, year_end)
            if y_start_clamped <= y_end_clamped and st.session_state.selected_dates != (y_start_clamped, y_end_clamped):
                st.session_state.selected_dates = (y_start_clamped, y_end_clamped)
                st.rerun()

        with st.expander("**:material/filter_alt: Filters**"):
            filter_source = df_full if df_full is not None and not df_full.empty else pd.DataFrame()

            proponent_pills = st.pills("Proponent", options=[":material/business: Mgmt", ":material/person: Shareholder"], selection_mode="multi", key="proponent_pills")
            prop_map = {":material/business: Mgmt": "Management", ":material/person: Shareholder": "Shareholder"}
            proponent_filter = [prop_map[p] for p in proponent_pills if p in prop_map]

            vote_against_pills = st.pills("Vote Against", options=[":material/gavel: Mgmt", ":material/policy: ISS", ":material/rule: Policy"], selection_mode="multi", key="vote_against_pills")
            vs_mgmt = ":material/gavel: Mgmt" in vote_against_pills
            vs_iss = ":material/policy: ISS" in vote_against_pills
            vs_pol = ":material/rule: Policy" in vote_against_pills

            esg_pills = st.pills("ESG Pillar", options=[":material/eco: E", ":material/groups: S", ":material/account_balance: G"], selection_mode="multi", key="esg_pills")
            esg_map = {":material/eco: E": "E", ":material/groups: S": "S", ":material/account_balance: G": "G"}
            esg_filter = [esg_map[p] for p in esg_pills if p in esg_map]

            filters = {}
            filters['Proposal Code Category'] = st.multiselect("Proposal Category", sorted(filter_source['Proposal Code Category'].dropna().unique()) if 'Proposal Code Category' in filter_source.columns else [])
            filters['Proposal Subcategory'] = st.multiselect("Proposal Subcategory", sorted(filter_source['Proposal Subcategory'].dropna().unique()) if 'Proposal Subcategory' in filter_source.columns else [])
            filters['Country'] = st.multiselect("Country", sorted(filter_source['Country'].dropna().unique()) if 'Country' in filter_source.columns else [])
            region = st.selectbox("Region", ["Global", "North America", "South America", "Europe", "Asia", "Africa", "Oceania"], key="map_region")

            if st.button("Clear All Filters", type="secondary"):
                st.rerun()

    effective_region = COUNTRY_REGIONS.get(filters['Country'][0], "Global") if filters.get('Country') and len(filters['Country']) == 1 else region

    df = filter_dates(df_full, start, end) if has_dates else pd.DataFrame()
    if has_dates and not df.empty:
        if proponent_filter and 'Proponent' in df.columns:
            df = df[df['Proponent'].isin(proponent_filter)]
        df = apply_esg_filter(df, esg_filter)
        df = apply_filters(df, filters)
        df = apply_vote_filters(df, vs_mgmt, vs_iss, vs_pol)
        if region != "Global" and not filters.get('Country') and 'Country' in df.columns:
            region_countries = [c for c, r in COUNTRY_REGIONS.items() if r == region]
            df = df[df['Country'].isin(region_countries)]

    with st.sidebar:
        if has_dates and not df.empty:
            st.download_button(":material/download: Download CSV", df.to_csv(index=False).encode('utf-8'), f"{fund}_{start:%Y%m%d}-{end:%Y%m%d}.csv", "text/csv")
        st.caption(f"Generated: {datetime.now():%d %b %Y}")

    has_data = has_dates and not df.empty and len(df) >= 2
    st.subheader(":material/how_to_vote: Proxy Voting Dashboard")
    hdr1, hdr2, hdr3 = st.columns([1,0.8,0.9])
    hdr1.write(f"**Account:** {fund}")
    hdr2.write(f"**Period:** {start:%b %d, %Y} - {end:%b %d, %Y}" if has_dates else "**Period:** Select dates to view data")
    hdr3.write(f"**Voting Policy:** {voting_policy}")

    stats, votable_df = calc_stats(df) if has_data else ({k: '' for k in ['votable_mtgs', 'voted_mtgs', 'dissent_mtgs', 'mtg_rate', 'dissent_pct', 'votable_props', 'voted_props', 'prop_rate', 'for', 'against', 'abstain', 'withhold', 'for_pct', 'against_pct', 'abstain_pct', 'withhold_pct', 'with_mgmt', 'vs_mgmt', 'with_pol', 'vs_pol', 'with_mgmt_pct', 'vs_mgmt_pct', 'with_pol_pct', 'vs_pol_pct', 'sh_props', 'msop1', 'msop2', 'msop3']}, pd.DataFrame())

    st.subheader(":material/analytics: Voting Overview", divider="gray")
    tbl_col, chart_col = st.columns(2)
    progress_cfg = st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)

    with tbl_col:
        st.dataframe(pd.DataFrame({
            'Meeting Overview': ['Votable Meetings', 'Meetings Voted', 'Meetings with at least one vote against mgmt'],
            'Number': [stats['votable_mtgs'], stats['voted_mtgs'], stats['dissent_mtgs']],
            'Percentage': [None, stats['mtg_rate'] if has_data else None, stats['dissent_pct'] if has_data else None]
        }), hide_index=True, column_config={"Number": num_col(), "Percentage": progress_cfg})

        prop_rows = [
            ('Votable Proposals', 'votable_props', None),
            ('Proposals Voted', 'voted_props', 'prop_rate'),
            ('Votes FOR', 'for', 'for_pct'),
            ('Votes AGAINST', 'against', 'against_pct'),
            ('Votes ABSTAIN', 'abstain', 'abstain_pct'),
            ('Votes WITHHOLD', 'withhold', 'withhold_pct'),
            ('With Management', 'with_mgmt', 'with_mgmt_pct'),
            ('Against Management', 'vs_mgmt', 'vs_mgmt_pct'),
            ('With Policy', 'with_pol', 'with_pol_pct'),
            ('Against Policy', 'vs_pol', 'vs_pol_pct'),
            ('Shareholder Proposals', 'sh_props', 'sh_props_pct'),
            ('MSOP 1 Year', 'msop1', 'msop1_pct'),
            ('MSOP 2 Years', 'msop2', 'msop2_pct'),
            ('MSOP 3 Years', 'msop3', 'msop3_pct'),
        ]
        st.dataframe(pd.DataFrame({
            'Proposal Overview': [r[0] for r in prop_rows],
            'Number': [stats[r[1]] if has_data else None for r in prop_rows],
            'Percentage': [stats[r[2]] if has_data and r[2] else None for r in prop_rows]
        }), hide_index=True, height=560, column_config={"Number": num_col(), "Percentage": progress_cfg})

    with chart_col:
        if has_data:
            st.markdown("##### :material/bar_chart: Vote Distribution")
            chart_data = [(label, stats[key], color) for label, key, color in [('For', 'for', CLR['pri']), ('Against', 'against', CLR['danger']), ('Abstain', 'abstain', CLR['warn']), ('Withhold', 'withhold', CLR['gray'])] if stats[key] > 0]
            if chart_data:
                labels, values, colors = zip(*chart_data)
                st.plotly_chart(plot_donut(labels, values, colors, f"<b>{sum(values):,}</b><br>Votes", text_color=CLR['pri'], show_legend=True, show_pct_in_legend=True, height=220))

            st.markdown("##### :material/done_all: Alignment Analysis")
            align_col1, align_col2 = st.columns(2)
            align_col1.plotly_chart(plot_donut(['Aligned', 'Divergent'], [stats['with_mgmt_pct'], stats['vs_mgmt_pct']], [CLR['pri'], CLR['danger']], f"<b>{format_pct(stats['with_mgmt_pct'])}</b>", "Votes with Management", CLR['pri'], show_legend=False, height=200))
            align_col2.plotly_chart(plot_donut(['Aligned', 'Divergent'], [stats['with_pol_pct'], stats['vs_pol_pct']], [CLR['pri'], CLR['danger']], f"<b>{format_pct(stats['with_pol_pct'])}</b>", "Votes with Policy", CLR['pri'], show_legend=False, height=200))

    st.subheader(":material/category: Proposal Categories", divider="gray")
    cat_cfg = {'Proposals Votable': num_col(), 'Proposals Voted': num_col(), 'Vote Against Mgmt': num_col(), 'Vote Against ISS': num_col(), 'Vote Against Policy': num_col(), 'Shareholder Proposals': num_col()}
    empty_cat = pd.DataFrame({'Category': [], 'Proposals Votable': [], 'Proposals Voted': [], '% For': [], '% Against': [], '% Abstain': [], 'Vote Against Mgmt': [], 'Vote Against ISS': [], 'Vote Against Policy': [], 'Shareholder Proposals': []})

    cat_tab, subcat_tab = st.tabs([":material/category: Categories", ":material/list: Subcategories"])
    with cat_tab:
        if has_data and 'Proposal Code Category' in votable_df.columns:
            st.dataframe(votable_df.groupby('Proposal Code Category').apply(calc_category_stats, include_groups=False).reset_index().rename(columns={'Proposal Code Category': 'Category'}).sort_values('Proposals Votable', ascending=False), hide_index=True, column_config=cat_cfg)
        else:
            st.dataframe(empty_cat, hide_index=True)
    with subcat_tab:
        if has_data and 'Proposal Subcategory' in votable_df.columns:
            st.dataframe(votable_df.groupby('Proposal Subcategory').apply(calc_category_stats, include_groups=False).reset_index().rename(columns={'Proposal Subcategory': 'Subcategory'}).sort_values('Proposals Votable', ascending=False), hide_index=True, column_config=cat_cfg)
        else:
            st.dataframe(empty_cat.rename(columns={'Category': 'Subcategory'}), hide_index=True)

    if has_data and 'Proposal Code Category' in votable_df.columns:
        bar_fig = plot_category_bar(votable_df, 'Proposal Code Category', title='% of Total Proposals by Category')
        if bar_fig:
            st.plotly_chart(bar_fig, use_container_width=True, key="bar_category")

    st.subheader(":material/public: Market Breakdown", divider="gray")
    market_bar_tab, market_map_tab = st.tabs([":material/bar_chart: Bar", ":material/map: Map"])

    with market_bar_tab:
        if has_data:
            market_data = market_breakdown(votable_df)
            render_market_table(market_data)
            if 'Country' in votable_df.columns:
                unique_countries = votable_df['Country'].dropna().unique()
                if len(unique_countries) == 1:
                    st.info(f"Only one country selected: **{unique_countries[0]}**")
                else:
                    market_bar_fig = plot_category_bar(votable_df, 'Country', top_n=10, title='% of Total Meetings by Country')
                    if market_bar_fig:
                        st.plotly_chart(market_bar_fig, use_container_width=True, key="bar_market")
        else:
            st.dataframe(EMPTY_MARKET, hide_index=True)

    with market_map_tab:
        if has_data:
            market_data = market_breakdown(votable_df)
            render_market_table(market_data)
            voted_df = votable_df[votable_df['Voted (Yes, No, Partial)'].isin(['Yes', 'Partial'])] if has_col(votable_df, 'Voted (Yes, No, Partial)') else votable_df
            render_map(voted_df, effective_region)
        else:
            st.dataframe(EMPTY_MARKET, hide_index=True)

    st.subheader(":material/ballot: Detailed Vote Analysis", divider="gray")
    meetings_tab, proposals_tab = st.tabs([":material/business: Meetings List", ":material/ballot: All Proposals"])

    with meetings_tab:
        if has_data:
            meeting_cols = [c for c in ['Meeting ID', 'Company Name', 'Primary ISIN', 'Industry Sector', 'Country', 'Market Cap (USD)', 'Meeting Date', 'Meeting Type', 'Percentage Votable Shares'] if c in votable_df.columns]
            meetings_df = votable_df.groupby('Meeting ID').agg({**{c: 'first' for c in meeting_cols if c != 'Meeting ID'}, 'Proposal Text': 'size'}).reset_index().rename(columns={'Proposal Text': 'Proposals'})

            if 'Market Cap (USD)' in meetings_df.columns:
                meetings_df['Market Cap ($M)'] = meetings_df['Market Cap (USD)'] / 1_000_000
            if 'Vote Against Management' in votable_df.columns:
                meetings_df['Meetings with at least one vote against mgmt'] = meetings_df['Meeting ID'].map(votable_df.groupby('Meeting ID')['Vote Against Management'].apply(lambda x: 'Yes' if (x == 'Yes').any() else 'No'))
            if 'Percentage Votable Shares' in meetings_df.columns:
                meetings_df = meetings_df.rename(columns={'Percentage Votable Shares': '% Votable Shares'})

            display_cols = ['Company Name', 'Primary ISIN', 'Industry Sector', 'Country', 'Market Cap ($M)', '% Votable Shares', 'Meeting Type', 'Meeting Date', 'Proposals', 'Voted', 'Meetings with at least one vote against mgmt']
            st.dataframe(meetings_df[[c for c in display_cols if c in meetings_df.columns]], hide_index=True, column_config={'Market Cap ($M)': usd_mil_col(), 'Meeting Date': date_col(), '% Votable Shares': pct_col(), 'Proposals': num_col()})
            st.caption(f"Total: {len(meetings_df):,} meetings")
        else:
            st.dataframe(pd.DataFrame({'Company Name': [], 'Primary ISIN': [], 'Industry Sector': [], 'Country': [], 'Market Cap ($M)': [], '% Votable Shares': [], 'Meeting Type': [], 'Meeting Date': [], 'Proposals': [], 'Voted': [], 'Meetings with at least one vote against mgmt': []}), hide_index=True)
            st.caption("Total: 0 meetings")

    @st.fragment
    def render_proposals_tab(proposals_df):
        if not proposals_df.empty:
            with st.expander(":material/filter_alt: Filters"):
                filter_col1, filter_col2, filter_col3 = st.columns([2.5, 1.5, 4])
                with filter_col1:
                    sel_company = st.selectbox("Company", ['All'] + sorted(proposals_df['Company Name'].dropna().unique().tolist()) if 'Company Name' in proposals_df.columns else ['All'])
                with filter_col2:
                    votable_pills = st.pills("Votable", options=[":material/check_circle: Yes", ":material/cancel: No"], selection_mode="multi", key="votable_proposals_pills")
                    votable_pill_map = {":material/check_circle: Yes": "Yes", ":material/cancel: No": "No"}
                    votable_filter = [votable_pill_map[p] for p in votable_pills if p in votable_pill_map]
                with filter_col3:
                    vote_instr_pills = st.pills("Vote Instruction", options=[":material/check: For", ":material/close: Agst", ":material/remove: Abst", ":material/block: Withhld", ":material/do_not_disturb: DNV"], selection_mode="multi", key="vote_instr_proposals_pills")
                    pill_map = {":material/check: For": "For", ":material/close: Agst": "Against", ":material/block: Withhld": "Withhold", ":material/remove: Abst": "Abstain", ":material/do_not_disturb: DNV": "Do Not Vote"}
                    vote_instr_pill_filter = [pill_map[p] for p in vote_instr_pills if p in pill_map]

            filtered_df = proposals_df.copy()
            if sel_company != 'All' and 'Company Name' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['Company Name'] == sel_company]
            if vote_instr_pill_filter and 'Vote Instruction' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['Vote Instruction'].isin(vote_instr_pill_filter)]
            if votable_filter and 'Votable Proposal' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['Votable Proposal'].isin(votable_filter)]

            st.dataframe(filtered_df, hide_index=True, column_config={'Meeting Date': date_col()})
            st.caption(f"Showing {len(filtered_df):,} of {len(proposals_df):,} proposals")
        else:
            st.dataframe(pd.DataFrame({'Company Name': [], 'ISIN': [], 'Meeting Date': [], 'Proposal Number': [], 'Category': [], 'Proposal Text': [], 'Proponent': [], 'ESG Pillar': [], 'Votable Proposal': [], 'Vote Instruction': [], 'Vote Against Management': [], 'Blended Rationale': []}), hide_index=True)
            st.caption("Showing 0 proposals")

    with proposals_tab:
        if has_data:
            proposal_cols = [c for c in ['Company Name', 'Primary ISIN', 'Industry Sector', 'Meeting Date', 'Proposal Number', 'Proposal Code Category', 'Proposal Text', 'Proponent', 'ESG Pillar', 'Votable Proposal', 'Management Recommendation', 'ISS Recommendation', 'Voting Policy Recommendation', 'Vote Instruction', 'Vote Against Management', 'Vote Against ISS', 'Vote Against Policy', 'Blended Rationale'] if c in votable_df.columns]
            proposals_df = votable_df[proposal_cols].drop_duplicates().rename(columns={'Voting Policy Recommendation': 'Policy Recommendation', 'Proposal Code Category': 'Category'})
            render_proposals_tab(proposals_df)
        else:
            render_proposals_tab(pd.DataFrame())

if __name__ == "__main__":
    main()
