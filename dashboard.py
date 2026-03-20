"""
CLV Executive Dashboard — Room 4 Hackathon
Streamlit app that talks directly to the MCP server's CLV logic.
"""

import streamlit as st
import plotly.graph_objects as go
import psycopg2
import os

st.set_page_config(page_title="CLV Dashboard — Room 4", layout="wide", initial_sidebar_state="collapsed")

# ── DB connection ──

DB_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "postgres"),
    "dbname": os.getenv("PG_DB", "Adventureworks"),
}


@st.cache_resource
def get_conn():
    return psycopg2.connect(**DB_CONFIG)


# ── CLV query (same logic as MCP server) ──

CLV_SQL = """
WITH customer_orders AS (
    SELECT
        h.customerid,
        COUNT(*)                             AS order_count,
        SUM(h.subtotal)::float               AS total_revenue,
        SUM(h.freight)::float                AS total_freight,
        SUM(h.taxamt)::float                 AS total_tax,
        MIN(h.orderdate)                     AS first_order,
        MAX(h.orderdate)                     AS last_order
    FROM sales.salesorderheader h
    GROUP BY h.customerid
),
customer_cost AS (
    SELECT
        h.customerid,
        SUM(d.orderqty * p.standardcost)::float AS total_product_cost
    FROM sales.salesorderheader h
    JOIN sales.salesorderdetail d ON d.salesorderid = h.salesorderid
    JOIN production.product p ON p.productid = d.productid
    GROUP BY h.customerid
)
SELECT
    co.customerid,
    co.order_count,
    co.total_revenue,
    COALESCE(co.total_revenue - COALESCE(cc.total_product_cost, 0), co.total_revenue) AS gross_margin,
    COALESCE(co.total_revenue - COALESCE(cc.total_product_cost, 0) - co.total_freight - co.total_tax, 0) AS net_margin,
    co.total_freight,
    co.total_tax,
    COALESCE(cc.total_product_cost, 0)::float AS total_product_cost,
    co.first_order,
    co.last_order,
    co.order_count::float
        * COALESCE(co.total_revenue - COALESCE(cc.total_product_cost, 0), co.total_revenue) / NULLIF(co.order_count, 0)
        * GREATEST(EXTRACT(EPOCH FROM co.last_order - co.first_order) / 86400.0 / 365.0, 1.0)
        AS predictive_clv
FROM customer_orders co
LEFT JOIN customer_cost cc ON cc.customerid = co.customerid
ORDER BY co.total_revenue DESC
"""


@st.cache_data(ttl=300)
def load_clv_data():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(CLV_SQL)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return rows


# ── Styling ──

st.markdown("""
<style>
    [data-testid="stHeader"] { background: #0F1117; }
    .block-container { padding-top: 1.5rem; }
    .metric-card {
        background: #22252F; border: 1px solid #2E3140; border-radius: 12px;
        padding: 20px; text-align: center;
    }
    .metric-val { font-size: 32px; font-weight: 700; }
    .metric-label { font-size: 12px; color: #9B99A1; text-transform: uppercase; letter-spacing: 0.5px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: #1A1D27; border: 1px solid #2E3140; border-radius: 8px;
        padding: 8px 20px; color: #9B99A1;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(124,110,246,0.08); border-color: #7C6EF6; color: #7C6EF6;
    }
</style>
""", unsafe_allow_html=True)


# ── Load data ──

try:
    data = load_clv_data()
except Exception as e:
    st.error(f"Cannot connect to database: {e}")
    st.stop()

METHOD_KEYS = {
    "Revenue": "total_revenue",
    "Gross Margin": "gross_margin",
    "Net Margin": "net_margin",
    "Predictive": "predictive_clv",
}
METHOD_COLORS = {
    "Revenue": "#F0997B",
    "Gross Margin": "#7C6EF6",
    "Net Margin": "#5DCAA5",
    "Predictive": "#85B7EB",
}

# ── Header ──

st.markdown("#### Room 4 — CLV Analytics")
st.markdown("# Customer Lifetime Value — Executive View")
st.caption("One dashboard that replaces the 40. Toggle methods, drill into divergence.")

# ── Method selector ──

method = st.radio(
    "CLV Method:",
    list(METHOD_KEYS.keys()),
    horizontal=True,
    index=1,
)
key = METHOD_KEYS[method]
color = METHOD_COLORS[method]

# ── Summary metrics ──

