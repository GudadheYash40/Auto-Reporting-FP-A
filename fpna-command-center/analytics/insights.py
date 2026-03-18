"""
insights.py
-----------
Responsibility: Convert variance numbers into natural-language FP&A
commentary — the kind a finance analyst writes for an MBR deck.

Architecture:
  1.  _classify()       → reads KPIs, returns a structured signal dict
  2.  _build_sentences() → maps signals → sentence templates (filled with ₹ values)
  3.  generate()        → public API — returns full InsightReport dataclass

Design principle: rules are EXPLICIT. Every sentence traces back to a
specific threshold or condition. This means you can explain every word
the engine produces — which is exactly what interviewers will ask.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field


# ── INR FORMATTER ──────────────────────────────────────────────────────────
def _inr(val: float, unit: str = "auto") -> str:
    """Format a rupee value in Indian notation."""
    val = float(val)
    if unit == "cr"   or (unit == "auto" and abs(val) >= 1e7):
        return f"₹{abs(val)/1e7:.2f} Cr"
    if unit == "lakh" or (unit == "auto" and abs(val) >= 1e5):
        return f"₹{abs(val)/1e5:.1f}L"
    return f"₹{abs(val):,.0f}"


# ── THRESHOLDS (tuneable) ───────────────────────────────────────────────────
THRESHOLDS = {
    "arr_var_minor":      0.03,   # 3%  — mention but not alarming
    "arr_var_moderate":   0.08,   # 8%  — warrants explanation
    "arr_var_critical":   0.15,   # 15% — escalation language
    "nrr_healthy":        1.00,   # 100% — benchmark
    "nrr_warning":        0.97,   # 97%  — flag for management
    "burn_efficient":     1.00,   # <1×  — excellent
    "burn_acceptable":    1.50,   # <1.5× — acceptable
    "burn_high":          2.00,   # >2×  — concern
    "ltv_cac_strong":     5.0,    # >5× — healthy unit economics
    "ltv_cac_warning":    3.0,    # <3× — concerning
    "churn_low":          0.005,  # 0.5%/month — best in class
    "churn_high":         0.025,  # 2.5%/month — needs attention
}


# ── INSIGHT REPORT DATACLASS ───────────────────────────────────────────────
@dataclass
class InsightReport:
    month:             str
    headline:          str           # One-line executive summary
    revenue_insights:  list  = field(default_factory=list)   # 2-4 bullets
    efficiency_insights: list = field(default_factory=list)  # 2-3 bullets
    risk_flags:        list  = field(default_factory=list)   # 0-3 red flags
    positive_signals:  list  = field(default_factory=list)   # 0-3 green signals
    recommended_actions: list = field(default_factory=list)  # 1-3 actions
    overall_rating:    str   = "neutral"   # "strong" | "neutral" | "at-risk"


# ── SIGNAL CLASSIFIER ──────────────────────────────────────────────────────
def _classify(monthly_row: pd.Series, seg_details: list, reg_details: list) -> dict:
    """
    Read KPIs and return a structured signal dict.
    Every downstream sentence template reads from this dict — no raw numbers
    in the template layer.
    """
    arr_var_pct   = float(monthly_row["arr_var_pct"]) / 100
    nrr           = float(monthly_row["nrr"])
    burn_multiple = float(monthly_row["burn_multiple"])
    ltv_cac       = float(monthly_row["ltv_cac"])
    churn_rate    = float(monthly_row["gross_churn_rate"])
    arr_variance  = float(monthly_row["arr_variance"])
    new_arr       = float(monthly_row["total_new_arr"])
    expansion_arr = float(monthly_row["total_expansion_arr"])
    churned_arr   = float(monthly_row["total_churned_arr"])
    net_new_arr   = float(monthly_row["total_net_new_arr"])
    total_arr     = float(monthly_row["total_ending_arr"])
    total_opex    = float(monthly_row["total_opex"])

    # Segment movers
    seg_sorted     = sorted(seg_details, key=lambda x: x["arr_variance"])
    worst_seg      = seg_sorted[0]  if seg_sorted else None
    best_seg       = seg_sorted[-1] if seg_sorted else None

    # Region movers
    reg_sorted     = sorted(reg_details, key=lambda x: x["arr_variance"])
    worst_reg      = reg_sorted[0]  if reg_sorted else None
    best_reg       = reg_sorted[-1] if reg_sorted else None

    return dict(
        # Revenue
        arr_var_pct      = arr_var_pct,
        arr_variance     = arr_variance,
        arr_variance_abs = abs(arr_variance),
        arr_favorable    = arr_variance >= 0,
        arr_minor        = abs(arr_var_pct) < THRESHOLDS["arr_var_minor"],
        arr_moderate     = THRESHOLDS["arr_var_minor"] <= abs(arr_var_pct) < THRESHOLDS["arr_var_moderate"],
        arr_significant  = abs(arr_var_pct) >= THRESHOLDS["arr_var_moderate"],
        arr_critical     = abs(arr_var_pct) >= THRESHOLDS["arr_var_critical"],

        # Components
        new_arr          = new_arr,
        expansion_arr    = expansion_arr,
        churned_arr      = churned_arr,
        net_new_arr      = net_new_arr,
        total_arr        = total_arr,

        # Retention
        nrr              = nrr,
        nrr_healthy      = nrr >= THRESHOLDS["nrr_healthy"],
        nrr_warning      = nrr < THRESHOLDS["nrr_warning"],
        churn_rate       = churn_rate,
        churn_low        = churn_rate <= THRESHOLDS["churn_low"],
        churn_high       = churn_rate >= THRESHOLDS["churn_high"],

        # Efficiency
        burn_multiple    = burn_multiple,
        burn_efficient   = burn_multiple <= THRESHOLDS["burn_efficient"],
        burn_acceptable  = burn_multiple <= THRESHOLDS["burn_acceptable"],
        burn_high        = burn_multiple >= THRESHOLDS["burn_high"],
        total_opex       = total_opex,
        ltv_cac          = ltv_cac,
        ltv_cac_strong   = ltv_cac >= THRESHOLDS["ltv_cac_strong"],
        ltv_cac_warning  = ltv_cac < THRESHOLDS["ltv_cac_warning"],

        # Dimensions
        worst_seg        = worst_seg,
        best_seg         = best_seg,
        worst_reg        = worst_reg,
        best_reg         = best_reg,
    )


# ── SENTENCE BUILDER ───────────────────────────────────────────────────────
def _build_sentences(s: dict, month: str) -> InsightReport:
    """
    Map signals → sentences. Each condition maps to exactly one sentence.
    This is a deterministic rule engine — no ML, no randomness.
    """
    report = InsightReport(month=month, headline="")

    # ── HEADLINE ────────────────────────────────────────────────────────
    if s["arr_favorable"] and s["arr_significant"]:
        report.headline = (
            f"{month} revenue beat budget by {_inr(s['arr_variance_abs'])} "
            f"({abs(s['arr_var_pct'])*100:.1f}% favorable) — "
            f"expansion ARR of {_inr(s['expansion_arr'])} was the primary driver."
        )
        report.overall_rating = "strong"

    elif s["arr_favorable"] and not s["arr_significant"]:
        report.headline = (
            f"{month} revenue in line with budget, {_inr(s['arr_variance_abs'])} "
            f"favorable. Net New ARR of {_inr(s['net_new_arr'])} sustaining growth trajectory."
        )
        report.overall_rating = "neutral"

    elif not s["arr_favorable"] and s["arr_critical"]:
        report.headline = (
            f"⚠️ {month} revenue missed budget by {_inr(s['arr_variance_abs'])} "
            f"({abs(s['arr_var_pct'])*100:.1f}% unfavorable) — "
            f"churn of {_inr(s['churned_arr'])} exceeded plan. Immediate review required."
        )
        report.overall_rating = "at-risk"

    elif not s["arr_favorable"] and s["arr_significant"]:
        report.headline = (
            f"{month} revenue missed budget by {_inr(s['arr_variance_abs'])} "
            f"({abs(s['arr_var_pct'])*100:.1f}% unfavorable). "
            f"New business of {_inr(s['new_arr'])} partially offset churn of {_inr(s['churned_arr'])}."
        )
        report.overall_rating = "at-risk"

    else:
        report.headline = (
            f"{month} revenue {_inr(s['arr_variance_abs'])} "
            f"{'above' if s['arr_favorable'] else 'below'} budget. "
            f"Performance within acceptable variance range."
        )
        report.overall_rating = "neutral"

    # ── REVENUE INSIGHTS ────────────────────────────────────────────────

    # 1. New business
    report.revenue_insights.append(
        f"New business ARR of {_inr(s['new_arr'])} "
        f"{'contributed positively' if s['net_new_arr'] > 0 else 'was below expectations'} "
        f"to the month's growth motion."
    )

    # 2. Expansion
    if s["expansion_arr"] > 0:
        report.revenue_insights.append(
            f"Seat expansion and upsells added {_inr(s['expansion_arr'])} in expansion ARR — "
            f"{'strong signal of product stickiness in existing accounts.' if s['expansion_arr'] > 1e6 else 'moderate upsell activity this month.'}"
        )

    # 3. Churn
    if s["churn_high"]:
        report.revenue_insights.append(
            f"Gross churn of {_inr(s['churned_arr'])} ({s['churn_rate']*100:.2f}%/month) "
            f"is elevated above the {THRESHOLDS['churn_high']*100:.1f}% threshold. "
            f"{'SMB segment showing highest churn pressure.' if s['worst_seg'] and str(s['worst_seg']['segment']) == 'SMB' else 'Review customer health scores across all segments.'}"
        )
    elif s["churn_low"]:
        report.revenue_insights.append(
            f"Churn remained well-controlled at {_inr(s['churned_arr'])} "
            f"({s['churn_rate']*100:.2f}%/month) — below the {THRESHOLDS['churn_low']*100:.1f}% best-in-class benchmark."
        )
    else:
        report.revenue_insights.append(
            f"Churn of {_inr(s['churned_arr'])} ({s['churn_rate']*100:.2f}%/month) "
            f"within acceptable range. No immediate action required."
        )

    # 4. Segment dimension
    if s["worst_seg"] and s["best_seg"]:
        worst_name = str(s["worst_seg"]["segment"])
        best_name  = str(s["best_seg"]["segment"])
        worst_var  = s["worst_seg"]["arr_variance"]
        best_var   = s["best_seg"]["arr_variance"]
        report.revenue_insights.append(
            f"By segment: {best_name} led with {_inr(best_var)} "
            f"{'favorable' if best_var >= 0 else 'unfavorable'} variance; "
            f"{worst_name} lagged with {_inr(abs(worst_var))} unfavorable variance — "
            f"{'investigate pricing pressure and competitive displacement.' if worst_name == 'SMB' else 'review deal pipeline and renewal calendar.'}"
        )

    # 5. Region dimension
    if s["worst_reg"] and s["best_reg"]:
        report.revenue_insights.append(
            f"By region: {s['best_reg']['region']} outperformed; "
            f"{s['worst_reg']['region']} underperformed with "
            f"{_inr(abs(s['worst_reg']['arr_variance']))} unfavorable variance "
            f"({s['worst_reg']['arr_var_pct']:+.1f}%)."
        )

    # ── EFFICIENCY INSIGHTS ─────────────────────────────────────────────

    # Burn multiple
    if s["burn_efficient"]:
        report.efficiency_insights.append(
            f"Burn multiple of {s['burn_multiple']:.2f}× is excellent — "
            f"generating {_inr(s['net_new_arr'])} Net New ARR on {_inr(s['total_opex'])} opex."
        )
    elif s["burn_acceptable"]:
        report.efficiency_insights.append(
            f"Burn multiple of {s['burn_multiple']:.2f}× is within acceptable range. "
            f"Every ₹1 of burn is generating ₹{1/s['burn_multiple']:.2f} in Net New ARR."
        )
    elif s["burn_high"]:
        report.efficiency_insights.append(
            f"Burn multiple of {s['burn_multiple']:.2f}× is high — "
            f"spending {_inr(s['total_opex'])} to generate only {_inr(s['net_new_arr'])} Net New ARR. "
            f"Capital efficiency needs urgent improvement."
        )
    else:
        report.efficiency_insights.append(
            f"Burn multiple of {s['burn_multiple']:.2f}× slightly above 1.5× target. "
            f"Monitor for deterioration in coming months."
        )

    # NRR
    if s["nrr_healthy"]:
        report.efficiency_insights.append(
            f"NRR of {s['nrr']*100:.1f}% is above 100% — existing customers are expanding "
            f"faster than they are churning. This reduces dependence on new logo acquisition."
        )
    elif s["nrr_warning"]:
        report.efficiency_insights.append(
            f"NRR of {s['nrr']*100:.1f}% has dropped below 97% — a meaningful warning signal. "
            f"Net revenue from existing customers is contracting. "
            f"Prioritise customer success investment and renewal risk reviews."
        )
    else:
        report.efficiency_insights.append(
            f"NRR of {s['nrr']*100:.1f}% is below 100% — churn is outpacing expansion. "
            f"Investigate root causes across the customer base."
        )

    # LTV:CAC
    if s["ltv_cac_strong"]:
        report.efficiency_insights.append(
            f"LTV:CAC ratio of {s['ltv_cac']:.1f}× signals strong unit economics — "
            f"each customer acquired generates {s['ltv_cac']:.1f}× their acquisition cost over their lifetime."
        )
    elif s["ltv_cac_warning"]:
        report.efficiency_insights.append(
            f"LTV:CAC of {s['ltv_cac']:.1f}× is below the 3× healthy threshold. "
            f"Either reduce CAC through more efficient GTM or improve retention to extend LTV."
        )

    # ── RISK FLAGS ──────────────────────────────────────────────────────
    if not s["arr_favorable"] and s["arr_significant"]:
        report.risk_flags.append(
            f"Revenue miss of {_inr(s['arr_variance_abs'])} ({abs(s['arr_var_pct'])*100:.1f}%) "
            f"exceeds the 8% moderate threshold — requires CFO-level commentary in MBR deck."
        )

    if s["nrr_warning"]:
        report.risk_flags.append(
            f"NRR below 97% for this period — if this persists for 2 consecutive months, "
            f"it signals structural retention issues rather than one-off churn events."
        )

    if s["burn_high"]:
        report.risk_flags.append(
            f"Burn multiple of {s['burn_multiple']:.2f}× will compress runway meaningfully "
            f"if Net New ARR does not accelerate in the next quarter."
        )

    if s["churn_high"]:
        report.risk_flags.append(
            f"Monthly churn rate of {s['churn_rate']*100:.2f}% implies an annualised churn "
            f"of ~{s['churn_rate']*12*100:.1f}% — well above best-in-class SaaS benchmarks."
        )

    # ── POSITIVE SIGNALS ────────────────────────────────────────────────
    if s["expansion_arr"] > 1_000_000:
        report.positive_signals.append(
            f"Expansion ARR of {_inr(s['expansion_arr'])} demonstrates strong product-led "
            f"growth within existing accounts."
        )

    if s["ltv_cac_strong"]:
        report.positive_signals.append(
            f"LTV:CAC of {s['ltv_cac']:.1f}× is well above the 5× strong threshold — "
            f"unit economics support accelerated GTM investment."
        )

    if s["burn_efficient"] or s["burn_acceptable"]:
        report.positive_signals.append(
            f"Capital efficiency (burn multiple {s['burn_multiple']:.2f}×) is healthy — "
            f"growth is being funded efficiently relative to cash deployed."
        )

    if s["nrr_healthy"]:
        report.positive_signals.append(
            f"NRR above 100% reduces new logo dependency — "
            f"existing customer base is self-sustaining for revenue growth."
        )

    # ── RECOMMENDED ACTIONS ─────────────────────────────────────────────
    if not s["arr_favorable"] and s["arr_significant"]:
        report.recommended_actions.append(
            f"Conduct win/loss review for {str(s['worst_seg']['segment']) if s['worst_seg'] else 'underperforming'} "
            f"segment — identify whether miss is pipeline, pricing, or competitive."
        )

    if s["churn_high"] or s["nrr_warning"]:
        report.recommended_actions.append(
            "Activate 90-day customer health programme — CSM to personally review "
            "all accounts with health score below 70 and flag renewal risk by next MBR."
        )

    if s["burn_high"]:
        report.recommended_actions.append(
            "Freeze discretionary spend and delay non-critical hires until Net New ARR "
            "returns above ₹60L/month — present revised hiring plan at next board review."
        )

    if s["ltv_cac_warning"]:
        report.recommended_actions.append(
            "Audit sales cycle efficiency — reduce CAC by tightening ICP definition "
            "and shifting budget toward highest-converting acquisition channels."
        )

    if not report.recommended_actions:
        report.recommended_actions.append(
            "Maintain current trajectory. Review expansion motion to sustain NRR above 100% "
            "heading into Q1 planning cycle."
        )

    return report


# ── PUBLIC API ─────────────────────────────────────────────────────────────
def generate(monthly_row: pd.Series,
             seg_details: list,
             reg_details: list) -> InsightReport:
    """
    Main entry point for the insights engine.

    Args:
        monthly_row : one row from monthly_kpis DataFrame
        seg_details : list of dicts from segment_variance for this month
        reg_details : list of dicts from region_variance for this month

    Returns:
        InsightReport dataclass
    """
    month   = str(monthly_row["month_label"])
    signals = _classify(monthly_row, seg_details, reg_details)
    report  = _build_sentences(signals, month)
    return report


def generate_all_months(monthly: pd.DataFrame,
                        seg_var: pd.DataFrame,
                        reg_var: pd.DataFrame) -> list:
    """Generate InsightReport for every month in the dataset."""
    reports = []
    for _, row in monthly.iterrows():
        ml = row["month_label"]
        seg_d = seg_var[seg_var["month_label"] == ml].to_dict("records")
        reg_d = reg_var[reg_var["month_label"] == ml].to_dict("records")
        reports.append(generate(row, seg_d, reg_d))
    return reports


# ── REPORT PRINTER ─────────────────────────────────────────────────────────
def print_report(r: InsightReport):
    rating_icon = {"strong": "🟢", "neutral": "🟡", "at-risk": "🔴"}.get(r.overall_rating, "⚪")
    print(f"\n{'═'*70}")
    print(f"  {rating_icon}  INSIGHT REPORT — {r.month}  [{r.overall_rating.upper()}]")
    print(f"{'═'*70}")
    print(f"\n  HEADLINE\n  {r.headline}")

    if r.revenue_insights:
        print(f"\n  REVENUE ANALYSIS")
        for i, s in enumerate(r.revenue_insights, 1):
            print(f"  {i}. {s}")

    if r.efficiency_insights:
        print(f"\n  EFFICIENCY & UNIT ECONOMICS")
        for i, s in enumerate(r.efficiency_insights, 1):
            print(f"  {i}. {s}")

    if r.risk_flags:
        print(f"\n  ⚠️  RISK FLAGS")
        for s in r.risk_flags:
            print(f"  • {s}")

    if r.positive_signals:
        print(f"\n  ✅ POSITIVE SIGNALS")
        for s in r.positive_signals:
            print(f"  • {s}")

    if r.recommended_actions:
        print(f"\n  RECOMMENDED ACTIONS")
        for i, s in enumerate(r.recommended_actions, 1):
            print(f"  {i}. {s}")
    print()


if __name__ == "__main__":
    import sys
    sys.path.append(".")
    from pipeline.data_loader import load_all
    from pipeline.cleaner import run_cleaning
    from pipeline.metrics import run_metrics
    from analytics.variance import segment_variance, region_variance, company_variance

    raw = load_all()
    _, _, _, master = run_cleaning(raw)
    tables = run_metrics(master)

    monthly = company_variance(tables["monthly_kpis"])
    seg_var = segment_variance(tables["segment_kpis"])
    reg_var = region_variance(tables["region_kpis"])

    # Print reports for three interesting months
    for target_month in ["May 2024", "Sep 2024", "Dec 2024"]:
        row     = monthly[monthly["month_label"] == target_month].iloc[0]
        seg_d   = seg_var[seg_var["month_label"] == target_month].to_dict("records")
        reg_d   = reg_var[reg_var["month_label"] == target_month].to_dict("records")
        report  = generate(row, seg_d, reg_d)
        print_report(report)
