"""
Sales Analytics Dashboard — Streamlit Frontend
------------------------------------------------------
Consumes the FastAPI backend (api.py) over HTTP — this dashboard has
NO direct database access. All data comes through the REST API, the
same way a real separated frontend/backend architecture would work.

Sidebar filters (date range, region) are passed as query params to
every API call, so every chart on the page reflects the same filtered
view — not just a subset of charts.

Run (two terminals):
    Terminal 1: uvicorn api:app --reload
    Terminal 2: streamlit run dashboard.py
"""

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Sales Analytics Dashboard", page_icon="📊", layout="wide")


@st.cache_data(ttl=60)
def fetch(endpoint: str, params: dict = None) -> pd.DataFrame:
    """Fetch from the API and return as a DataFrame. Cached for 60s so
    switching between chart views doesn't re-hit the API every time.

    Most endpoints return a list of records, which pandas turns into a
    DataFrame directly. /api/date-range returns a single flat dict
    instead (e.g. {"min_date": ..., "max_date": ...}) — pandas can't
    build a DataFrame from a dict of scalars without an explicit index,
    so that case needs wrapping in a list first."""
    resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        data = [data]
    return pd.DataFrame(data)


st.title("📊 Sales Analytics Dashboard")
st.caption("Retail sales data — powered by a FastAPI backend with real SQL queries")

try:
    requests.get(API_BASE, timeout=3)
except requests.exceptions.ConnectionError:
    st.error(
        "Can't reach the API backend at " + API_BASE + " — make sure it's running: "
        "`uvicorn api:app --reload` in a separate terminal."
    )
    st.stop()

# ---------------- Sidebar filters ----------------
st.sidebar.header("Filters")

bounds = fetch("/api/date-range").iloc[0]
min_date = pd.to_datetime(bounds["min_date"]).date()
max_date = pd.to_datetime(bounds["max_date"]).date()

date_range_input = st.sidebar.date_input(
    "Order date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
# date_input returns a single date while the user is mid-selection —
# only treat it as a real range once both ends are picked
if isinstance(date_range_input, tuple) and len(date_range_input) == 2:
    start_date, end_date = date_range_input
else:
    start_date, end_date = min_date, max_date

regions_df = fetch("/api/regions")
available_regions = regions_df.iloc[:, 0].tolist() if not regions_df.empty else []
selected_regions = st.sidebar.multiselect(
    "Region", options=available_regions, default=available_regions,
)

if st.sidebar.button("Reset filters"):
    st.rerun()

# Shared query params applied to every endpoint call below
filter_params = {
    "start_date": str(start_date),
    "end_date": str(end_date),
}
if selected_regions and len(selected_regions) < len(available_regions):
    filter_params["region"] = ",".join(selected_regions)

st.sidebar.caption(
    f"Showing {start_date} to {end_date}"
    + (f" · {len(selected_regions)} region(s)" if selected_regions != available_regions else " · all regions")
)

# ---------------- Top-level KPIs ----------------
region_df = fetch("/api/sales-by-region", params=filter_params)

if region_df.empty:
    st.warning("No data matches the current filters. Try widening the date range or regions.")
    st.stop()

total_sales = region_df["total_sales"].sum()
total_profit = region_df["total_profit"].sum()
profit_margin = (total_profit / total_sales * 100) if total_sales else 0

kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("Total Sales", f"${total_sales:,.0f}")
kpi2.metric("Total Profit", f"${total_profit:,.0f}")
kpi3.metric("Profit Margin", f"{profit_margin:.1f}%")

st.divider()

# ---------------- Monthly trend ----------------
st.subheader("Monthly Sales & Profit Trend")
trend_df = fetch("/api/monthly-trend", params=filter_params)
trend_df["month"] = pd.to_datetime(trend_df["month"])

fig_trend = px.line(
    trend_df, x="month", y=["total_sales", "total_profit"],
    labels={"value": "Amount ($)", "month": "Month", "variable": ""},
    color_discrete_map={"total_sales": "#1F3864", "total_profit": "#2FE0C0"},
)
st.plotly_chart(fig_trend, use_container_width=True)

col1, col2 = st.columns(2)

# ---------------- Sales by region ----------------
with col1:
    st.subheader("Sales & Profit by Region")
    fig_region = px.bar(
        region_df, x="Region", y=["total_sales", "total_profit"],
        barmode="group",
        labels={"value": "Amount ($)", "Region": "", "variable": ""},
        color_discrete_map={"total_sales": "#1F3864", "total_profit": "#2FE0C0"},
    )
    st.plotly_chart(fig_region, use_container_width=True)

# ---------------- Customer segments ----------------
with col2:
    st.subheader("Sales by Customer Segment")
    segment_df = fetch("/api/customer-segments", params=filter_params)
    fig_segment = px.pie(
        segment_df, names="segment", values="total_sales", hole=0.4,
    )
    st.plotly_chart(fig_segment, use_container_width=True)

st.divider()

# ---------------- Category breakdown ----------------
st.subheader("Category & Sub-Category Breakdown")
st.caption("Which product lines actually drive sales and profit — sized by sales, colored by profit.")
category_df = fetch("/api/category-breakdown", params=filter_params)

if not category_df.empty:
    fig_category = px.treemap(
        category_df, path=["category", "sub_category"], values="total_sales",
        color="total_profit", color_continuous_scale=["#d84c4c", "#e8e8e8", "#2fa84f"],
        color_continuous_midpoint=0,
    )
    st.plotly_chart(fig_category, use_container_width=True)

    losing_subcats = category_df[category_df["total_profit"] < 0]
    if not losing_subcats.empty:
        names = ", ".join(losing_subcats["sub_category"])
        st.warning(f"⚠️ Losing money overall in this filtered view: {names}")

st.divider()

# ---------------- Top products ----------------
st.subheader("Top Products")
sort_by = st.radio("Sort by", ["sales", "profit"], horizontal=True)
top_n = st.slider("Number of products", 5, 20, 10)

products_params = {**filter_params, "limit": top_n, "by": sort_by}
products_df = fetch("/api/top-products", params=products_params)

if not products_df.empty:
    fig_products = px.bar(
        products_df.sort_values(f"total_{sort_by}"),
        x=f"total_{sort_by}", y="product_name", orientation="h",
        color="category",
        labels={f"total_{sort_by}": f"Total {sort_by.title()} ($)", "product_name": ""},
    )
    fig_products.update_layout(height=400 + top_n * 15)
    st.plotly_chart(fig_products, use_container_width=True)

st.divider()

# ---------------- Profit vs. discount ----------------
st.subheader("Profit vs. Discount Level")
st.caption(
    "A genuinely useful business question: is discounting hurting profit? "
    "The data says yes, sharply, above 20%."
)
discount_df = fetch("/api/profit-vs-discount", params=filter_params)

if not discount_df.empty:
    fig_discount = px.bar(
        discount_df, x="discount_bucket", y="avg_profit_per_order",
        color="avg_profit_per_order",
        color_continuous_scale=["#d84c4c", "#e8e8e8", "#2fa84f"],
        color_continuous_midpoint=0,
        labels={"avg_profit_per_order": "Avg Profit per Order ($)", "discount_bucket": "Discount Level"},
    )
    st.plotly_chart(fig_discount, use_container_width=True)

    with st.expander("See underlying numbers"):
        st.dataframe(discount_df, use_container_width=True, hide_index=True)