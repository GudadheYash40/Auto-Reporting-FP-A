"""
cleaner.py
----------
Responsibility: Normalize column names, fill gaps, add derived time
columns, and merge all three DataFrames into one master DataFrame
ready for metric calculation.
"""

import pandas as pd
import numpy as np


def clean_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize revenue data and add time dimension columns."""
    df = df.copy()

    # Fill any missing numeric values with 0 (conservative: missing = no activity)
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].fillna(0)

    # Enforce non-negative ARR values
    arr_cols = ["beginning_arr","new_arr","expansion_arr",
                "churned_arr","net_new_arr","ending_arr","mrr"]
    for col in arr_cols:
        df[col] = df[col].clip(lower=0)

    # Add time dimension helpers (useful for groupbys in dashboard)
    df["year"]    = df["month"].dt.year
    df["month_num"] = df["month"].dt.month
    df["quarter"] = df["month"].dt.quarter.map({1:"Q1",2:"Q2",3:"Q3",4:"Q4"})
    df["month_label"] = df["month"].dt.strftime("%b %Y")   # e.g. "Jan 2024"

    # Segment ordering (for consistent chart ordering)
    seg_order = pd.CategoricalDtype(["Enterprise","Mid-Market","SMB"], ordered=True)
    df["segment"] = df["segment"].astype(seg_order)

    return df


def clean_budget(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize budget data."""
    df = df.copy()
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].fillna(0).clip(lower=0)
    df["month_label"] = df["month"].dt.strftime("%b %Y")
    return df


def clean_expenses(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize expense data and add category groupings."""
    df = df.copy()
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].fillna(0).clip(lower=0)

    # Group expenses into three buckets (useful for pie/donut chart)
    df["people_cost"]     = df["salaries_engineering"] + df["salaries_sales"] + df["salaries_gna"]
    df["gtm_cost"]        = df["sales_marketing"]
    df["infrastructure_cost"] = df["cloud_infrastructure"] + df["office_admin"] + df["software_tools"]

    df["month_label"] = df["month"].dt.strftime("%b %Y")
    return df


def build_master(revenue: pd.DataFrame,
                 budget:  pd.DataFrame,
                 expenses: pd.DataFrame) -> pd.DataFrame:
    """
    Merge revenue + budget on (month, region, segment).
    Join expenses on month (expenses are company-wide, not per-region).
    Result: one row per (month × region × segment) with all columns.
    """
    # Revenue-level merge with budget
    master = revenue.merge(
        budget[["month","region","segment",
                "budgeted_ending_arr","budgeted_new_arr","budgeted_mrr"]],
        on=["month","region","segment"],
        how="left"
    )

    # Apportion company-wide expenses equally across 9 region×segment combos
    # (3 regions × 3 segments = 9 combos per month)
    COMBOS = 9
    expense_slim = expenses[["month","total_opex",
                              "people_cost","gtm_cost","infrastructure_cost"]].copy()
    for col in ["total_opex","people_cost","gtm_cost","infrastructure_cost"]:
        expense_slim[col] = expense_slim[col] / COMBOS

    master = master.merge(expense_slim, on="month", how="left")

    # Sort for clean display
    master = master.sort_values(["month","region","segment"]).reset_index(drop=True)

    print(f"[cleaner] Master DataFrame — {len(master)} rows × {len(master.columns)} cols")
    return master


def run_cleaning(raw: dict) -> tuple:
    """Entry point: takes raw dict from data_loader, returns cleaned DataFrames."""
    rev  = clean_revenue(raw["revenue"])
    bud  = clean_budget(raw["budget"])
    exp  = clean_expenses(raw["expenses"])
    master = build_master(rev, bud, exp)
    return rev, bud, exp, master


if __name__ == "__main__":
    import sys
    sys.path.append(".")
    from pipeline.data_loader import load_all

    raw = load_all()
    rev, bud, exp, master = run_cleaning(raw)
    print("\n── Master sample ──")
    print(master[["month_label","region","segment","ending_arr",
                  "budgeted_ending_arr","total_opex"]].head(9).to_string(index=False))