total_clv = sum(r[key] or 0 for r in data)
total_customers = len(data)
avg_clv = total_clv / total_customers if total_customers else 0
customers_with_orders = sum(1 for r in data if r["order_count"] > 0)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total CLV", f"${total_clv:,.0f}")
c2.metric("Customers", f"{customers_with_orders:,}")
c3.metric("Avg CLV", f"${avg_clv:,.0f}")
c4.metric("Repeat Buyers", f"{sum(1 for r in data if r['order_count'] > 1):,}")

st.divider()

# ── Charts row ──

col_bar, col_table = st.columns([1, 1])

# Bar chart: Top 10 customers
with col_bar:
    st.markdown("##### Top 10 Customers by " + method)
    top10 = sorted(data, key=lambda r: r[key] or 0, reverse=True)[:10]
    fig = go.Figure(go.Bar(
        x=[f"C-{r['customerid']}" for r in top10],
        y=[r[key] or 0 for r in top10],
        marker_color=color,
        text=[f"${(r[key] or 0):,.0f}" for r in top10],
        textposition="outside",
    ))
    fig.update_layout(
        plot_bgcolor="#0F1117", paper_bgcolor="#0F1117",
        font_color="#E8E6E1", height=400,
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#2E3140", title="CLV ($)"),
    )
    st.plotly_chart(fig, use_container_width=True)

# Reconciliation table: highest divergence
with col_table:
    st.markdown("##### CLV Reconciliation — Highest Divergence")

    recon_rows = []
    for r in data:
        rev = r["total_revenue"] or 0
        gm = r["gross_margin"] or 0
        net = r["net_margin"] or 0
        pred = r["predictive_clv"] or 0
        vals = [rev, gm, net, pred]
        spread = max(vals) - min(vals) if vals else 0

        cost_gap = rev - gm
        freight_gap = gm - net
        pred_gap = abs(pred - gm)
        if spread < rev * 0.15:
            driver = "Aligned"
        elif pred_gap > cost_gap and pred_gap > freight_gap:
            driver = "Repeat buyer"
        elif cost_gap > freight_gap:
            driver = "High-cost SKUs"
        else:
            driver = "High freight"
        if net < 0:
            driver = "Negative net"

        recon_rows.append({
            "Customer": f"C-{r['customerid']}",
            "Revenue": f"${rev:,.0f}",
            "Gross": f"${gm:,.0f}",
            "Net": f"${net:,.0f}",
            "Predictive": f"${pred:,.0f}",
            "Spread": spread,
            "Driver": driver,
        })

    recon_rows.sort(key=lambda x: x["Spread"], reverse=True)
    display_rows = recon_rows[:10]

    import pandas as pd
    df = pd.DataFrame(display_rows)
    df["Spread"] = df["Spread"].apply(lambda x: f"${x:,.0f}")
    st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

# ── What-If Simulator ──

st.markdown("##### What-If Simulator")
st.caption("Simulate how freight or cost reductions change CLV for a specific customer.")

wif_cols = st.columns([1, 1, 1, 2])
with wif_cols[0]:
    top_ids = [r["customerid"] for r in sorted(data, key=lambda r: r["total_revenue"] or 0, reverse=True)[:50]]
    selected_customer = st.selectbox("Customer", top_ids, format_func=lambda x: f"C-{x}")
with wif_cols[1]:
    freight_red = st.slider("Freight reduction %", 0, 100, 20)
with wif_cols[2]:
    cost_red = st.slider("Cost reduction %", 0, 100, 10)

cust_data = next((r for r in data if r["customerid"] == selected_customer), None)
if cust_data:
    with wif_cols[3]:
        orig_net = cust_data["net_margin"] or 0
        new_freight = (cust_data["total_freight"] or 0) * (1 - freight_red / 100)
        new_cost = (cust_data["total_product_cost"] or 0) * (1 - cost_red / 100)
        new_gross = (cust_data["total_revenue"] or 0) - new_cost
        new_net = new_gross - new_freight - (cust_data["total_tax"] or 0)
        delta = new_net - orig_net

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Original Net CLV", f"${orig_net:,.0f}")
        mc2.metric("Simulated Net CLV", f"${new_net:,.0f}")
        mc3.metric("Delta", f"${delta:+,.0f}", delta=f"{delta:+,.0f}")

st.divider()

# ── Footer ──

st.markdown("""
<div style="text-align:center; color:#9B99A1; font-size:12px; padding:16px;">
    Room 4 — CLV Analytics | MCP + Streamlit + PostgreSQL (AdventureWorks)
    <br>Francesco, Maximo, Raman, Esther, Patcharee
</div>
""", unsafe_allow_html=True)
