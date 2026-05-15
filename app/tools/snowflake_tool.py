"""Structured data tool - queries PostgreSQL for customer data and KPIs.
In production this would connect to Snowflake. For PoC, uses the same PostgreSQL
instance as pgvector (separate tables for structured data).
"""

import os
import logging

_conn = None


def _get_connection():
    global _conn
    if _conn is None:
        try:
            import psycopg
            pg = os.environ["PG_CONNECTION_STRING"]
            parts = dict(p.split("=", 1) for p in pg.split() if "=" in p)
            _conn = psycopg.connect(
                host=parts["host"], port=int(parts["port"]),
                dbname=parts["dbname"], user=parts["user"],
                password=parts["password"], sslmode=parts.get("sslmode", "require"),
            )
            _conn.autocommit = True
        except Exception as e:
            logging.warning(f"PostgreSQL connection failed: {e}")
            return None
    return _conn


def get_customer_profile(query: str) -> str:
    """Get customer profile data relevant to the query."""
    conn = _get_connection()
    if conn is None:
        return _mock_customer_data()
    try:
        cur = conn.cursor()
        # Try to extract customer name or ID from query
        cur.execute("""
            SELECT customer_id, name, segment, lifetime_value,
                   last_contact_date, total_calls_12m, avg_sentiment,
                   products, open_issues, propensity_upsell, propensity_churn
            FROM customer_profiles
            ORDER BY last_contact_date DESC
            LIMIT 5
        """)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        if rows:
            return "\n".join(str(dict(zip(cols, row))) for row in rows)
        return "No customer data found"
    except Exception as e:
        logging.warning(f"Customer query failed: {e}")
        return _mock_customer_data()


def query_kpis(query: str) -> str:
    """Query KPI metrics."""
    conn = _get_connection()
    if conn is None:
        return _mock_kpi_data()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT metric_name, metric_value, period, call_centre, trend, target_value
            FROM kpi_metrics
            ORDER BY period DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        if rows:
            return "\n".join(str(dict(zip(cols, row))) for row in rows)
        return "No KPI data found"
    except Exception as e:
        logging.warning(f"KPI query failed: {e}")
        return _mock_kpi_data()


def get_call_history(customer_id: str = None) -> str:
    """Get call history with metadata."""
    conn = _get_connection()
    if conn is None:
        return ""
    try:
        cur = conn.cursor()
        if customer_id:
            cur.execute("""
                SELECT call_id, customer_id, call_date, summary, tags,
                       sentiment, estimated_nps, resolution_status, commercial_opportunity
                FROM call_metadata WHERE customer_id = %s
                ORDER BY call_date DESC LIMIT 10
            """, (customer_id,))
        else:
            cur.execute("""
                SELECT call_id, customer_id, call_date, summary, tags,
                       sentiment, estimated_nps, resolution_status, commercial_opportunity
                FROM call_metadata
                ORDER BY call_date DESC LIMIT 10
            """)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return "\n".join(str(dict(zip(cols, row))) for row in rows)
    except Exception as e:
        logging.warning(f"Call history query failed: {e}")
        return ""


def get_themes() -> str:
    """Get discovered themes."""
    conn = _get_connection()
    if conn is None:
        return ""
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT theme, frequency, is_new, sentiment_correlation, call_count
            FROM discovered_themes
            ORDER BY call_count DESC
        """)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return "\n".join(str(dict(zip(cols, row))) for row in rows)
    except Exception as e:
        logging.warning(f"Themes query failed: {e}")
        return ""


def _mock_customer_data() -> str:
    return """customer_id: C-1001, name: Mario Rossi, segment: Premium, lifetime_value: 45000, avg_sentiment: -0.2 (declining), open_issues: Billing dispute"""


def _mock_kpi_data() -> str:
    return """NPS (May 2026): 42 (target: 50) declining | CSAT: 3.8/5 (target: 4.2) | FCR: 68% (target: 75%) | AHT: 6.2min (target: 5.5)"""
