import pandas as pd
import numpy as np
import os

np.random.seed(42)
os.makedirs("data/raw", exist_ok=True)
os.makedirs("data/processed", exist_ok=True)

# ── CONFIG ──────────────────────────────────────────────────────────────────
MONTHS = pd.date_range("2024-01-01", periods=12, freq="MS")
REGIONS = ["North", "South", "West"]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]

# Annual contract values (INR) per segment
ACV = {"Enterprise": 1_800_000, "Mid-Market": 540_000, "SMB": 120_000}

# Starting customer counts per region×segment
START_CUSTOMERS = {
    ("North",  "Enterprise"): 5,  ("North",  "Mid-Market"): 12, ("North",  "SMB"): 30,
    ("South",  "Enterprise"): 4,  ("South",  "Mid-Market"): 10, ("South",  "SMB"): 25,
    ("West",   "Enterprise"): 6,  ("West",   "Mid-Market"): 14, ("West",   "SMB"): 35,
}

# Monthly churn rates per segment
CHURN_RATE = {"Enterprise": 0.008, "Mid-Market": 0.018, "SMB": 0.030}

# Monthly new customer additions (base) per region×segment
NEW_BASE = {
    ("North",  "Enterprise"): 0.4, ("North",  "Mid-Market"): 1.0, ("North",  "SMB"): 3.0,
    ("South",  "Enterprise"): 0.3, ("South",  "Mid-Market"): 0.8, ("South",  "SMB"): 2.5,
    ("West",   "Enterprise"): 0.5, ("West",   "Mid-Market"): 1.2, ("West",   "SMB"): 3.5,
}

# Expansion ARR multiplier per month (seat upgrades, upsells)
EXPANSION_RATE = {"Enterprise": 0.015, "Mid-Market": 0.010, "SMB": 0.005}

# Seasonality index by month (Jan=1 … Dec=12)
# Q1 slow, Q2 ramp, Q3 flat, Q4 strong (Indian enterprise buying patterns)
SEASONALITY = [0.80, 0.85, 0.95, 1.00, 1.05, 1.10, 1.00, 1.00, 1.05, 1.10, 1.15, 1.25]

# Mid-year growth event: West Enterprise expansion in Jul-Aug
PROMO_BOOST = {(6, "West", "Enterprise"): 2, (7, "West", "Enterprise"): 1}

# ── REVENUE GENERATION ──────────────────────────────────────────────────────
records = []
customers = {k: v for k, v in START_CUSTOMERS.items()}

for m_idx, month in enumerate(MONTHS):
    season = SEASONALITY[m_idx]
    for region in REGIONS:
        for segment in SEGMENTS:
            key = (region, segment)
            curr_customers = customers[key]

            # Churn
            churned = max(0, int(np.random.poisson(curr_customers * CHURN_RATE[segment])))
            churned = min(churned, curr_customers)

            # New customers (seasonality + promo boost)
            boost = PROMO_BOOST.get((m_idx, region, segment), 0)
            new_raw = NEW_BASE[key] * season + boost
            new_custs = int(np.random.poisson(max(new_raw, 0.1)))

            # Expansion ARR on existing base
            base_arr = curr_customers * ACV[segment]
            expansion_arr = base_arr * EXPANSION_RATE[segment] * season
            expansion_arr = round(expansion_arr + np.random.normal(0, expansion_arr * 0.05))

            new_arr      = new_custs * ACV[segment]
            churned_arr  = churned   * ACV[segment]
            net_new_arr  = new_arr + expansion_arr - churned_arr
            ending_arr   = base_arr + net_new_arr
            mrr          = ending_arr / 12

            records.append({
                "month":          month.strftime("%Y-%m"),
                "region":         region,
                "segment":        segment,
                "beginning_arr":  round(base_arr),
                "new_customers":  new_custs,
                "churned_customers": churned,
                "new_arr":        round(new_arr),
                "expansion_arr":  round(expansion_arr),
                "churned_arr":    round(churned_arr),
                "net_new_arr":    round(net_new_arr),
                "ending_arr":     round(ending_arr),
                "mrr":            round(mrr),
                "ending_customers": max(0, curr_customers + new_custs - churned),
            })

            customers[key] = max(0, curr_customers + new_custs - churned)

revenue_df = pd.DataFrame(records)
revenue_df.to_csv("data/raw/revenue.csv", index=False)
print(f"✓ revenue.csv — {len(revenue_df)} rows")

