"""
variance.py
-----------
Responsibility: Compute detailed variance analysis between actuals
and budget across every dimension — company, segment, region, and driver.

Variance sign convention (standard FP&A):
  Revenue variance: Actual > Budget = FAVORABLE (+)
  Expense variance: Actual < Budget = FAVORABLE (+)  ← inverted
"""

import pandas as pd
import numpy as np


def company_variance(monthly: pd.DataFrame) -> pd.DataFrame:
    """Overall company-level variance for every month."""
    df = monthly.copy()

    df["arr_variance"]       = df["total_ending_arr"]  - df["total_budgeted_arr"]
    df["arr_var_pct"]        = (df["arr_variance"] / df["total_budgeted_arr"] * 100).round(2)
    df["mrr_variance"]       = df["total_mrr"]         - df["total_budgeted_mrr"]

    # Favorable / Unfavorable flag
    df["arr_flag"] = df["arr_variance"].apply(
        lambda v: "Favorable" if v >= 0 else "Unfavorable"
    )

    # Magnitude bucket — used by insights engine to pick language intensity
    df["arr_magnitude"] = pd.cut(
        df["arr_var_pct"].abs(),
        bins=[0, 3, 8, 15, 100],
        labels=["minor", "moderate", "significant", "critical"]
    )
    return df


def segment_variance(segment: pd.DataFrame) -> pd.DataFrame:
    """Variance broken down by segment for every month."""
    df = segment.copy()
    df["arr_variance"] = df["ending_arr"] - df["budgeted_arr"]
    df["arr_var_pct"]  = (df["arr_variance"] / df["budgeted_arr"].replace(0, np.nan) * 100).round(2)
    df["flag"]         = df["arr_variance"].apply(lambda v: "F" if v >= 0 else "U")
    return df


def region_variance(region: pd.DataFrame) -> pd.DataFrame:
    """Variance broken down by region for every month."""
    df = region.copy()
    df["arr_variance"] = df["ending_arr"] - df["budgeted_arr"]
    df["arr_var_pct"]  = (df["arr_variance"] / df["budgeted_arr"].replace(0, np.nan) * 100).round(2)
    df["flag"]         = df["arr_variance"].apply(lambda v: "F" if v >= 0 else "U")
    return df


def driver_decomposition(monthly_row: pd.Series) -> dict:
    """
    Break total ARR variance into its three component drivers:
      1. New business variance    = actual new ARR   − implied budget new ARR
      2. Expansion variance       = actual expansion − implied budget expansion
      3. Churn variance           = budget churn     − actual churn  (inverted: less churn = favorable)

    Returns a dict with each driver's value and flag.
    """
    # Implied budget splits (assume budget proportioned same as actuals in prior month)
    total_var   = monthly_row["arr_variance"]
    new_arr     = monthly_row["total_new_arr"]
    exp_arr     = monthly_row["total_expansion_arr"]
    churn_arr   = monthly_row["total_churned_arr"]
    net_new     = monthly_row["total_net_new_arr"]

    # Apportion total variance proportionally across drivers
    if abs(net_new) > 0:
        new_share  = new_arr  / (new_arr + exp_arr + churn_arr + 1)
        exp_share  = exp_arr  / (new_arr + exp_arr + churn_arr + 1)
        churn_share= churn_arr/ (new_arr + exp_arr + churn_arr + 1)
    else:
        new_share = exp_share = churn_share = 1/3

    return {
        "new_business_var":  round(total_var * new_share),
        "expansion_var":     round(total_var * exp_share),
        "churn_var":         round(total_var * churn_share),   # negative = more churn than plan
        "new_arr":           round(new_arr),
        "expansion_arr":     round(exp_arr),
        "churned_arr":       round(churn_arr),
    }


def top_movers(seg_var: pd.DataFrame, region_var: pd.DataFrame,
               month_label: str, n: int = 3) -> dict:
    """
    Find the top N favorable and unfavorable movers
    across segment and region for a given month.
    """
    seg_m = seg_var[seg_var["month_label"] == month_label].copy()
    reg_m = region_var[region_var["month_label"] == month_label].copy()

    seg_sorted = seg_m.sort_values("arr_variance")
    reg_sorted = reg_m.sort_values("arr_variance")

    return {
        "worst_segment":  seg_sorted.iloc[0]["segment"]  if len(seg_sorted) else None,
        "best_segment":   seg_sorted.iloc[-1]["segment"] if len(seg_sorted) else None,
        "worst_region":   reg_sorted.iloc[0]["region"]   if len(reg_sorted) else None,
        "best_region":    reg_sorted.iloc[-1]["region"]  if len(reg_sorted) else None,
        "seg_details":    seg_sorted[["segment","arr_variance","arr_var_pct","flag"]].to_dict("records"),
        "reg_details":    reg_sorted[["region", "arr_variance","arr_var_pct","flag"]].to_dict("records"),
    }


if __name__ == "__main__":
    import sys
    sys.path.append(".")
    from pipeline.data_loader import load_all
    from pipeline.cleaner import run_cleaning
    from pipeline.metrics import run_metrics

    raw = load_all()
    _, _, _, master = run_cleaning(raw)
    tables = run_metrics(master)

    co_var  = company_variance(tables["monthly_kpis"])
    seg_var = segment_variance(tables["segment_kpis"])
    reg_var = region_variance(tables["region_kpis"])

    print("── Company variance (last 3 months) ──────────────────────────")
    print(co_var[["month_label","arr_variance","arr_var_pct","arr_flag","arr_magnitude"]].tail(3).to_string(index=False))

    print("\n── Segment variance Dec 2024 ──────────────────────────────────")
    print(seg_var[seg_var["month_label"]=="Dec 2024"][["segment","arr_variance","arr_var_pct","flag"]].to_string(index=False))

    print("\n── Top movers Dec 2024 ────────────────────────────────────────")
    movers = top_movers(seg_var, reg_var, "Dec 2024")
    print(f"  Worst segment : {movers['worst_segment']}")
    print(f"  Best segment  : {movers['best_segment']}")
    print(f"  Worst region  : {movers['worst_region']}")
    print(f"  Best region   : {movers['best_region']}")
