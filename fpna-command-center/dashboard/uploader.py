"""
uploader.py
-----------
Universal FP&A analyser — accepts any company's CSV files,
validates and maps columns, runs the full pipeline, and returns
an InsightReport. Embedded as Page 0 in the Streamlit app.

Supported input modes:
  A) Zenvora format  — use the pre-built synthetic data as-is
  B) Custom upload   — user uploads their own revenue + budget + expenses CSVs
  C) Template mode   — user downloads blank templates, fills them, re-uploads

Column mapping handles the most common naming variations so users
don't need to rename their spreadsheets.
"""

import pandas as pd
import numpy as np
import streamlit as st
import io
import os
import sys

_HERE         = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
for _p in [_PROJECT_ROOT, _HERE]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── COLUMN ALIASES ─────────────────────────────────────────────────────────
# Maps common real-world column names → our internal standard names.
# Extend this dict as you encounter new naming conventions.

REVENUE_ALIASES = {
    # month
    "month": ["month", "date", "period", "reporting_month", "report_month",
              "month_year", "year_month", "ym"],
    # region
    "region": ["region", "geography", "geo", "area", "territory",
                "market", "country", "location"],
    # segment
    "segment": ["segment", "tier", "customer_segment", "customer_tier",
                 "plan", "product_tier", "type"],
    # arr figures
    "beginning_arr": ["beginning_arr", "start_arr", "opening_arr",
                       "arr_start", "arr_open", "arr_begin"],
    "new_arr":        ["new_arr", "new_business_arr", "new_logo_arr",
                       "new_revenue", "new_sales"],
    "expansion_arr":  ["expansion_arr", "expansion", "upsell_arr",
                       "upsell", "expansion_revenue", "seat_expansion"],
    "churned_arr":    ["churned_arr", "churn_arr", "lost_arr",
                       "churn", "attrition_arr", "cancelled_arr"],
    "net_new_arr":    ["net_new_arr", "net_arr", "net_arr_change",
                       "arr_change", "delta_arr"],
    "ending_arr":     ["ending_arr", "end_arr", "closing_arr",
                       "arr_end", "arr_close", "arr_total", "total_arr"],
    "mrr":            ["mrr", "monthly_recurring_revenue", "monthly_revenue",
                       "revenue", "monthly_arr"],
    # customer counts
    "new_customers":      ["new_customers", "new_logos", "new_accounts",
                            "customers_added", "new_clients"],
    "churned_customers":  ["churned_customers", "lost_customers",
                            "customers_lost", "churn_count", "cancelled_customers"],
    "ending_customers":   ["ending_customers", "total_customers",
                            "active_customers", "customer_count", "accounts"],
}

BUDGET_ALIASES = {
    "month":               ["month","date","period","reporting_month"],
    "region":              ["region","geography","geo","area","territory","market"],
    "segment":             ["segment","tier","customer_segment","plan"],
    "budgeted_ending_arr": ["budgeted_ending_arr","budget_arr","planned_arr",
                             "target_arr","arr_target","arr_plan","plan_arr"],
    "budgeted_new_arr":    ["budgeted_new_arr","budget_new_arr","planned_new_arr",
                             "target_new_arr"],
    "budgeted_mrr":        ["budgeted_mrr","budget_mrr","planned_mrr",
                             "target_mrr","mrr_plan","mrr_target"],
}

EXPENSES_ALIASES = {
    "month":                   ["month","date","period","reporting_month"],
    "total_opex":              ["total_opex","total_expenses","opex",
                                 "total_cost","total_costs","expenses"],
    "salaries_engineering":    ["salaries_engineering","engineering_salaries",
                                 "r&d","rd_cost","tech_payroll","engineering_cost",
                                 "dev_salaries","development_cost"],
    "salaries_sales":          ["salaries_sales","sales_salaries","sales_payroll",
                                 "sales_compensation","sales_cost"],
    "salaries_gna":            ["salaries_gna","gna_salaries","gna","g&a",
                                 "general_admin","admin_cost","overhead"],
    "sales_marketing":         ["sales_marketing","marketing","marketing_spend",
                                 "gtm_spend","s&m","sales_and_marketing",
                                 "marketing_cost","growth_spend"],
    "cloud_infrastructure":    ["cloud_infrastructure","infrastructure","cloud",
                                 "hosting","aws","gcp","azure","server_cost",
                                 "infra_cost"],
    "office_admin":            ["office_admin","office","facilities","rent",
                                 "admin","office_cost"],
    "software_tools":          ["software_tools","tools","software","saas_tools",
                                 "subscriptions","software_cost"],
}


