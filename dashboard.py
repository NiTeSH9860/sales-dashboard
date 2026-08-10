"""
Sales Analytics Dashboard — Streamlit Frontend
------------------------------------------------------
Consumes the FastAPI backend (api.py) over HTTP — this dashboard has
NO direct database access. All data comes through the REST API, the
same way a real separated frontend/backend architecture would work.

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
    switching between chart views doesn't re-hit the API every time."""
    resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=10)
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


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

# ---------------- Top-level KPIs ----------------
region_df = fetch("/api/sales-by-region")
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
trend_df = fetch("/api/monthly-trend")
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
    segment_df = fetch("/api/customer-segments")
    fig_segment = px.pie(
        segment_df, names="segment", values="total_sales", hole=0.4,
    )
    st.plotly_chart(fig_segment, use_container_width=True)

st.divider()

# ---------------- Top products ----------------
st.subheader("Top Products")
sort_by = st.radio("Sort by", ["sales", "profit"], horizontal=True)
top_n = st.slider("Number of products", 5, 20, 10)

products_df = fetch("/api/top-products", params={"limit": top_n, "by": sort_by})
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
discount_df = fetch("/api/profit-vs-discount")

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