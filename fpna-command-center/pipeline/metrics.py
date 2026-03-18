"""
metrics.py
----------
Responsibility: Compute every SaaS KPI from the master DataFrame
and persist all tables to SQLite for the dashboard to query.

KPIs computed:
  - MRR / ARR (already in data, validated here)
  - Net New ARR (new + expansion - churn)
  - NRR (Net Revenue Retention) — per segment per month
  - Gross Churn Rate
  - Burn Multiple
  - CAC (Customer Acquisition Cost)
  - LTV (Lifetime Value)
  - LTV:CAC Ratio
  - Runway (months of cash left)
"""

import pandas as pd
import numpy as np
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "processed", "fpna.db")

# Assumed cash balance at Jan 2024 start (₹)
STARTING_CASH = 15_000_000   # ₹1.5 Crore


def compute_monthly_summary(master: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate master (per region×segment) to monthly company-wide totals.
    This is the primary table for KPI cards and trend charts.
    """
    grp = master.groupby("month").agg(
        month_label       = ("month_label",          "first"),
        total_mrr         = ("mrr",                  "sum"),
        total_ending_arr  = ("ending_arr",            "sum"),
        total_beginning_arr = ("beginning_arr",       "sum"),
        total_new_arr     = ("new_arr",               "sum"),
        total_expansion_arr = ("expansion_arr",       "sum"),
        total_churned_arr = ("churned_arr",            "sum"),
        total_net_new_arr = ("net_new_arr",            "sum"),
        total_budgeted_arr = ("budgeted_ending_arr",  "sum"),
        total_budgeted_mrr = ("budgeted_mrr",         "sum"),
        total_opex        = ("total_opex",            "sum"),   # already company-wide after /9 × 9
        total_new_customers    = ("new_customers",    "sum"),
        total_churned_customers= ("churned_customers","sum"),
        total_ending_customers = ("ending_customers", "sum"),
        people_cost       = ("people_cost",           "sum"),
        gtm_cost          = ("gtm_cost",              "sum"),
        infra_cost        = ("infrastructure_cost",   "sum"),
    ).reset_index()

    # ── NRR (Net Revenue Retention) ───────────────────────────────────────
    # NRR = (Beginning ARR + Expansion - Churn) / Beginning ARR
    grp["nrr"] = (
        (grp["total_beginning_arr"] + grp["total_expansion_arr"] - grp["total_churned_arr"])
        / grp["total_beginning_arr"]
    ).round(4)

    # ── Gross Churn Rate ──────────────────────────────────────────────────
    # Churned ARR / Beginning ARR
    grp["gross_churn_rate"] = (
        grp["total_churned_arr"] / grp["total_beginning_arr"]
    ).round(4)

    # ── Burn Multiple ─────────────────────────────────────────────────────
    # Net Burn / Net New ARR  (lower = more efficient)
    # Net Burn = Total Opex (we assume revenue not yet cash-collected for simplicity)
    grp["burn_multiple"] = (
        grp["total_opex"] / grp["total_net_new_arr"].replace(0, np.nan)
    ).round(2)

    # ── CAC (Customer Acquisition Cost) ──────────────────────────────────
    # Sales & Marketing spend / New Customers acquired
    # GTM cost = sales_marketing (already summed)
    grp["cac"] = (
        grp["gtm_cost"] / grp["total_new_customers"].replace(0, np.nan)
    ).round(0)

    # ── ARPU (Average Revenue Per User) ──────────────────────────────────
    grp["arpu"] = (
        grp["total_mrr"] / grp["total_ending_customers"].replace(0, np.nan)
    ).round(0)

    # ── LTV (Lifetime Value) ──────────────────────────────────────────────
    # LTV = ARPU / Monthly Churn Rate
    # Monthly customer churn rate
    grp["customer_churn_rate"] = (
        grp["total_churned_customers"] / grp["total_ending_customers"].replace(0, np.nan)
    ).round(4)
    grp["ltv"] = (
        grp["arpu"] / grp["customer_churn_rate"].replace(0, np.nan)
    ).round(0)

    # ── LTV:CAC Ratio ─────────────────────────────────────────────────────
    grp["ltv_cac"] = (
        grp["ltv"] / grp["cac"].replace(0, np.nan)
    ).round(2)

    # ── Cumulative Cash Burn & Runway ─────────────────────────────────────
    grp = grp.sort_values("month").reset_index(drop=True)
    grp["cumulative_burn"]  = grp["total_opex"].cumsum()
    grp["cash_remaining"]   = STARTING_CASH - grp["cumulative_burn"]

    # Runway = cash remaining / avg monthly burn (last 3 months)
    grp["avg_monthly_burn"] = grp["total_opex"].rolling(3, min_periods=1).mean()
    grp["runway_months"]    = (
        grp["cash_remaining"] / grp["avg_monthly_burn"]
    ).clip(lower=0).round(1)

    # ── ARR Variance ──────────────────────────────────────────────────────
    grp["arr_variance"]     = grp["total_ending_arr"]  - grp["total_budgeted_arr"]
    grp["arr_variance_pct"] = (
        grp["arr_variance"] / grp["total_budgeted_arr"].replace(0, np.nan) * 100
    ).round(2)
    grp["mrr_variance"]     = grp["total_mrr"] - grp["total_budgeted_mrr"]

    return grp


def compute_segment_summary(master: pd.DataFrame) -> pd.DataFrame:
    """Monthly KPIs broken down by segment (for segment drill-down charts)."""
    grp = master.groupby(["month","segment"]).agg(
        month_label        = ("month_label",        "first"),
        ending_arr         = ("ending_arr",          "sum"),
        beginning_arr      = ("beginning_arr",       "sum"),
        new_arr            = ("new_arr",             "sum"),
        expansion_arr      = ("expansion_arr",       "sum"),
        churned_arr        = ("churned_arr",         "sum"),
        net_new_arr        = ("net_new_arr",         "sum"),
        budgeted_arr       = ("budgeted_ending_arr", "sum"),
        new_customers      = ("new_customers",       "sum"),
        churned_customers  = ("churned_customers",   "sum"),
        ending_customers   = ("ending_customers",    "sum"),
        mrr                = ("mrr",                 "sum"),
    ).reset_index()

    grp["nrr"] = (
        (grp["beginning_arr"] + grp["expansion_arr"] - grp["churned_arr"])
        / grp["beginning_arr"].replace(0, np.nan)
    ).round(4)
    grp["arr_variance"] = grp["ending_arr"] - grp["budgeted_arr"]
    grp["arr_var_pct"]  = (grp["arr_variance"] / grp["budgeted_arr"].replace(0, np.nan) * 100).round(2)

    return grp


def compute_region_summary(master: pd.DataFrame) -> pd.DataFrame:
    """Monthly KPIs broken down by region."""
    grp = master.groupby(["month","region"]).agg(
        month_label   = ("month_label",        "first"),
        ending_arr    = ("ending_arr",          "sum"),
        beginning_arr = ("beginning_arr",       "sum"),
        new_arr       = ("new_arr",             "sum"),
        expansion_arr = ("expansion_arr",       "sum"),
        churned_arr   = ("churned_arr",         "sum"),
        net_new_arr   = ("net_new_arr",         "sum"),
        budgeted_arr  = ("budgeted_ending_arr", "sum"),
        mrr           = ("mrr",                 "sum"),
    ).reset_index()

    grp["arr_variance"] = grp["ending_arr"] - grp["budgeted_arr"]
    grp["arr_var_pct"]  = (grp["arr_variance"] / grp["budgeted_arr"].replace(0, np.nan) * 100).round(2)

    return grp


def compute_waterfall_data(monthly: pd.DataFrame, selected_month: str) -> pd.DataFrame:
    """
    Build waterfall (bridge) chart data for a given month.
    Returns ordered steps from Budget ARR → Actual ARR.

    Steps: Budget → New ARR → Expansion ARR → Churn → Actual
    """
    row = monthly[monthly["month_label"] == selected_month].iloc[0]

    steps = [
        {"label": "Budget ARR",    "value": row["total_budgeted_arr"],  "type": "base"},
        {"label": "New ARR",       "value": row["total_new_arr"],        "type": "positive"},
        {"label": "Expansion ARR", "value": row["total_expansion_arr"],  "type": "positive"},
        {"label": "Churn",         "value": -row["total_churned_arr"],   "type": "negative"},
        {"label": "Actual ARR",    "value": row["total_ending_arr"],     "type": "total"},
    ]
    return pd.DataFrame(steps)


def save_to_sqlite(tables: dict[str, pd.DataFrame]):
    """Persist all computed tables to SQLite."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    for table_name, df in tables.items():
        # Convert datetime to string for SQLite
        df_save = df.copy()
        for col in df_save.select_dtypes(include=["datetime64[ns]","datetime64[ns, UTC]"]).columns:
            df_save[col] = df_save[col].astype(str)
        # Convert categorical to string
        for col in df_save.select_dtypes(include="category").columns:
            df_save[col] = df_save[col].astype(str)

        df_save.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"[metrics] Saved '{table_name}' → SQLite ({len(df_save)} rows)")

    conn.close()
    print(f"[metrics] Database written to {DB_PATH}")


def run_metrics(master: pd.DataFrame) -> dict:
    """Entry point: compute all KPI tables and save to SQLite."""
    monthly  = compute_monthly_summary(master)
    segment  = compute_segment_summary(master)
    region   = compute_region_summary(master)
    waterfall_dec = compute_waterfall_data(monthly, "Dec 2024")

    tables = {
        "monthly_kpis":    monthly,
        "segment_kpis":    segment,
        "region_kpis":     region,
        "waterfall_dec":   waterfall_dec,
        "master":          master,
    }
    save_to_sqlite(tables)
    return tables


if __name__ == "__main__":
    import sys
    sys.path.append(".")
    from pipeline.data_loader import load_all
    from pipeline.cleaner import run_cleaning

    raw = load_all()
    _, _, _, master = run_cleaning(raw)
    tables = run_metrics(master)

    print("\n── Monthly KPI snapshot ──────────────────────────────────────")
    cols = ["month_label","total_mrr","total_ending_arr","nrr",
            "burn_multiple","cac","ltv_cac","runway_months"]
    print(tables["monthly_kpis"][cols].to_string(index=False))

    print("\n── Dec 2024 Waterfall ────────────────────────────────────────")
    print(tables["waterfall_dec"].to_string(index=False))
