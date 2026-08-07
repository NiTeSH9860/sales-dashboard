"""
Sales Analytics Dashboard — Data Loading & Cleaning
------------------------------------------------------------
Loads the Sample Superstore retail dataset, fixes a real data-quality
issue, and loads the clean data into a SQLite database — this project
is built around genuine SQL queries, not just pandas, since that's the
specific skill gap it's meant to demonstrate.

Data quality issue found on inspection: the raw CSV has a second,
unrelated table (regional manager names) accidentally concatenated
after the real order data, with no separator — likely from someone
naively combining multiple sheets of the original Tableau Superstore
workbook (Orders, Returns, People) into one CSV. This corrupts columns
for those trailing rows (e.g. "Row ID" contains values like "Person").
Detected by checking where "Order Date" stops parsing as a real date,
not just by dropping nulls blindly.

Run: python load_data.py
Requires: pip install pandas
"""

import sqlite3

import pandas as pd

CSV_PATH = "data/superstore.csv"
DB_PATH = "data/superstore.db"


def load_and_clean() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    print(f"Raw rows loaded: {len(df)}")

    # Find where the real Orders table ends: valid rows have a parseable
    # Order Date. The corrupted trailing rows (a different table
    # entirely) have NaN here because they were never real order records.
    df["Order Date"] = pd.to_datetime(df["Order Date"], format="%m/%d/%Y", errors="coerce")
    valid_mask = df["Order Date"].notna()

    n_dropped = (~valid_mask).sum()
    print(f"Dropping {n_dropped} rows from a corrupted trailing table "
          f"(different data accidentally concatenated into this CSV)")

    df = df[valid_mask].copy()
    df["Ship Date"] = pd.to_datetime(df["Ship Date"], format="%m/%d/%Y", errors="coerce")

    print(f"Clean order rows: {len(df)}")
    return df


def load_into_sqlite(df: pd.DataFrame, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    df.to_sql("orders", conn, if_exists="replace", index=False)
    conn.close()
    print(f"Loaded {len(df)} rows into {db_path} (table: orders)")


def sanity_check_with_sql(db_path: str) -> None:
    """Confirm the SQLite load actually works with a real SQL query —
    not pandas — since that's the point of this project."""
    conn = sqlite3.connect(db_path)
    query = """
        SELECT Region, ROUND(SUM(Sales), 2) AS total_sales, ROUND(SUM(Profit), 2) AS total_profit
        FROM orders
        GROUP BY Region
        ORDER BY total_sales DESC
    """
    result = pd.read_sql(query, conn)
    conn.close()

    print("\nSanity check — total sales & profit by region (via SQL):")
    print(result.to_string(index=False))


if __name__ == "__main__":
    df = load_and_clean()
    load_into_sqlite(df, DB_PATH)
    sanity_check_with_sql(DB_PATH)
