"""
Sales Analytics Dashboard — FastAPI Backend
--------------------------------------------------
REST API exposing business-analyst SQL queries over the cleaned
Superstore SQLite database. The dashboard (built separately) consumes
these endpoints over HTTP rather than querying the database directly —
a more realistic separation between data/business logic and
presentation than a monolithic Streamlit script.

Run: uvicorn api:app --reload
Docs: http://localhost:8000/docs (FastAPI's automatic interactive docs)
Requires: pip install fastapi uvicorn
"""

import sqlite3
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = "data/superstore.db"

app = FastAPI(
    title="Sales Analytics API",
    description="Business-analyst SQL queries over Superstore retail data",
    version="1.1.0",
)

# Allow the Streamlit dashboard (running on a different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def run_query(query: str, params: tuple = ()) -> list[dict]:
    with get_db() as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def build_filters(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    region: Optional[str] = None,
) -> tuple[str, list]:
    """Builds a WHERE clause fragment (starting with 'AND ...', or empty
    string if no filters) plus its parameters, using parameterized
    placeholders throughout — never string-interpolating raw filter
    values into SQL, to avoid injection."""
    conditions = []
    params: list = []

    if start_date:
        conditions.append('"Order Date" >= ?')
        params.append(start_date)
    if end_date:
        conditions.append('"Order Date" <= ?')
        params.append(end_date)
    if region:
        # region can be comma-separated for multi-select filtering
        regions = [r.strip() for r in region.split(",") if r.strip()]
        if regions:
            placeholders = ",".join("?" for _ in regions)
            conditions.append(f"Region IN ({placeholders})")
            params.extend(regions)

    if not conditions:
        return "", []
    return "AND " + " AND ".join(conditions), params


@app.get("/")
def root():
    return {"status": "ok", "message": "Sales Analytics API — see /docs for endpoints"}


@app.get("/api/date-range")
def date_range():
    """Min and max order date in the dataset — lets the dashboard
    initialize a date picker with sensible real bounds."""
    query = """
        SELECT MIN("Order Date") AS min_date, MAX("Order Date") AS max_date
        FROM orders
    """
    return run_query(query)[0]


@app.get("/api/regions")
def regions():
    """Distinct region names — for populating a filter dropdown."""
    query = "SELECT DISTINCT Region FROM orders ORDER BY Region"
    return [row["Region"] for row in run_query(query)]


@app.get("/api/sales-by-region")
def sales_by_region(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    region: Optional[str] = None,
):
    """Total sales and profit per region, highest sales first."""
    where_sql, where_params = build_filters(start_date, end_date, region)
    query = f"""
        SELECT Region, ROUND(SUM(Sales), 2) AS total_sales, ROUND(SUM(Profit), 2) AS total_profit
        FROM orders
        WHERE 1=1 {where_sql}
        GROUP BY Region
        ORDER BY total_sales DESC
    """
    return run_query(query, tuple(where_params))


@app.get("/api/monthly-trend")
def monthly_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    region: Optional[str] = None,
):
    """Total sales and profit by month, chronological — for a trend
    line chart. Uses SQLite's strftime to bucket by year-month."""
    where_sql, where_params = build_filters(start_date, end_date, region)
    query = f"""
        SELECT
            strftime('%Y-%m', "Order Date") AS month,
            ROUND(SUM(Sales), 2) AS total_sales,
            ROUND(SUM(Profit), 2) AS total_profit,
            COUNT(DISTINCT "Order ID") AS order_count
        FROM orders
        WHERE 1=1 {where_sql}
        GROUP BY month
        ORDER BY month
    """
    return run_query(query, tuple(where_params))


@app.get("/api/top-products")
def top_products(
    limit: int = 10,
    by: str = "sales",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    region: Optional[str] = None,
):
    """Top N products by total sales or total profit.
    by='sales' or by='profit', validated against a fixed set of columns
    to avoid building a query from raw user input (SQL injection risk)."""
    allowed_sort = {"sales": "total_sales", "profit": "total_profit"}
    if by not in allowed_sort:
        raise HTTPException(status_code=400, detail="'by' must be 'sales' or 'profit'")
    sort_col = allowed_sort[by]

    where_sql, where_params = build_filters(start_date, end_date, region)
    query = f"""
        SELECT
            "Product Name" AS product_name,
            Category AS category,
            ROUND(SUM(Sales), 2) AS total_sales,
            ROUND(SUM(Profit), 2) AS total_profit,
            SUM(Quantity) AS total_quantity
        FROM orders
        WHERE 1=1 {where_sql}
        GROUP BY "Product Name"
        ORDER BY {sort_col} DESC
        LIMIT ?
    """
    return run_query(query, tuple(where_params) + (limit,))


@app.get("/api/customer-segments")
def customer_segments(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    region: Optional[str] = None,
):
    """Sales, profit, and order count by customer segment
    (Consumer / Corporate / Home Office)."""
    where_sql, where_params = build_filters(start_date, end_date, region)
    query = f"""
        SELECT
            Segment AS segment,
            ROUND(SUM(Sales), 2) AS total_sales,
            ROUND(SUM(Profit), 2) AS total_profit,
            COUNT(DISTINCT "Order ID") AS order_count,
            ROUND(AVG(Sales), 2) AS avg_order_value
        FROM orders
        WHERE 1=1 {where_sql}
        GROUP BY Segment
        ORDER BY total_sales DESC
    """
    return run_query(query, tuple(where_params))


@app.get("/api/profit-vs-discount")
def profit_vs_discount(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    region: Optional[str] = None,
):
    """Average profit margin at each discount level — a genuinely
    useful business question: is discounting actually hurting profit?
    Bucket discount into ranges since raw values are too granular."""
    where_sql, where_params = build_filters(start_date, end_date, region)
    query = f"""
        SELECT
            CASE
                WHEN Discount = 0 THEN '0% (no discount)'
                WHEN Discount <= 0.2 THEN '1-20%'
                WHEN Discount <= 0.4 THEN '21-40%'
                WHEN Discount <= 0.6 THEN '41-60%'
                ELSE '60%+'
            END AS discount_bucket,
            COUNT(*) AS order_count,
            ROUND(SUM(Sales), 2) AS total_sales,
            ROUND(SUM(Profit), 2) AS total_profit,
            ROUND(AVG(Profit), 2) AS avg_profit_per_order
        FROM orders
        WHERE 1=1 {where_sql}
        GROUP BY discount_bucket
        ORDER BY MIN(Discount)
    """
    return run_query(query, tuple(where_params))


@app.get("/api/category-breakdown")
def category_breakdown(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    region: Optional[str] = None,
):
    """Sales and profit by Category and Sub-Category — a drill-down
    view for 'which product lines actually drive the business'."""
    where_sql, where_params = build_filters(start_date, end_date, region)
    query = f"""
        SELECT
            Category AS category,
            "Sub-Category" AS sub_category,
            ROUND(SUM(Sales), 2) AS total_sales,
            ROUND(SUM(Profit), 2) AS total_profit,
            SUM(Quantity) AS total_quantity
        FROM orders
        WHERE 1=1 {where_sql}
        GROUP BY Category, "Sub-Category"
        ORDER BY category, total_sales DESC
    """
    return run_query(query, tuple(where_params))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# ---------------------------------------------------------------
# Next steps:
#   - Streamlit dashboard consuming these endpoints over HTTP
# ---------------------------------------------------------------