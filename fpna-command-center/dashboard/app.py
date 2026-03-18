"""
app.py  —  Zenvora FP&A Command Center
----------------------------------------
Streamlit dashboard for Monthly Business Review (MBR) reporting.
Run with:  streamlit run dashboard/app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.graph_objects as go
import plotly.express as px
import sys, os

# ── PATH SETUP ─────────────────────────────────────────────────────────────
# Ensures pipeline/ and dashboard/ are importable however Streamlit is launched
_HERE         = os.path.dirname(os.path.abspath(__file__))   # .../dashboard/
_PROJECT_ROOT = os.path.dirname(_HERE)                        # .../fpna-command-center/
for _p in [_PROJECT_ROOT, _HERE]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pipeline.data_loader import load_all
from pipeline.cleaner import run_cleaning
from pipeline.metrics import run_metrics, compute_waterfall_data
try:
    from dashboard.uploader import render_upload_page   # launched from project root
except ModuleNotFoundError:
    from uploader import render_upload_page             # launched from dashboard/

# ── PAGE CONFIG ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Zenvora FP&A Command Center",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── THEME COLORS ───────────────────────────────────────────────────────────
CLR = {
    "purple":  "#534AB7",
    "teal":    "#1D9E75",
    "coral":   "#D85A30",
    "amber":   "#EF9F27",
    "red":     "#E24B4A",
    "gray":    "#888780",
    "bg":      "#F1EFE8",
    "text":    "#2C2C2A",
}

# ── CUSTOM CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* KPI card container */
  div[data-testid="stMetric"]                { background: #f9f8f4; border-radius: 10px;
                                               padding: 16px 20px; border: 0.5px solid #D3D1C7; }
  /* Label row — muted gray */
  [data-testid="stMetricLabel"]  p           { font-size: 0.78rem !important;
                                               color: #5F5E5A !important; font-weight: 400; }
  /* Main value — always dark, high contrast */
  [data-testid="stMetricValue"]              { font-size: 1.55rem !important;
                                               font-weight: 500; color: #2C2C2A !important; }
  [data-testid="stMetricValue"] *            { color: #2C2C2A !important; }
  /* Delta row — keep Streamlit's red/green but ensure readable size */
  [data-testid="stMetricDelta"]              { font-size: 0.82rem !important; }
  [data-testid="stMetricDelta"] p            { font-size: 0.82rem !important; }
  /* Delta arrow + text — positive = teal, negative = red */
  [data-testid="stMetricDelta"][data-direction="up"]   p { color: #0F6E56 !important; }
  [data-testid="stMetricDelta"][data-direction="down"] p { color: #A32D2D !important; }
  [data-testid="stMetricDelta"][data-direction="off"]  p { color: #5F5E5A !important; }
  .section-header                     { font-size: 1rem; font-weight: 500;
                                        color: #2C2C2A; margin: 1.5rem 0 0.5rem; }
  .insight-box                        { background: #EAF3DE; border-left: 3px solid #1D9E75;
                                        border-radius: 6px; padding: 12px 16px;
                                        font-size: 0.88rem; color: #27500A; margin-bottom: 8px; }
  .warn-box                           { background: #FAEEDA; border-left: 3px solid #EF9F27;
                                        border-radius: 6px; padding: 12px 16px;
                                        font-size: 0.88rem; color: #633806; margin-bottom: 8px; }
  .bad-box                            { background: #FCEBEB; border-left: 3px solid #E24B4A;
                                        border-radius: 6px; padding: 12px 16px;
                                        font-size: 0.88rem; color: #501313; margin-bottom: 8px; }
  footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── DATA LOADING (cached) ──────────────────────────────────────────────────
@st.cache_data
def load_demo_data():
    raw = load_all()
    _, _, _, master = run_cleaning(raw)
    return run_metrics(master)

# ── SESSION STATE: pick demo or custom uploaded data ───────────────────────
if "using_custom_data" not in st.session_state:
    st.session_state["using_custom_data"] = False

if st.session_state["using_custom_data"] and "custom_tables" in st.session_state:
    tables       = st.session_state["custom_tables"]
    COMPANY_NAME = st.session_state.get("custom_company", "Your Company")
    CURRENCY_SYM = st.session_state.get("currency", "₹")
else:
    tables       = load_demo_data()
    COMPANY_NAME = "Zenvora"
    CURRENCY_SYM = "₹"
monthly  = tables["monthly_kpis"]
segment  = tables["segment_kpis"]
region   = tables["region_kpis"]

# ── HELPERS ────────────────────────────────────────────────────────────────
def fmt_inr(val, unit="auto"):
    """Format a rupee value with Indian numbering (Cr / L / K)."""
    if pd.isna(val): return "—"
    val = float(val)
    if unit == "cr"  or (unit == "auto" and abs(val) >= 1e7):
        return f"₹{val/1e7:.2f} Cr"
    if unit == "lakh" or (unit == "auto" and abs(val) >= 1e5):
        return f"₹{val/1e5:.1f} L"
    return f"₹{val:,.0f}"

def delta_pct(actual, budget):
    if budget == 0: return 0
    return round((actual - budget) / abs(budget) * 100, 1)

MONTH_LABELS = monthly["month_label"].tolist()

# ── SIDEBAR ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## 📊 {COMPANY_NAME} FP&A")
    st.caption("SaaS · FP&A Command Center")

    # Active data badge
    if st.session_state["using_custom_data"]:
        st.success(f"📂 Custom data: {COMPANY_NAME}")
        if st.button("↩ Switch to demo data", use_container_width=True):
            st.session_state["using_custom_data"] = False
            st.rerun()
    else:
        st.info("📊 Demo: Zenvora (synthetic)")

    st.divider()

    selected_month = st.selectbox(
        "Reporting month",
        MONTH_LABELS,
        index=len(MONTH_LABELS) - 1,
    )
    selected_segment = st.multiselect(
        "Segments",
        ["Enterprise", "Mid-Market", "SMB"],
        default=["Enterprise", "Mid-Market", "SMB"],
    )
    selected_region = st.multiselect(
        "Regions",
        ["North", "South", "West"],
        default=["North", "South", "West"],
    )
    st.divider()
    st.caption("Navigate")
    page = st.radio(
        "View",
        ["📂 Upload Data", "📈 MBR Overview", "🌊 Waterfall Bridge",
         "🔍 Segment Drill-Down", "🎛 Scenario Simulator"],
        label_visibility="collapsed",
    )

# Current month row
cur   = monthly[monthly["month_label"] == selected_month].iloc[0]
# Previous month row (for delta)
cur_idx = MONTH_LABELS.index(selected_month)
prev  = monthly.iloc[max(cur_idx - 1, 0)]

# ══════════════════════════════════════════════════════════════════════════
# PAGE 0 — UPLOAD DATA
# ══════════════════════════════════════════════════════════════════════════
if page == "📂 Upload Data":
    render_upload_page()

# ══════════════════════════════════════════════════════════════════════════
# PAGE 1 — MBR OVERVIEW
# ══════════════════════════════════════════════════════════════════════════
elif page == "📈 MBR Overview":

    st.title("Monthly Business Review")
    st.caption(f"{COMPANY_NAME} · {selected_month} · All figures in {CURRENCY_SYM}")
    st.divider()

    # ── KPI CARDS ROW 1 ───────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    arr_delta = delta_pct(cur.total_ending_arr, cur.total_budgeted_arr)
    c1.metric(
        "Total ARR",
        fmt_inr(cur.total_ending_arr),
        f"{arr_delta:+.1f}% vs budget",
        delta_color="normal" if arr_delta >= 0 else "inverse",
    )

    mrr_delta = delta_pct(cur.total_mrr, prev.total_mrr)
    c2.metric(
        "MRR",
        fmt_inr(cur.total_mrr),
        f"{mrr_delta:+.1f}% vs prev month",
    )

    c3.metric(
        "Net New ARR",
        fmt_inr(cur.total_net_new_arr),
        f"New ₹{cur.total_new_arr/1e5:.0f}L | Exp ₹{cur.total_expansion_arr/1e5:.0f}L | Churn −₹{cur.total_churned_arr/1e5:.0f}L",
        delta_color="off",
    )

    nrr_pct = round(cur.nrr * 100, 1)
    c4.metric(
        "NRR",
        f"{nrr_pct}%",
        "Above 100% ✓" if nrr_pct >= 100 else "Below 100% ✗",
        delta_color="normal" if nrr_pct >= 100 else "inverse",
    )

    c5, c6, c7, c8 = st.columns(4)

    c5.metric("Burn Multiple",
              f"{cur.burn_multiple:.2f}×",
              "Efficient (<1.5×)" if cur.burn_multiple < 1.5 else "High (>1.5×)",
              delta_color="normal" if cur.burn_multiple < 1.5 else "inverse")

    c6.metric("CAC", fmt_inr(cur.cac, "lakh"),
              f"LTV:CAC = {cur.ltv_cac:.1f}×")

    c7.metric("Monthly Opex", fmt_inr(cur.total_opex),
              f"People {fmt_inr(cur.people_cost)} | GTM {fmt_inr(cur.gtm_cost)}", delta_color="off")

    c8.metric("ARR Variance",
              fmt_inr(cur.arr_variance),
              f"{arr_delta:+.1f}% vs plan",
              delta_color="normal" if cur.arr_variance >= 0 else "inverse")

    st.divider()

    # ── ARR TREND CHART ───────────────────────────────────────────────────
    st.markdown('<p class="section-header">ARR trend — actual vs budget</p>', unsafe_allow_html=True)

    fig_arr = go.Figure()
    fig_arr.add_trace(go.Scatter(
        x=monthly["month_label"], y=monthly["total_ending_arr"] / 1e7,
        name="Actual ARR", mode="lines+markers",
        line=dict(color=CLR["purple"], width=2.5),
        marker=dict(size=5),
    ))
    fig_arr.add_trace(go.Scatter(
        x=monthly["month_label"], y=monthly["total_budgeted_arr"] / 1e7,
        name="Budget ARR", mode="lines",
        line=dict(color=CLR["gray"], width=1.5, dash="dot"),
    ))
    fig_arr.update_layout(
        yaxis_title="ARR (₹ Crores)", xaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=0, r=0, t=10, b=0), height=300,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
    )
    fig_arr.update_yaxes(gridcolor="#E8E6DF")
    fig_arr.update_xaxes(gridcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_arr, use_container_width=True)

    # ── NRR + BURN SIDE BY SIDE ───────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<p class="section-header">NRR — monthly</p>', unsafe_allow_html=True)
        nrr_vals = monthly["nrr"] * 100
        fig_nrr = go.Figure()
        fig_nrr.add_hline(y=100, line_dash="dot", line_color=CLR["gray"], line_width=1)
        fig_nrr.add_trace(go.Scatter(
            x=monthly["month_label"], y=nrr_vals.round(2),
            fill="tozeroy", mode="lines+markers",
            line=dict(color=CLR["teal"], width=2),
            fillcolor="rgba(29,158,117,0.1)",
            marker=dict(color=[CLR["teal"] if v >= 100 else CLR["red"] for v in nrr_vals], size=6),
        ))
        fig_nrr.update_layout(
            yaxis_title="NRR (%)", height=260, margin=dict(l=0,r=0,t=10,b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False, font=dict(size=12),
        )
        fig_nrr.update_yaxes(gridcolor="#E8E6DF", range=[96, 103])
        fig_nrr.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_nrr, use_container_width=True)

    with col_r:
        st.markdown('<p class="section-header">Burn multiple — monthly</p>', unsafe_allow_html=True)
        burn_vals = monthly["burn_multiple"]
        fig_burn = go.Figure()
        fig_burn.add_hline(y=1.5, line_dash="dot", line_color=CLR["amber"], line_width=1,
                           annotation_text="1.5× target", annotation_position="top right")
        fig_burn.add_trace(go.Bar(
            x=monthly["month_label"], y=burn_vals,
            marker_color=[CLR["teal"] if v <= 1.5 else CLR["coral"] for v in burn_vals],
            marker_line_width=0,
        ))
        fig_burn.update_layout(
            yaxis_title="Burn Multiple (×)", height=260, margin=dict(l=0,r=0,t=10,b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False, font=dict(size=12),
        )
        fig_burn.update_yaxes(gridcolor="#E8E6DF")
        fig_burn.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_burn, use_container_width=True)

    # ── EXPENSE BREAKDOWN ─────────────────────────────────────────────────
    st.markdown('<p class="section-header">Monthly opex breakdown — ₹ Lakhs</p>', unsafe_allow_html=True)

    raw_exp = load_all()["expenses"]
    raw_exp["month_label"] = pd.to_datetime(raw_exp["month"]).dt.strftime("%b %Y")
    fig_exp = go.Figure()
    for cat, col, color in [
        ("People", "salaries_engineering", CLR["purple"]),
        ("Sales & Mktg", "sales_marketing", CLR["coral"]),
        ("G&A", "salaries_gna", CLR["amber"]),
        ("Infra & Tools", "cloud_infrastructure", CLR["teal"]),
    ]:
        fig_exp.add_trace(go.Bar(
            name=cat,
            x=raw_exp["month_label"],
            y=(raw_exp[col] / 1e5).round(1),
            marker_color=color, marker_line_width=0,
        ))
    fig_exp.update_layout(
        barmode="stack", yaxis_title="₹ Lakhs", height=280,
        margin=dict(l=0,r=0,t=10,b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
    )
    fig_exp.update_yaxes(gridcolor="#E8E6DF")
    fig_exp.update_xaxes(gridcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_exp, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════
# PAGE 2 — WATERFALL BRIDGE
# ══════════════════════════════════════════════════════════════════════════
elif page == "🌊 Waterfall Bridge":

    st.title("Budget → Actual Bridge")
    st.caption(f"Waterfall analysis · {selected_month}")
    st.divider()

    wf = compute_waterfall_data(monthly, selected_month)

    # Build waterfall using Plotly
    measures = []
    for _, row in wf.iterrows():
        if row["type"] == "base":    measures.append("absolute")
        elif row["type"] == "total": measures.append("total")
        else:                        measures.append("relative")

    colors = []
    for _, row in wf.iterrows():
        if row["type"] == "base":     colors.append(CLR["purple"])
        elif row["type"] == "total":  colors.append(CLR["purple"])
        elif row["value"] >= 0:       colors.append(CLR["teal"])
        else:                         colors.append(CLR["red"])

    fig_wf = go.Figure(go.Waterfall(
        name="ARR Bridge",
        orientation="v",
        measure=measures,
        x=wf["label"].tolist(),
        y=wf["value"].tolist(),
        text=[fmt_inr(v) for v in wf["value"]],
        textposition="outside",
        connector=dict(line=dict(color=CLR["gray"], width=1, dash="dot")),
        increasing=dict(marker=dict(color=CLR["teal"])),
        decreasing=dict(marker=dict(color=CLR["red"])),
        totals=dict(marker=dict(color=CLR["purple"])),
    ))
    fig_wf.update_layout(
        yaxis_title="ARR (₹)", height=420,
        margin=dict(l=0, r=0, t=20, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13), showlegend=False,
    )
    fig_wf.update_yaxes(gridcolor="#E8E6DF",
                        tickformat=".2s",
                        tickprefix="₹")
    st.plotly_chart(fig_wf, use_container_width=True)

    # ── Bridge table ──────────────────────────────────────────────────────
    st.markdown('<p class="section-header">Bridge detail</p>', unsafe_allow_html=True)
    wf_display = wf.copy()
    wf_display["value_fmt"] = wf_display["value"].apply(fmt_inr)
    wf_display["impact"] = wf_display["value"].apply(
        lambda v: "✅ Favorable" if v > 0 else ("🔴 Unfavorable" if v < 0 else "—")
    )
    st.dataframe(
        wf_display[["label","value_fmt","impact"]].rename(
            columns={"label":"Driver","value_fmt":"Amount (₹)","impact":"Impact"}
        ),
        hide_index=True, use_container_width=True,
    )

    # ── Auto-generated insight ────────────────────────────────────────────
    st.markdown('<p class="section-header">Auto-generated variance insight</p>', unsafe_allow_html=True)
    variance     = float(cur.arr_variance)
    churn_val    = float(cur.total_churned_arr)
    expansion_val= float(cur.total_expansion_arr)
    new_val      = float(cur.total_new_arr)

    if variance < 0:
        st.markdown(f"""
        <div class="bad-box">
        <b>❗ Revenue missed budget by {fmt_inr(abs(variance))}</b><br>
        Churn of {fmt_inr(churn_val)} was the primary drag, partially offset by expansion ARR of
        {fmt_inr(expansion_val)}. New business contributed {fmt_inr(new_val)} against plan.
        Recommend reviewing SMB retention playbook and accelerating Enterprise upsell motions.
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="insight-box">
        <b>✅ Revenue beat budget by {fmt_inr(variance)}</b><br>
        Expansion ARR of {fmt_inr(expansion_val)} exceeded plan, driven by seat growth in
        Enterprise accounts. New business added {fmt_inr(new_val)}. Churn of {fmt_inr(churn_val)}
        remained within acceptable range.
        </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
