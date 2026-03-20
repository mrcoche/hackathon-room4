"""
MCP Server — CLV Analytics
Room 4 Hackathon: One metric, four methods, zero ambiguity.

Tools:
  get_clv       - Calculate CLV for a customer using a chosen method
  reconcile     - Show all 4 CLV methods side-by-side for a customer
  query_data    - Run read-only SQL against AdventureWorks
  list_customers - List top customers by revenue
  what_if       - Simulate CLV under different freight/cost assumptions
"""

import os
import psycopg2
from mcp.server.fastmcp import FastMCP

DB_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "postgres"),
    "dbname": os.getenv("PG_DB", "Adventureworks"),
}

mcp = FastMCP("CLV Analytics", instructions="Customer Lifetime Value analytics for AdventureWorks data.")


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


# ---------- shared SQL fragments ----------

_BASE_CLV_SQL = """
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
    {where}
    GROUP BY h.customerid
),
customer_cost AS (
    SELECT
        h.customerid,
        SUM(d.orderqty * p.standardcost)::float AS total_product_cost
    FROM sales.salesorderheader h
    JOIN sales.salesorderdetail d ON d.salesorderid = h.salesorderid
    JOIN production.product p ON p.productid = d.productid
    {where}
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
"""


def _compute_clv(customer_id: int | None = None, limit: int = 20):
    where = f"WHERE h.customerid = {int(customer_id)}" if customer_id else ""
    sql = _BASE_CLV_SQL.format(where=where) + " ORDER BY co.total_revenue DESC"
    if not customer_id:
        sql += f" LIMIT {int(limit)}"

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows
    finally:
        conn.close()


# ---------- Tools ----------

@mcp.tool()
def get_clv(customer_id: int, method: str = "gross_margin") -> dict:
    """
    Calculate CLV for a single customer.
    Methods: revenue, gross_margin (default), net_margin, predictive.
    """
    rows = _compute_clv(customer_id)
    if not rows:
        return {"error": f"No orders found for customer {customer_id}"}
    r = rows[0]
    method_map = {
        "revenue": r["total_revenue"],
        "gross_margin": r["gross_margin"],
        "net_margin": r["net_margin"],
        "predictive": r["predictive_clv"],
    }
    value = method_map.get(method, r["gross_margin"])
    return {
        "customer_id": r["customerid"],
        "method": method,
        "clv": round(value, 2) if value else 0,
        "order_count": r["order_count"],
        "first_order": str(r["first_order"].date()) if r["first_order"] else None,
        "last_order": str(r["last_order"].date()) if r["last_order"] else None,
    }


@mcp.tool()
def reconcile(customer_id: int) -> dict:
    """
    Show all 4 CLV methods for a customer side-by-side with the divergence driver.
    """
    rows = _compute_clv(customer_id)
    if not rows:
        return {"error": f"No orders found for customer {customer_id}"}
    r = rows[0]
    revenue = r["total_revenue"] or 0
    gross = r["gross_margin"] or 0
    net = r["net_margin"] or 0
    pred = r["predictive_clv"] or 0
    vals = [revenue, gross, net, pred]
    spread = max(vals) - min(vals) if vals else 0

    # determine primary driver
    cost_gap = revenue - gross
    freight_gap = gross - net
    pred_gap = abs(pred - gross)
    if pred_gap > cost_gap and pred_gap > freight_gap:
        driver = "Repeat-buyer extrapolation"
    elif cost_gap > freight_gap:
        driver = "High product cost"
    else:
        driver = "High freight/tax"
    if spread < revenue * 0.15:
        driver = "Broadly aligned"

    return {
        "customer_id": customer_id,
        "revenue_clv": round(revenue, 2),
        "gross_margin_clv": round(gross, 2),
        "net_margin_clv": round(net, 2),
        "predictive_clv": round(pred, 2),
        "spread": round(spread, 2),
        "primary_driver": driver,
    }


@mcp.tool()
def list_customers(top_n: int = 20, method: str = "gross_margin") -> list[dict]:
    """
    List top customers ranked by a CLV method.
    Methods: revenue, gross_margin, net_margin, predictive.
    """
    rows = _compute_clv(limit=top_n)
    method_key = {
        "revenue": "total_revenue",
        "gross_margin": "gross_margin",
        "net_margin": "net_margin",
        "predictive": "predictive_clv",
    }.get(method, "gross_margin")

    results = []
    for r in rows:
        results.append({
            "customer_id": r["customerid"],
            "clv": round(r[method_key] or 0, 2),
            "order_count": r["order_count"],
        })
    results.sort(key=lambda x: x["clv"], reverse=True)
    return results[:top_n]


@mcp.tool()
def what_if(customer_id: int, freight_reduction_pct: float = 0, cost_reduction_pct: float = 0) -> dict:
    """
    Simulate CLV under different assumptions.
    freight_reduction_pct: reduce freight by this % (0-100).
    cost_reduction_pct: reduce product cost by this % (0-100).
    """
    rows = _compute_clv(customer_id)
    if not rows:
        return {"error": f"No orders found for customer {customer_id}"}
    r = rows[0]
    new_freight = (r["total_freight"] or 0) * (1 - freight_reduction_pct / 100)
    new_cost = (r["total_product_cost"] or 0) * (1 - cost_reduction_pct / 100)
    new_gross = (r["total_revenue"] or 0) - new_cost
    new_net = new_gross - new_freight - (r["total_tax"] or 0)

    return {
        "customer_id": customer_id,
        "scenario": f"-{freight_reduction_pct}% freight, -{cost_reduction_pct}% cost",
        "original_net_clv": round(r["net_margin"] or 0, 2),
        "simulated_net_clv": round(new_net, 2),
        "delta": round(new_net - (r["net_margin"] or 0), 2),
        "original_gross_clv": round(r["gross_margin"] or 0, 2),
        "simulated_gross_clv": round(new_gross, 2),
    }


@mcp.tool()
def query_data(sql: str) -> list[dict]:
    """
    Run a read-only SQL query against AdventureWorks.
    Only SELECT and WITH statements are allowed.
    """
    stripped = sql.strip().upper()
    if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
        return [{"error": "Only SELECT/WITH queries are allowed."}]
    for forbidden in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"]:
        if forbidden in stripped.split("--")[0].split("/*")[0]:
            return [{"error": f"Forbidden keyword: {forbidden}"}]

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()[:500]]
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run()
