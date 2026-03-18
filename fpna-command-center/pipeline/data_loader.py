"""
data_loader.py
--------------
Responsibility: Read raw CSVs, validate schema and data types,
raise clear errors if something is wrong before any processing begins.
"""

import pandas as pd
import os

# Absolute path so this works regardless of Streamlit launch directory
RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")

REQUIRED_COLS = {
    "revenue": [
        "month", "region", "segment",
        "beginning_arr", "new_arr", "expansion_arr",
        "churned_arr", "net_new_arr", "ending_arr",
        "mrr", "new_customers", "churned_customers", "ending_customers"
    ],
    "budget": [
        "month", "region", "segment",
        "budgeted_ending_arr", "budgeted_new_arr", "budgeted_mrr"
    ],
    "expenses": [
        "month", "total_opex",
        "salaries_engineering", "salaries_sales", "salaries_gna",
        "sales_marketing", "cloud_infrastructure", "office_admin", "software_tools"
    ]
}

NUMERIC_COLS = {
    "revenue":  ["beginning_arr","new_arr","expansion_arr","churned_arr",
                 "net_new_arr","ending_arr","mrr",
                 "new_customers","churned_customers","ending_customers"],
    "budget":   ["budgeted_ending_arr","budgeted_new_arr","budgeted_mrr"],
    "expenses": ["total_opex","salaries_engineering","salaries_sales",
                 "salaries_gna","sales_marketing","cloud_infrastructure",
                 "office_admin","software_tools"]
}


def load_csv(name: str) -> pd.DataFrame:
    """Load a single CSV by name ('revenue', 'budget', 'expenses')."""
    path = os.path.join(RAW_DIR, f"{name}.csv")

    if not os.path.exists(path):
        raise FileNotFoundError(f"[data_loader] Missing file: {path}")

    df = pd.read_csv(path)
    print(f"[data_loader] Loaded {name}.csv — {len(df)} rows, {len(df.columns)} cols")

    # ── Schema validation ──────────────────────────────────────────────────
    missing = set(REQUIRED_COLS[name]) - set(df.columns)
    if missing:
        raise ValueError(f"[data_loader] {name}.csv missing columns: {missing}")

    # ── Type coercion ──────────────────────────────────────────────────────
    df["month"] = pd.to_datetime(df["month"], format="%Y-%m")

    for col in NUMERIC_COLS[name]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Null check ─────────────────────────────────────────────────────────
    null_counts = df[NUMERIC_COLS[name]].isnull().sum()
    nulls = null_counts[null_counts > 0]
    if not nulls.empty:
        print(f"[data_loader] WARNING — nulls found in {name}.csv:\n{nulls}")

    return df


def load_all() -> dict[str, pd.DataFrame]:
    """Load and return all three DataFrames as a dict."""
    return {
        "revenue":  load_csv("revenue"),
        "budget":   load_csv("budget"),
        "expenses": load_csv("expenses"),
    }


if __name__ == "__main__":
    data = load_all()
    for name, df in data.items():
        print(f"\n── {name} preview ──")
        print(df.head(3).to_string())
