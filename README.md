# 📊 Auto-Reporting FP&A Command Center

> **Automates the Monthly Business Review (MBR) reporting workflow for SaaS companies** — from raw CSVs to executive-ready dashboards with AI-generated variance insights.

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-red?logo=streamlit)](https://streamlit.io)
[![Plotly](https://img.shields.io/badge/Plotly-5.20+-purple?logo=plotly)](https://plotly.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 🎯 Problem This Solves

Finance teams at SaaS companies spend **4–6 hours every month** manually:
- Pulling revenue data from CRMs and billing systems into spreadsheets
- Calculating ARR, NRR, burn multiple, CAC, and LTV by hand
- Writing variance commentary explaining why actuals missed budget
- Building waterfall charts and KPI slides for leadership

**This project automates that entire workflow** — upload three CSVs, get a fully interactive MBR dashboard with auto-generated insights in under 60 seconds.

---

## 🖥️ Live Demo

👉 **[View the live dashboard →](https://your-name-fpna-command-center.streamlit.app)**

Uses Zenvora Technologies — a synthetic Indian B2B SaaS company (FY 2024, INR) with realistic revenue, budget, and expense data.

---

## ✨ Features

| Feature | What it does |
|---|---|
| **KPI Dashboard** | ARR, MRR, NRR, burn multiple, CAC, LTV:CAC — all in one view |
| **Waterfall Bridge Chart** | Visualises budget → actual ARR movement by driver |
| **Variance Analysis Engine** | Decomposes misses into new business, expansion, and churn |
| **Auto-Generated Insights** | Rule-based NLG produces CFO-ready MBR commentary |
| **Segment Drill-Down** | Enterprise / Mid-Market / SMB performance with region heatmap |
| **Scenario Simulator** | Adjust hiring, marketing, churn — see runway impact in real time |
| **Universal CSV Upload** | Works with any company's data — auto-maps 50+ column name variants |

---

## 🏗️ Architecture

```
Raw CSVs (revenue, budget, expenses)
        │
        ▼
┌─────────────────────────────┐
│   Pipeline Layer            │
│   data_loader.py            │  Schema validation at ingestion
│   cleaner.py                │  Normalize, merge, add time dims
│   metrics.py                │  Compute 12 SaaS KPIs → SQLite
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│   Analytics Layer           │
│   variance.py               │  Budget vs actual decomposition
│   insights.py               │  Rule-based NLG commentary engine
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│   Dashboard Layer           │
│   app.py (Streamlit)        │  5-page interactive dashboard
│   uploader.py               │  Universal CSV ingestion
└─────────────────────────────┘
```

---

## 📐 SaaS Metrics Computed

| Metric | Formula | Why It Matters |
|---|---|---|
| **ARR** | Ending MRR × 12 | Annualised revenue benchmark |
| **Net New ARR** | New + Expansion − Churn | Monthly growth heartbeat |
| **NRR** | (Begin + Expansion − Churn) / Begin | Customer base health |
| **Gross Churn Rate** | Churned ARR / Beginning ARR | Retention signal |
| **Burn Multiple** | Net Burn / Net New ARR | Capital efficiency |
| **CAC** | GTM Spend / New Customers | Acquisition cost |
| **LTV** | ARPU / Monthly Churn Rate | Customer lifetime value |
| **LTV:CAC** | LTV / CAC | Unit economics ratio |
| **Runway** | Cash Remaining / Avg Monthly Burn | Months of operation left |

---

## 🚀 Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-username/fpna-command-center.git
cd fpna-command-center
pip install -r requirements.txt
```

### 2. Generate demo data

```bash
python generate_data.py
```

### 3. Run the dashboard

```bash
streamlit run dashboard/app.py
```

Opens at `http://localhost:8501`

### 4. Use your own company's data

Click **"📂 Upload Data"** in the sidebar. Upload your revenue, budget, and expenses CSVs — column names are auto-mapped. Download blank templates if needed.

---

## 📁 Project Structure

```
fpna-command-center/
│
├── data/
│   ├── raw/                    # Input CSVs
│   │   ├── revenue.csv         # ARR by region × segment × month
│   │   ├── budget.csv          # Planned targets
│   │   └── expenses.csv        # Monthly opex breakdown
│   └── processed/
│       └── fpna.db             # SQLite — pre-computed KPI tables
│
├── pipeline/
│   ├── data_loader.py          # Ingest & schema validation
│   ├── cleaner.py              # Normalize, merge, derive columns
│   └── metrics.py             # Compute all KPIs, write to SQLite
│
├── analytics/
│   ├── variance.py             # Budget vs actual decomposition
│   └── insights.py            # NLG rule engine → MBR commentary
│
├── dashboard/
│   ├── app.py                  # Streamlit entry point (5 pages)
│   └── uploader.py            # Universal CSV ingestion
│
├── generate_data.py            # Synthetic Zenvora dataset (INR)
├── requirements.txt
└── README.md
```

---

## 📤 Uploading Your Own Data

The dashboard accepts any company's CSV files. Column names are **automatically mapped** — you don't need to rename your spreadsheets.

### Supported column name variants (examples)

| Standard name | Also recognised as |
|---|---|
| `ending_arr` | `arr_total`, `arr_end`, `closing_arr`, `total_arr` |
| `region` | `territory`, `geography`, `geo`, `market`, `area` |
| `segment` | `plan`, `tier`, `customer_tier`, `product_tier` |
| `expansion_arr` | `upsell`, `upsell_arr`, `seat_expansion` |
| `budgeted_ending_arr` | `plan_arr`, `target_arr`, `arr_target`, `budget_arr` |

### Columns that are auto-derived if missing

- `mrr` ← `ending_arr ÷ 12`
- `net_new_arr` ← `new_arr + expansion_arr − churned_arr`
- `beginning_arr` ← `ending_arr − net_new_arr`
- `total_opex` ← sum of all expense category columns

---

## 💡 Insights Engine

The auto-commentary system (`insights.py`) is a **deterministic rule engine** — not an LLM.

Every sentence traces back to a named threshold:

```python
THRESHOLDS = {
    "arr_var_moderate":  0.08,   # 8%  miss → warrants explanation
    "nrr_warning":       0.97,   # <97% NRR → retention risk flag
    "burn_acceptable":   1.50,   # >1.5× burn → efficiency warning
    "ltv_cac_strong":    5.0,    # >5× → healthy unit economics
}
```

This makes the output **auditable** — a CFO can trace every flag back to the condition that triggered it.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Data processing | Python, Pandas, NumPy |
| Storage | SQLite (via `sqlite3`) |
| Visualisation | Plotly (waterfall, line, bar, heatmap) |
| Dashboard | Streamlit |
| Deployment | Streamlit Cloud (free tier) |

---

## 📦 Requirements

```
streamlit>=1.32.0
pandas>=2.0.0
numpy>=1.26.0
plotly>=5.20.0
```

---

## 🎓 What I Learned

- How FP&A teams structure MBR reporting workflows
- SaaS-specific metrics and what each signals about business health
- Building ETL pipelines with validation, cleaning, and derived metrics
- Designing rule-based NLG systems that produce auditable outputs
- Streamlit session state for multi-page apps with dynamic data

---

## 📄 License

MIT — use freely, attribution appreciated.