# ── COLUMN MAPPER ──────────────────────────────────────────────────────────
def _map_columns(df: pd.DataFrame, alias_map: dict) -> tuple[pd.DataFrame, dict]:
    """
    Try to rename df columns to standard names using alias_map.
    Returns (renamed_df, mapping_log) where mapping_log shows what was renamed.
    """
    df = df.copy()
    # Normalise uploaded column names: lowercase, strip spaces, replace spaces with _
    df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_")
                  for c in df.columns]

    rename_map = {}
    for standard_name, aliases in alias_map.items():
        for alias in aliases:
            if alias in df.columns and standard_name not in df.columns:
                rename_map[alias] = standard_name
                break

    df = df.rename(columns=rename_map)
    return df, rename_map


def _infer_missing_columns(df: pd.DataFrame, file_type: str) -> pd.DataFrame:
    """
    If some columns are missing, try to derive them from what's present.
    For example: mrr = ending_arr / 12, net_new_arr = new_arr + expansion_arr - churned_arr
    """
    df = df.copy()

    if file_type == "revenue":
        # Derive mrr from ending_arr
        if "mrr" not in df.columns and "ending_arr" in df.columns:
            df["mrr"] = (df["ending_arr"] / 12).round(0)
            st.info("ℹ️  MRR column not found — derived as ending_arr ÷ 12")

        # Derive net_new_arr
        if "net_new_arr" not in df.columns:
            cols_present = all(c in df.columns for c in ["new_arr","expansion_arr","churned_arr"])
            if cols_present:
                df["net_new_arr"] = df["new_arr"] + df["expansion_arr"] - df["churned_arr"]
                st.info("ℹ️  Net New ARR derived from: New + Expansion − Churn")

        # Derive beginning_arr if missing
        if "beginning_arr" not in df.columns and "ending_arr" in df.columns:
            if "net_new_arr" in df.columns:
                df["beginning_arr"] = df["ending_arr"] - df["net_new_arr"]
            else:
                df["beginning_arr"] = df["ending_arr"]

        # Default customer counts to 0 if absent
        for col in ["new_customers","churned_customers","ending_customers"]:
            if col not in df.columns:
                df[col] = 0

    if file_type == "budget":
        if "budgeted_mrr" not in df.columns and "budgeted_ending_arr" in df.columns:
            df["budgeted_mrr"] = (df["budgeted_ending_arr"] / 12).round(0)
        if "budgeted_new_arr" not in df.columns and "budgeted_ending_arr" in df.columns:
            df["budgeted_new_arr"] = (df["budgeted_ending_arr"] * 0.10).round(0)

    if file_type == "expenses":
        expense_cols = ["salaries_engineering","salaries_sales","salaries_gna",
                        "sales_marketing","cloud_infrastructure","office_admin","software_tools"]
        if "total_opex" not in df.columns:
            present = [c for c in expense_cols if c in df.columns]
            if present:
                df["total_opex"] = df[present].sum(axis=1)
                st.info(f"ℹ️  total_opex derived by summing: {', '.join(present)}")
        # Fill missing category breakdowns with 0
        for col in expense_cols:
            if col not in df.columns:
                df[col] = 0

    return df


def _validate_upload(df: pd.DataFrame, required: list, file_name: str) -> list:
    """Return list of missing required columns after mapping."""
    missing = [c for c in required if c not in df.columns]
    return missing


def _parse_month(df: pd.DataFrame) -> pd.DataFrame:
    """Try multiple date formats for the month column."""
    df = df.copy()
    for fmt in ["%Y-%m", "%Y-%m-%d", "%m/%Y", "%b %Y", "%B %Y", "%Y/%m"]:
        try:
            df["month"] = pd.to_datetime(df["month"], format=fmt)
            return df
        except Exception:
            continue
    # Last resort: let pandas infer
    df["month"] = pd.to_datetime(df["month"], infer_datetime_format=True)
    return df


# ── TEMPLATE GENERATORS ────────────────────────────────────────────────────
def revenue_template() -> pd.DataFrame:
    months = pd.date_range("2024-01-01", periods=12, freq="MS").strftime("%Y-%m")
    rows = []
    for m in months:
        for region in ["North","South","West"]:
            for segment in ["Enterprise","Mid-Market","SMB"]:
                rows.append({
                    "month": m, "region": region, "segment": segment,
                    "beginning_arr": 0, "new_arr": 0, "expansion_arr": 0,
                    "churned_arr": 0, "net_new_arr": 0, "ending_arr": 0,
                    "mrr": 0, "new_customers": 0,
                    "churned_customers": 0, "ending_customers": 0,
                })
    return pd.DataFrame(rows)


