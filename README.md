# Sales Analytics Dashboard

A live retail sales analytics dashboard — real SQL queries behind a FastAPI backend, visualized through a Streamlit frontend with interactive filters. Built on the Sample Superstore dataset (~10,000 real US retail orders, 2015–2018).

## What it does

A business analyst can open the dashboard, filter by date range and region, and immediately see: total sales/profit/margin, monthly trends, regional and customer-segment performance, a category/sub-category profitability treemap, top products, and how discounting affects profit — all backed by real SQL queries, not pre-computed static charts.

## Architecture

```
CSV → load_data.py → SQLite (data/superstore.db)
                            ↓
                     api.py (FastAPI, real SQL queries)
                            ↓  HTTP
                     dashboard.py (Streamlit, no direct DB access)
```

The dashboard has no direct database access — it consumes the API over HTTP exactly like a real separated frontend/backend system would, not a monolithic script.

## Findings

**The raw dataset had a hidden data-quality problem.** The CSV contained 806 corrupted trailing rows — a completely different table (regional manager names) accidentally concatenated onto the real order data with no separator, likely from someone naively merging multiple sheets of the original Tableau workbook into one file. Detected by checking where `Order Date` stops parsing as a real date, not by blindly dropping rows with any null value — a more defensible, explainable cleaning decision.

**Discounts above 20% are actively losing the company money.** Bucketing orders by discount level shows average profit per order goes solidly negative above the 20% threshold (as low as -$134.62 per order at 21–40% discount), while 0% and modest discounts stay clearly profitable. A genuinely actionable finding, not just a chart for its own sake.

**Furniture → Tables and Bookcases lose money overall, despite real sales volume.** The category treemap surfaces this immediately: Tables shows -$17,725 total profit against $206,965 in sales. A pure sales-only view would never reveal this — profit-aware analysis was necessary.

**A real bug in how the dashboard handled a single-object API response.** `/api/date-range` returns one flat JSON object (`{"min_date": ..., "max_date": ...}`), unlike every other endpoint which returns a list of records. `pd.DataFrame()` can't build a table from a dict of scalar values without an explicit index, so the whole dashboard crashed on load the first time this endpoint was added. Fixed by making the shared `fetch()` helper detect and wrap single-dict responses automatically, rather than special-casing just this one endpoint.

## API endpoints

All support optional `start_date`, `end_date`, and `region` (comma-separated) query parameters for filtering, using parameterized SQL throughout — no raw string interpolation of user input, to avoid SQL injection.

- `GET /api/sales-by-region` — total sales/profit per region
- `GET /api/monthly-trend` — chronological monthly sales/profit
- `GET /api/top-products` — top N products, sortable by sales or profit
- `GET /api/customer-segments` — sales/profit by customer segment
- `GET /api/profit-vs-discount` — average profit per order at each discount bucket
- `GET /api/category-breakdown` — sales/profit by category and sub-category
- `GET /api/date-range` — min/max order date, for initializing the date picker
- `GET /api/regions` — distinct region names, for the filter dropdown

Interactive docs at `/docs` once the API is running.

## Setup

```bash
pip install fastapi uvicorn pandas streamlit plotly requests
```

## Run it (two terminals)

```bash
# Terminal 1 — API
uvicorn api:app --reload

# Terminal 2 — Dashboard
streamlit run dashboard.py
```

First, load the data:
```bash
python load_data.py
```

## Tech stack

Python · FastAPI · SQLite · Streamlit · Plotly · pandas