# PAGE 3 — SEGMENT DRILL-DOWN
# ══════════════════════════════════════════════════════════════════════════
elif page == "🔍 Segment Drill-Down":

    st.title("Segment Drill-Down")
    st.caption(f"Performance by segment and region · {selected_month}")
    st.divider()

    # ── Segment ARR over time ─────────────────────────────────────────────
    st.markdown('<p class="section-header">ARR by segment — monthly trend</p>', unsafe_allow_html=True)
    seg_colors = {"Enterprise": CLR["purple"], "Mid-Market": CLR["teal"], "SMB": CLR["coral"]}
    fig_seg = go.Figure()
    for seg in ["Enterprise", "Mid-Market", "SMB"]:
        if seg not in selected_segment: continue
        df_s = segment[segment["segment"] == seg]
        fig_seg.add_trace(go.Scatter(
            x=df_s["month_label"], y=df_s["ending_arr"] / 1e7,
            name=seg, mode="lines+markers",
            line=dict(color=seg_colors[seg], width=2),
            marker=dict(size=4),
        ))
    fig_seg.update_layout(
        yaxis_title="ARR (₹ Crores)", height=300,
        margin=dict(l=0,r=0,t=10,b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
    )
    fig_seg.update_yaxes(gridcolor="#E8E6DF")
    fig_seg.update_xaxes(gridcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_seg, use_container_width=True)

    # ── Segment vs Budget for selected month ──────────────────────────────
    st.markdown(f'<p class="section-header">Budget vs actual — {selected_month}</p>', unsafe_allow_html=True)
    cur_seg = segment[segment["month_label"] == selected_month]

    col_l, col_r = st.columns(2)
    with col_l:
        fig_bva = go.Figure()
        for label, col, color in [("Actual ARR","ending_arr",CLR["purple"]),
                                   ("Budget ARR","budgeted_arr",CLR["gray"])]:
            fig_bva.add_trace(go.Bar(
                name=label,
                x=cur_seg["segment"].astype(str),
                y=cur_seg[col] / 1e7,
                marker_color=color, marker_line_width=0,
            ))
        fig_bva.update_layout(
            barmode="group", yaxis_title="₹ Crores", height=280,
            margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        )
        fig_bva.update_yaxes(gridcolor="#E8E6DF")
        st.plotly_chart(fig_bva, use_container_width=True)

    with col_r:
        # Variance % by segment
        fig_var = go.Figure()
        var_pcts = cur_seg["arr_var_pct"].tolist()
        fig_var.add_trace(go.Bar(
            x=cur_seg["segment"].astype(str),
            y=var_pcts,
            marker_color=[CLR["teal"] if v >= 0 else CLR["red"] for v in var_pcts],
            text=[f"{v:+.1f}%" for v in var_pcts],
            textposition="outside",
            marker_line_width=0,
        ))
        fig_var.add_hline(y=0, line_color=CLR["gray"], line_width=1)
        fig_var.update_layout(
            yaxis_title="Variance (%)", height=280,
            margin=dict(l=0,r=0,t=10,b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False, font=dict(size=12),
        )
        fig_var.update_yaxes(gridcolor="#E8E6DF")
        st.plotly_chart(fig_var, use_container_width=True)

    # ── Region heatmap ────────────────────────────────────────────────────
    st.markdown('<p class="section-header">ARR variance % by region — full year</p>', unsafe_allow_html=True)
    region_pivot = region.pivot_table(
        index="month_label", columns="region", values="arr_var_pct"
    ).reindex(MONTH_LABELS)

    fig_heat = px.imshow(
        region_pivot.T,
        color_continuous_scale=["#E24B4A","#F9F8F4","#1D9E75"],
        color_continuous_midpoint=0,
        aspect="auto",
        labels=dict(color="Variance %"),
    )
    fig_heat.update_layout(
        height=220, margin=dict(l=0,r=0,t=10,b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12), coloraxis_colorbar=dict(title="Var %"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # ── NRR by segment table ──────────────────────────────────────────────
    st.markdown(f'<p class="section-header">NRR by segment — {selected_month}</p>', unsafe_allow_html=True)
    nrr_tbl = cur_seg[["segment","ending_arr","beginning_arr",
                        "expansion_arr","churned_arr","nrr"]].copy()
    nrr_tbl["nrr_fmt"]          = (nrr_tbl["nrr"] * 100).round(1).astype(str) + "%"
    nrr_tbl["ending_arr_fmt"]   = nrr_tbl["ending_arr"].apply(fmt_inr)
    nrr_tbl["expansion_arr_fmt"]= nrr_tbl["expansion_arr"].apply(fmt_inr)
    nrr_tbl["churned_arr_fmt"]  = nrr_tbl["churned_arr"].apply(fmt_inr)
    st.dataframe(
        nrr_tbl[["segment","ending_arr_fmt","expansion_arr_fmt",
                 "churned_arr_fmt","nrr_fmt"]].rename(columns={
            "segment":"Segment","ending_arr_fmt":"Ending ARR",
            "expansion_arr_fmt":"Expansion","churned_arr_fmt":"Churned","nrr_fmt":"NRR"
        }),
        hide_index=True, use_container_width=True,
    )


# ══════════════════════════════════════════════════════════════════════════
# PAGE 4 — SCENARIO SIMULATOR
# ══════════════════════════════════════════════════════════════════════════
elif page == "🎛 Scenario Simulator":

    st.title("Scenario Simulator")
    st.caption("Adjust assumptions — see updated year-end projections in real time")
    st.divider()

    # Base values from latest month
    base_arr         = float(monthly["total_ending_arr"].iloc[-1])
    base_net_new_arr = float(monthly["total_net_new_arr"].mean())
    base_opex        = float(monthly["total_opex"].mean())
    base_churn_rate  = float(monthly["gross_churn_rate"].mean())
    remaining_months = 12 - len(monthly)  # months left in year
    CASH_REMAINING   = 15_000_000 - float(monthly["total_opex"].sum())

    # ── Sliders ───────────────────────────────────────────────────────────
    col_s1, col_s2 = st.columns(2)

    with col_s1:
        st.markdown("**Revenue levers**")
        rev_growth_adj = st.slider(
            "Monthly ARR growth rate (%)",
            min_value=-5.0, max_value=20.0,
            value=float(round((base_net_new_arr / base_arr) * 100, 1)),
            step=0.5,
            help="Adjust expected monthly net new ARR as % of current ARR"
        )
        churn_adj = st.slider(
            "Monthly gross churn rate (%)",
            min_value=0.0, max_value=5.0,
            value=float(round(base_churn_rate * 100, 2)),
            step=0.1,
            help="Lower = better retention"
        )
        expansion_adj = st.slider(
            "Expansion ARR multiplier",
            min_value=0.5, max_value=3.0, value=1.0, step=0.1,
            help="1.0 = baseline expansion rate. 2.0 = double the upsell activity"
        )

    with col_s2:
        st.markdown("**Cost levers**")
        headcount_adj = st.slider(
            "Engineering headcount change",
            min_value=-10, max_value=20, value=0, step=1,
            help="Each engineer costs ~₹1.8L/month fully loaded"
        )
        mktg_adj = st.slider(
            "Marketing spend change (%)",
            min_value=-50, max_value=100, value=0, step=5,
            help="Relative change from current monthly marketing budget"
        )
        infra_adj = st.slider(
            "Cloud infra change (%)",
            min_value=-30, max_value=100, value=0, step=5,
        )

    st.divider()

    # ── Simulate 6-month forward projection ───────────────────────────────
    ENG_COST_PER_HEAD  = 180_000
    BASE_MKTG          = 1_200_000
    BASE_INFRA         = 350_000

    sim_months    = 6
    sim_arr       = base_arr
    sim_cash      = CASH_REMAINING
    proj_arr, proj_opex, proj_cash, proj_burn = [], [], [], []

    adj_opex = (
        base_opex
        + headcount_adj * ENG_COST_PER_HEAD
        + BASE_MKTG * (mktg_adj / 100)
        + BASE_INFRA * (infra_adj / 100)
    )

    base_expansion = float(monthly["total_expansion_arr"].mean())

    for i in range(sim_months):
        net_new  = sim_arr * (rev_growth_adj / 100)
        churn    = sim_arr * (churn_adj / 100)
        expansion= base_expansion * expansion_adj
        sim_arr  = max(0, sim_arr + net_new + expansion - churn)
        sim_cash = sim_cash - adj_opex
        burn_m   = adj_opex / max(net_new + expansion - churn, 1)

        proj_arr.append(sim_arr)
        proj_opex.append(adj_opex)
        proj_cash.append(sim_cash)
        proj_burn.append(burn_m)

    proj_labels = [f"M+{i+1}" for i in range(sim_months)]
    runway_sim  = sim_cash / adj_opex if adj_opex > 0 else 99

    # ── Output KPI cards ──────────────────────────────────────────────────
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Projected ARR (M+6)", fmt_inr(proj_arr[-1]),
               f"{delta_pct(proj_arr[-1], base_arr):+.1f}% vs today")
    sc2.metric("Projected Monthly Opex", fmt_inr(adj_opex),
               f"{delta_pct(adj_opex, base_opex):+.1f}% vs baseline")
    sc3.metric("Cash Remaining (M+6)", fmt_inr(proj_cash[-1]))
    sc4.metric("Runway at M+6", f"{max(runway_sim,0):.1f} months",
               "⚠️ Low" if runway_sim < 6 else "✅ Healthy",
               delta_color="normal" if runway_sim >= 6 else "inverse")

    st.divider()

    # ── Projection charts ─────────────────────────────────────────────────
    col_p1, col_p2 = st.columns(2)

    with col_p1:
        st.markdown('<p class="section-header">Projected ARR — next 6 months</p>', unsafe_allow_html=True)
        fig_proj = go.Figure()
        # Historical (last 6 months)
        hist = monthly.tail(6)
        fig_proj.add_trace(go.Scatter(
            x=hist["month_label"], y=hist["total_ending_arr"] / 1e7,
            name="Historical", mode="lines+markers",
            line=dict(color=CLR["purple"], width=2),
        ))
        fig_proj.add_trace(go.Scatter(
            x=proj_labels, y=[v / 1e7 for v in proj_arr],
            name="Projected", mode="lines+markers",
            line=dict(color=CLR["teal"], width=2, dash="dot"),
            marker=dict(symbol="diamond", size=7),
        ))
        fig_proj.update_layout(
            yaxis_title="₹ Crores", height=280,
            margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        )
        fig_proj.update_yaxes(gridcolor="#E8E6DF")
        fig_proj.update_xaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_proj, use_container_width=True)

    with col_p2:
        st.markdown('<p class="section-header">Cash runway — projected</p>', unsafe_allow_html=True)
        fig_cash = go.Figure()
        fig_cash.add_trace(go.Bar(
            x=proj_labels, y=[max(v, 0) / 1e5 for v in proj_cash],
            marker_color=[CLR["teal"] if v > 6 * adj_opex else CLR["red"]
                          for v in proj_cash],
            marker_line_width=0, name="Cash remaining",
        ))
        fig_cash.update_layout(
            yaxis_title="₹ Lakhs", height=280,
            margin=dict(l=0,r=0,t=10,b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False, font=dict(size=12),
        )
        fig_cash.update_yaxes(gridcolor="#E8E6DF")
        st.plotly_chart(fig_cash, use_container_width=True)

    # ── Burn multiple warning ─────────────────────────────────────────────
    avg_proj_burn = float(np.mean(proj_burn))
    if avg_proj_burn > 2.0:
        st.markdown(f"""<div class="bad-box">
        ⚠️ <b>Projected burn multiple is {avg_proj_burn:.2f}×</b> — well above the 1.5× healthy threshold.
        Consider reducing headcount additions or cutting marketing spend to improve capital efficiency.
        </div>""", unsafe_allow_html=True)
    elif avg_proj_burn > 1.5:
        st.markdown(f"""<div class="warn-box">
        🟡 <b>Projected burn multiple is {avg_proj_burn:.2f}×</b> — slightly above target.
        Monitor closely and ensure Net New ARR accelerates in the next quarter.
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div class="insight-box">
        ✅ <b>Projected burn multiple is {avg_proj_burn:.2f}×</b> — within healthy range.
        Current trajectory supports efficient growth.
        </div>""", unsafe_allow_html=True)