def budget_template() -> pd.DataFrame:
    months = pd.date_range("2024-01-01", periods=12, freq="MS").strftime("%Y-%m")
    rows = []
    for m in months:
        for region in ["North","South","West"]:
            for segment in ["Enterprise","Mid-Market","SMB"]:
                rows.append({
                    "month": m, "region": region, "segment": segment,
                    "budgeted_ending_arr": 0,
                    "budgeted_new_arr": 0,
                    "budgeted_mrr": 0,
                })
    return pd.DataFrame(rows)


def expenses_template() -> pd.DataFrame:
    months = pd.date_range("2024-01-01", periods=12, freq="MS").strftime("%Y-%m")
    return pd.DataFrame([{
        "month": m,
        "salaries_engineering": 0, "salaries_sales": 0, "salaries_gna": 0,
        "sales_marketing": 0, "cloud_infrastructure": 0,
        "office_admin": 0, "software_tools": 0, "total_opex": 0,
    } for m in months])


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ── STREAMLIT UPLOADER PAGE ────────────────────────────────────────────────
def render_upload_page() -> dict | None:
    """
    Renders the upload UI. Returns a dict of DataFrames if upload is
    complete and valid, or None if not ready yet.
    """
    st.title("📂 Upload Your Company Data")
    st.caption("Upload CSVs for any SaaS company — the pipeline adapts automatically.")
    st.divider()

    # ── Mode selector ──────────────────────────────────────────────────────
    mode = st.radio(
        "Data source",
        ["🏢 Use Zenvora demo data", "📤 Upload my own CSVs", "📋 Download templates first"],
        horizontal=True,
    )

    # ── MODE A: Demo ───────────────────────────────────────────────────────
    if mode == "🏢 Use Zenvora demo data":
        st.success("✅ Using Zenvora synthetic data (FY 2024, INR). Proceed to any dashboard page.")
        return None   # caller uses the pre-loaded tables

    # ── MODE C: Templates ──────────────────────────────────────────────────
    if mode == "📋 Download templates first":
        st.info("Download these three templates, fill in your company's numbers, then come back and upload them.")
        c1, c2, c3 = st.columns(3)
        c1.download_button("⬇ revenue_template.csv",
                            df_to_csv_bytes(revenue_template()),
                            "revenue_template.csv", "text/csv")
        c2.download_button("⬇ budget_template.csv",
                            df_to_csv_bytes(budget_template()),
                            "budget_template.csv", "text/csv")
        c3.download_button("⬇ expenses_template.csv",
                            df_to_csv_bytes(expenses_template()),
                            "expenses_template.csv", "text/csv")

        st.markdown("""
        #### Template filling guide
        | Column | What to put |
        |---|---|
        | `month` | Format: `2024-01` (YYYY-MM) |
        | `region` | Your sales regions e.g. North / South / West |
        | `segment` | Customer tiers e.g. Enterprise / Mid-Market / SMB |
        | `ending_arr` | Total ARR at month end (in your currency) |
        | `new_arr` | ARR from new logos this month |
        | `expansion_arr` | ARR from upsells / seat expansions |
        | `churned_arr` | ARR lost to cancellations |
        | `total_opex` | Total operating expenses this month |

        **Tip:** You don't need every column. The engine will derive `mrr`, `net_new_arr`,
        and `beginning_arr` automatically if they're missing.
        """)
        return None

    # ── MODE B: Custom upload ──────────────────────────────────────────────
    st.markdown("### Upload your three files")
    st.caption("Column names don't need to match exactly — the engine auto-maps common variations.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Revenue file** *(required)*")
        rev_file = st.file_uploader("revenue.csv", type=["csv"], key="rev")
    with col2:
        st.markdown("**Budget file** *(required)*")
        bud_file = st.file_uploader("budget.csv", type=["csv"], key="bud")
    with col3:
        st.markdown("**Expenses file** *(optional)*")
        exp_file = st.file_uploader("expenses.csv", type=["csv"], key="exp")

    if not rev_file or not bud_file:
        st.info("👆 Upload at least the revenue and budget files to continue.")
        return None

    # ── Parse & map ────────────────────────────────────────────────────────
    results = {}
    all_ok  = True

    # Revenue
    with st.expander("🔍 Revenue file validation", expanded=True):
        rev_df = pd.read_csv(rev_file)
        rev_df, rev_map = _map_columns(rev_df, REVENUE_ALIASES)
        rev_df = _infer_missing_columns(rev_df, "revenue")
        rev_df = _parse_month(rev_df)

        required_rev = ["month","region","segment","ending_arr","new_arr",
                        "expansion_arr","churned_arr","mrr"]
        missing_rev  = _validate_upload(rev_df, required_rev, "revenue")

        if rev_map:
            st.success(f"✅ Auto-mapped {len(rev_map)} columns: {rev_map}")
        if missing_rev:
            st.error(f"❌ Still missing after mapping: {missing_rev}")
            all_ok = False
        else:
            st.success(f"✅ Revenue file ready — {len(rev_df)} rows, "
                       f"{rev_df['month'].dt.to_period('M').nunique()} months")
            results["revenue"] = rev_df

    # Budget
    with st.expander("🔍 Budget file validation", expanded=True):
        bud_df = pd.read_csv(bud_file)
        bud_df, bud_map = _map_columns(bud_df, BUDGET_ALIASES)
        bud_df = _infer_missing_columns(bud_df, "budget")
        bud_df = _parse_month(bud_df)

        required_bud = ["month","region","segment","budgeted_ending_arr"]
        missing_bud  = _validate_upload(bud_df, required_bud, "budget")

        if bud_map:
            st.success(f"✅ Auto-mapped {len(bud_map)} columns: {bud_map}")
        if missing_bud:
            st.error(f"❌ Still missing: {missing_bud}")
            all_ok = False
        else:
            st.success(f"✅ Budget file ready — {len(bud_df)} rows")
            results["budget"] = bud_df

    # Expenses (optional — synthesise if missing)
    if exp_file:
        with st.expander("🔍 Expenses file validation", expanded=True):
            exp_df = pd.read_csv(exp_file)
            exp_df, exp_map = _map_columns(exp_df, EXPENSES_ALIASES)
            exp_df = _infer_missing_columns(exp_df, "expenses")
            exp_df = _parse_month(exp_df)
            if exp_map:
                st.success(f"✅ Auto-mapped {len(exp_map)} columns: {exp_map}")
            st.success(f"✅ Expenses file ready — {len(exp_df)} rows")
            results["expenses"] = exp_df
    else:
        # Synthesise minimal expense data from revenue scale
        if "revenue" in results:
            arr_scale = results["revenue"].groupby("month")["ending_arr"].sum().mean()
            # Rough benchmark: opex ≈ 8–10% of ARR per month
            months_df = results["revenue"][["month"]].drop_duplicates().sort_values("month")
            synth_opex = max(arr_scale * 0.085, 500_000)
            exp_rows = []
            for _, row in months_df.iterrows():
                exp_rows.append({
                    "month": row["month"],
                    "total_opex":            round(synth_opex),
                    "salaries_engineering":  round(synth_opex * 0.38),
                    "salaries_sales":        round(synth_opex * 0.22),
                    "salaries_gna":          round(synth_opex * 0.11),
                    "sales_marketing":       round(synth_opex * 0.16),
                    "cloud_infrastructure":  round(synth_opex * 0.07),
                    "office_admin":          round(synth_opex * 0.04),
                    "software_tools":        round(synth_opex * 0.02),
                })
            results["expenses"] = pd.DataFrame(exp_rows)
            st.info("ℹ️  No expenses file uploaded — estimated from ARR scale (8.5% of ARR/month). Upload an expenses file for accurate burn analysis.")

    if not all_ok:
        st.warning("⚠️ Fix the errors above before running the analysis.")
        return None

    # ── Company metadata ───────────────────────────────────────────────────
    st.divider()
    st.markdown("### Company details *(optional — for dashboard labels)*")
    c1, c2, c3 = st.columns(3)
    company_name = c1.text_input("Company name", value="My Company")
    currency     = c2.selectbox("Currency", ["₹ INR", "$ USD", "€ EUR", "£ GBP"], index=0)
    industry     = c3.text_input("Industry", value="SaaS")

    # Store metadata in session
    st.session_state["company_name"] = company_name
    st.session_state["currency"]     = currency.split()[0]
    st.session_state["industry"]     = industry

    if st.button("🚀 Run FP&A Analysis", type="primary", use_container_width=True):
        with st.spinner("Running pipeline — cleaning data, computing KPIs, generating insights..."):
            from pipeline.cleaner import run_cleaning
            from pipeline.metrics import run_metrics

            _, _, _, master = run_cleaning(results)
            tables = run_metrics(master)
            st.session_state["custom_tables"]     = tables
            st.session_state["custom_company"]    = company_name
            st.session_state["using_custom_data"] = True
            st.success(f"✅ Analysis complete for **{company_name}** — navigate to any dashboard page.")
            return tables

    return None