# ── BUDGET GENERATION ───────────────────────────────────────────────────────
# Budget is set at Jan with optimistic projections (+8–15% vs actuals)
budget_records = []
for m_idx, month in enumerate(MONTHS):
    season = SEASONALITY[m_idx]
    for region in REGIONS:
        for segment in SEGMENTS:
            # Budget is slightly more optimistic than actuals
            budget_multiplier = 1.08 + np.random.uniform(0, 0.07)
            actual_row = revenue_df[
                (revenue_df.month == month.strftime("%Y-%m")) &
                (revenue_df.region == region) &
                (revenue_df.segment == segment)
            ].iloc[0]

            budget_records.append({
                "month":              month.strftime("%Y-%m"),
                "region":             region,
                "segment":            segment,
                "budgeted_ending_arr": round(actual_row["ending_arr"] * budget_multiplier),
                "budgeted_new_arr":   round(actual_row["new_arr"]     * budget_multiplier),
                "budgeted_mrr":       round(actual_row["mrr"]         * budget_multiplier),
            })

budget_df = pd.DataFrame(budget_records)
budget_df.to_csv("data/raw/budget.csv", index=False)
print(f"✓ budget.csv — {len(budget_df)} rows")

# ── EXPENSES GENERATION ─────────────────────────────────────────────────────
# Monthly opex for a ~₹4–6Cr ARR SaaS startup (INR)
EXPENSE_BASE = {
    "salaries_engineering":  2_800_000,
    "salaries_sales":        1_600_000,
    "salaries_gna":            800_000,
    "sales_marketing":       1_200_000,
    "cloud_infrastructure":    350_000,
    "office_admin":            200_000,
    "software_tools":          120_000,
}

EXPENSE_GROWTH = {   # monthly growth rate
    "salaries_engineering":  0.010,
    "salaries_sales":        0.012,
    "salaries_gna":          0.008,
    "sales_marketing":       0.015,
    "cloud_infrastructure":  0.008,
    "office_admin":          0.005,
    "software_tools":        0.005,
}

# Q4 hiring push in engineering & sales
HIRING_BUMP = {
    "salaries_engineering": {9: 300_000, 10: 300_000},
    "salaries_sales":       {9: 200_000, 10: 200_000},
}

expense_records = []
for m_idx, month in enumerate(MONTHS):
    row = {"month": month.strftime("%Y-%m")}
    total = 0
    for cat, base in EXPENSE_BASE.items():
        growth = (1 + EXPENSE_GROWTH[cat]) ** m_idx
        bump   = HIRING_BUMP.get(cat, {}).get(m_idx, 0)
        noise  = np.random.normal(1.0, 0.02)
        val    = round((base * growth + bump) * noise)
        row[cat] = val
        total += val
    row["total_opex"] = total
    expense_records.append(row)

expense_df = pd.DataFrame(expense_records)
expense_df.to_csv("data/raw/expenses.csv", index=False)
print(f"✓ expenses.csv — {len(expense_df)} rows")

# ── SUMMARY PREVIEW ─────────────────────────────────────────────────────────
print("\n── Revenue snapshot (₹) ──────────────────────────────────")
monthly = revenue_df.groupby("month").agg(
    total_mrr=("mrr","sum"),
    total_ending_arr=("ending_arr","sum"),
    total_net_new_arr=("net_new_arr","sum"),
).reset_index()
monthly["total_mrr_cr"]        = (monthly.total_mrr        / 1e7).round(2)
monthly["total_ending_arr_cr"] = (monthly.total_ending_arr / 1e7).round(2)
monthly["net_new_arr_L"]       = (monthly.total_net_new_arr / 1e5).round(1)
print(monthly[["month","total_mrr_cr","total_ending_arr_cr","net_new_arr_L"]].to_string(index=False))

print("\n── Expense snapshot (₹ Lakhs) ────────────────────────────")
expense_df["total_opex_L"] = (expense_df.total_opex / 1e5).round(1)
print(expense_df[["month","total_opex_L"]].to_string(index=False))

print("\n── Budget vs Actual sample (Dec 2024) ────────────────────")
dec_actual = revenue_df[revenue_df.month=="2024-12"].groupby("segment")["ending_arr"].sum().reset_index()
dec_budget = budget_df[budget_df.month=="2024-12"].groupby("segment")["budgeted_ending_arr"].sum().reset_index()
dec = dec_actual.merge(dec_budget, on="segment")
dec["variance"] = dec["ending_arr"] - dec["budgeted_ending_arr"]
dec["var_pct"]  = (dec["variance"] / dec["budgeted_ending_arr"] * 100).round(1)
print(dec.to_string(index=False))
