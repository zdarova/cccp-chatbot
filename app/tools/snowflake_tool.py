"""Snowflake tool - structured queries for customer data and KPIs."""

import os
import logging

_conn = None


def _get_connection():
    """Get Snowflake connection (lazy init)."""
    global _conn
    if _conn is None:
        try:
            import snowflake.connector
            _conn = snowflake.connector.connect(
                account=os.environ.get("SNOWFLAKE_ACCOUNT", ""),
                user=os.environ.get("SNOWFLAKE_USER", ""),
                password=os.environ.get("SNOWFLAKE_PASSWORD", ""),
                warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
                database=os.environ.get("SNOWFLAKE_DATABASE", "CCCP"),
                schema=os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
            )
        except Exception as e:
            logging.warning(f"Snowflake connection failed: {e}")
            return None
    return _conn


def get_customer_profile(query: str) -> str:
    """Get customer profile data relevant to the query."""
    conn = _get_connection()
    if conn is None:
        return _mock_customer_data(query)
    try:
        cur = conn.cursor()
        # Extract customer identifier from query (simplified)
        cur.execute("""
            SELECT customer_id, name, segment, lifetime_value, 
                   last_contact_date, total_calls_12m, avg_sentiment
            FROM customer_profiles
            LIMIT 5
        """)
        rows = cur.fetchall()
        if rows:
            cols = [d[0] for d in cur.description]
            return "\n".join(str(dict(zip(cols, row))) for row in rows)
        return "No customer data found"
    except Exception as e:
        logging.warning(f"Snowflake query failed: {e}")
        return _mock_customer_data(query)


def query_kpis(query: str) -> str:
    """Query KPI metrics from Snowflake."""
    conn = _get_connection()
    if conn is None:
        return _mock_kpi_data(query)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT metric_name, metric_value, period, call_centre, 
                   trend, target_value
            FROM kpi_metrics
            WHERE period >= DATEADD(month, -6, CURRENT_DATE())
            ORDER BY period DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        if rows:
            cols = [d[0] for d in cur.description]
            return "\n".join(str(dict(zip(cols, row))) for row in rows)
        return "No KPI data found"
    except Exception as e:
        logging.warning(f"Snowflake KPI query failed: {e}")
        return _mock_kpi_data(query)


def _mock_customer_data(query: str) -> str:
    """Mock data for PoC when Snowflake is not connected."""
    return """
customer_id: C-1234, name: Mario Rossi, segment: Premium, lifetime_value: €45,000
last_contact: 2025-05-10, total_calls_12m: 8, avg_sentiment: -0.2 (declining)
products: Business Line, Internet Pro, Cloud Backup
open_issues: billing dispute (€340), slow internet complaint
propensity_upsell: 0.72 (Security Pack), propensity_churn: 0.35
"""


def _mock_kpi_data(query: str) -> str:
    """Mock KPI data for PoC."""
    return """
NPS (May 2025): 42 (target: 50) — trend: declining (-3 vs prev month)
NPS (Apr 2025): 45 — stable
NPS (Mar 2025): 44 — improving (+2)
Avg Handle Time: 6.2 min (target: 5.5) — trend: increasing
First Call Resolution: 68% (target: 75%) — trend: stable
Customer Satisfaction (CSAT): 3.8/5 (target: 4.2) — declining
Agent Quality Score: 4.1/5 — stable
Call Volume: 12,400/month — increasing (+8% MoM)
Top complaint: billing issues (34%), service speed (22%), contract terms (18%)
"""
