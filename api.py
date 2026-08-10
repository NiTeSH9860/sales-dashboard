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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = "data/superstore.db"

app = FastAPI(
    title="Sales Analytics API",
    description="Business-analyst SQL queries over Superstore retail data",
    version="1.0.0",
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


@app.get("/")
def root():
    return {"status": "ok", "message": "Sales Analytics API — see /docs for endpoints"}


@app.get("/api/sales-by-region")
def sales_by_region():
    """Total sales and profit per region, highest sales first."""
    query = """
        SELECT Region, ROUND(SUM(Sales), 2) AS total_sales, ROUND(SUM(Profit), 2) AS total_profit
        FROM orders
        GROUP BY Region
        ORDER BY total_sales DESC
    """
    return run_query(query)


@app.get("/api/monthly-trend")
def monthly_trend():
    """Total sales and profit by month, chronological — for a trend
    line chart. Uses SQLite's strftime to bucket by year-month."""
    query = """
        SELECT
            strftime('%Y-%m', "Order Date") AS month,
            ROUND(SUM(Sales), 2) AS total_sales,
            ROUND(SUM(Profit), 2) AS total_profit,
            COUNT(DISTINCT "Order ID") AS order_count
        FROM orders
        GROUP BY month
        ORDER BY month
    """
    return run_query(query)


@app.get("/api/top-products")
def top_products(limit: int = 10, by: str = "sales"):
    """Top N products by total sales or total profit.
    by='sales' or by='profit', validated against a fixed set of columns
    to avoid building a query from raw user input (SQL injection risk)."""
    allowed_sort = {"sales": "total_sales", "profit": "total_profit"}
    if by not in allowed_sort:
        raise HTTPException(status_code=400, detail="'by' must be 'sales' or 'profit'")
    sort_col = allowed_sort[by]

    query = f"""
        SELECT
            "Product Name" AS product_name,
            Category AS category,
            ROUND(SUM(Sales), 2) AS total_sales,
            ROUND(SUM(Profit), 2) AS total_profit,
            SUM(Quantity) AS total_quantity
        FROM orders
        GROUP BY "Product Name"
        ORDER BY {sort_col} DESC
        LIMIT ?
    """
    return run_query(query, (limit,))


@app.get("/api/customer-segments")
def customer_segments():
    """Sales, profit, and order count by customer segment
    (Consumer / Corporate / Home Office)."""
    query = """
        SELECT
            Segment AS segment,
            ROUND(SUM(Sales), 2) AS total_sales,
            ROUND(SUM(Profit), 2) AS total_profit,
            COUNT(DISTINCT "Order ID") AS order_count,
            ROUND(AVG(Sales), 2) AS avg_order_value
        FROM orders
        GROUP BY Segment
        ORDER BY total_sales DESC
    """
    return run_query(query)


@app.get("/api/profit-vs-discount")
def profit_vs_discount():
    """Average profit margin at each discount level — a genuinely
    useful business question: is discounting actually hurting profit?
    Bucket discount into ranges since raw values are too granular."""
    query = """
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
        GROUP BY discount_bucket
        ORDER BY MIN(Discount)
    """
    return run_query(query)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
