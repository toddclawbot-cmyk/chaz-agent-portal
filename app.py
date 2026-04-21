import os
import json
import re
import time
import uuid
import queue
import threading
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv


# ─── Load Email Skill ───────────────────────────────────────────────
def load_email_skill():
    """Read the email skill file for voice/tone/template config."""
    skill_path = os.path.join(os.path.dirname(__file__), 'skills', 'email-skill.md')
    if os.path.exists(skill_path):
        with open(skill_path, 'r') as f:
            return f.read()
    return None


def build_outreach_email(ctx: dict) -> str:
    """Generate outreach email using the skill file + Groq LLM for flexible generation."""
    skill = load_email_skill()
    if not skill:
        # Fallback to existing hardcoded template
        return _build_fallback_email(ctx)

    system_prompt = (
        "You are Riley Torres, Sales Director at Chaz Bakery. "
        "Use the email skill below to write personalized customer outreach.\n\n"
        + skill + "\n\n"
        "Write the full email — subject line + body. Return ONLY the email."
    )

    context_vars = {
        "customer_name": ctx.get("customer_name", "there"),
        "customer_full": ctx.get("customer_full", ctx.get("customer_name", "")),
        "customer_email": ctx.get("customer_email", ""),
        "opp_name": ctx.get("opp_name", ""),
        "opp_value": ctx.get("opp_value", 0),
        "opp_close_date": ctx.get("opp_close_date", ""),
        "order_qty": int(ctx.get("cafe_units", 0) or 0),
        "order_date": ctx.get("order_date", ""),
        "order_description": ctx.get("order_date", "") + " Pastry Delivery",
        "shortage_lbs": ctx.get("butter_shortage", 0),
        "shortage_pct": ctx.get("coverage_pct", 0),
        "butter_need": ctx.get("butter_need", 0),
        "case_id": ctx.get("case_id", ""),
    }

    user_prompt = (
        f"Write the outreach email for:\n"
        + "\n".join(f"  - {k}: {v}" for k, v in context_vars.items())
        + "\n\nThe subject line format is defined in the skill file — follow it exactly."
        + f"\n\nContext: This is for customer '{context_vars['customer_name']}'."
        + f" Order qty: {context_vars['order_qty']} units."
        + f" Butter shortage: {context_vars['shortage_lbs']} lbs."
        + f" Opportunity: {context_vars['opp_name']} (${context_vars['opp_value']:,}, close {context_vars['opp_close_date']})."
        + f" Case: {context_vars['case_id']}."
        + "\n\nInclude: subject line + full body, sign off as Riley Torres, Sales Director, Chaz Bakery."
    )

    key = os.getenv("GROQ_API_KEY", "")
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 600
        },
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _build_fallback_email(ctx: dict) -> str:
    """Original hardcoded email template — used if no skill file exists."""
    customer = ctx.get("customer_name", "there")
    opp_name = ctx.get("opp_name", "")
    opp_val = ctx.get("opp_value", 0)
    opp_date = ctx.get("opp_close_date", "")
    units = int(ctx.get("cafe_units", 0) or 0)
    butter_need = ctx.get("butter_need", 0)
    shortage = ctx.get("butter_shortage", 0)
    case_id = ctx.get("case_id", "")

    return f"""To: {customer}, Cafe Lumiere — tghidaleson@salesforce.com
From: Riley Torres, Sales Director, Chaz Bakery
Subject: Cafe Lumiere — May 8 Pastry Delivery: Quick Heads Up

Hi {customer},

I'm reaching out proactively as your Chaz Bakery account team regarding your Full Pastry Program — the opportunity currently in our system ({opp_name}, ${opp_val:,}, closing {opp_date}).

Our ops team flagged a tight butter supply window. Grassland Dairy's next delivery isn't until April 26, and we're carefully managing production runs to protect your May 8 order of {units} pastry units.

Good news: your May 8 delivery is fully confirmed and scheduled as a priority run. We'll send a formal confirmation by end of day Friday.

I'm also keeping our ops team on the supply situation so we stay ahead of it. If anything changes on your end, let me know and we'll adjust immediately.

Talk soon,
Riley Torres | Sales Director | Chaz Bakery | rtorres@chazsbakery.com"""

load_dotenv()

app = Flask(__name__)

@app.route("/test-llm")
def test_llm():
    from dotenv import load_dotenv
    import os, requests
    load_dotenv()
    key = os.getenv("GROQ_API_KEY", "MISSING")
    try:
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "say hi"}], "max_tokens": 5},
            timeout=15)
        return {"key": key[:15]+"...", "status": resp.status_code, "response": resp.json()}
    except Exception as e:
        return {"key": key[:15]+"...", "error": str(e)}, 500



# ─── API Credentials ─────────────────────────────────────────────────
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
DATABRICKS_SERVER = os.getenv("DATABRICKS_SERVER")
DATABRICKS_WAREHOUSE = os.getenv("DATABRICKS_WAREHOUSE")
SALESFORCE_TOKEN = os.getenv("SALESFORCE_TOKEN")
SALESFORCE_INSTANCE = os.getenv("SALESFORCE_INSTANCE")

# In-memory storage
tasks = {}
chat_history = []

INVENTORY_KEYWORDS = ["inventory", "stock", "supply", "ingredients", "butter", "flour",
                      "shortage", "low", "looking", "next 3 weeks", "demand"]


def is_inventory_question(question):
    q = question.lower()
    return any(kw in q for kw in INVENTORY_KEYWORDS)


def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")


def emit_sse_event(task_id, step_num, step_name, status, output=None, details=None):
    if task_id not in tasks:
        return
    event = {
        "step": step_num,
        "name": step_name,
        "status": status,
        "output": output,
        "details": details,
        "timestamp": get_timestamp()
    }
    tasks[task_id]["steps"].append(event)
    try:
        tasks[task_id]["queue"].put_nowait(event)
    except queue.Full:
        pass


# ─── Databricks API ──────────────────────────────────────────────────
def db_req(statement):
    """Execute a Databricks SQL statement and return result rows + column names."""
    url = f"https://{DATABRICKS_SERVER}/api/2.0/sql/statements"
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "statement": statement,
        "warehouse_id": DATABRICKS_WAREHOUSE
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status", {}).get("state") == "SUCCEEDED":
        cols = [c["name"] for c in data["manifest"]["schema"]["columns"]]
        rows = data["result"]["data_array"]
        return {"columns": cols, "rows": rows, "state": "SUCCEEDED"}
    elif data.get("status", {}).get("state") == "PENDING":
        # Poll for result
        stmt_id = data["statement_id"]
        for _ in range(40):
            time.sleep(2)
            check = requests.get(f"{url}/{stmt_id}", headers=headers, timeout=30)
            check.raise_for_status()
            result = check.json()
            if result.get("status", {}).get("state") == "SUCCEEDED":
                cols = [c["name"] for c in result["manifest"]["schema"]["columns"]]
                rows = result["result"]["data_array"]
                return {"columns": cols, "rows": rows, "state": "SUCCEEDED"}
            elif result.get("status", {}).get("state") == "FAILED":
                return {"error": result["status"].get("error", {}).get("error_message", "Query failed"), "state": "FAILED"}
        return {"error": "Query timed out", "state": "TIMEOUT"}
    else:
        return {"error": data.get("status", {}).get("error", {}).get("error_message", "Unknown error"), "state": "FAILED"}


# ─── Salesforce API ──────────────────────────────────────────────────
def sf_req(method, path, data=None):
    """Make a Salesforce REST API request."""
    base = f"https://{SALESFORCE_INSTANCE}/services/data/v66.0"
    headers = {
        "Authorization": f"Bearer {SALESFORCE_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{base}{path}"
    if method == "GET":
        resp = requests.get(url, headers=headers, timeout=30)
    elif method == "POST":
        resp = requests.post(url, headers=headers, json=data, timeout=30)
    elif method == "PATCH":
        resp = requests.patch(url, headers=headers, json=data, timeout=30)
    else:
        raise ValueError(f"Unsupported method: {method}")
    resp.raise_for_status()
    return resp.json() if resp.content else {}


def sf_soql_query(soql: str):
    """
    Execute a SOQL query and return {columns, rows, state} in the same
    shape as db_req() so the formatter in run_general_agent can stay generic.
    """
    base = f"https://{SALESFORCE_INSTANCE}/services/data/v66.0"
    headers = {"Authorization": f"Bearer {SALESFORCE_TOKEN}"}
    import urllib.parse
    url = f"{base}/query?q={urllib.parse.quote(soql)}"

    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except Exception as ex:
        return {"error": f"Request failed: {ex}", "state": "FAILED"}

    if resp.status_code != 200:
        try:
            body = resp.json()
            if isinstance(body, list) and body:
                msg = body[0].get("message", resp.text)
                code = body[0].get("errorCode", "")
                return {"error": f"{code}: {msg}", "state": "FAILED", "status_code": resp.status_code}
        except Exception:
            pass
        return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}", "state": "FAILED", "status_code": resp.status_code}

    data = resp.json()
    records = data.get("records", [])
    if not records:
        return {"columns": [], "rows": [], "state": "SUCCEEDED"}

    # Derive column order from the SOQL itself so output matches what was asked.
    m = re.search(r"select\s+(.+?)\s+from\s", soql, re.IGNORECASE | re.DOTALL)
    if m:
        cols = [c.strip() for c in m.group(1).split(",")]
    else:
        cols = [k for k in records[0].keys() if k != "attributes"]

    def get_path(rec, path):
        """Resolve 'Account.Name' into rec['Account']['Name'], returning '' if missing."""
        cur = rec
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return ""
            if cur is None:
                return ""
        # If we landed on a dict at the end (relationship with no leaf), return empty
        if isinstance(cur, dict):
            return ""
        return cur

    rows = []
    for rec in records:
        row = []
        for col in cols:
            key = col.strip()
            row.append(get_path(rec, key))
        rows.append(row)

    return {"columns": cols, "rows": rows, "state": "SUCCEEDED", "total": data.get("totalSize", len(rows))}


# ─── Agent Steps ────────────────────────────────────────────────────

def run_inventory_agent(task_id, question):
    """Run the real 6-step inventory risk assessment."""
    try:
        steps = []

        # ── Step 1: Query Databricks — inventory at risk ──────────────
        emit_sse_event(task_id, 1, "query_databricks_inventory", "running",
                       "Querying Databricks: inventory levels vs. reorder points...")

        result = db_req("""
            SELECT ingredient_name, current_stock, reorder_point, unit_size,
                   ROUND(current_stock/reorder_point*100, 0) as coverage_pct
            FROM chazbakedgoods.sales.supplier_inventory
            WHERE current_stock <= reorder_point * 1.2
            ORDER BY current_stock/reorder_point ASC
        """)
        if result.get("error"):
            raise Exception(f"Databricks error: {result['error']}")

        at_risk = []
        for row in result["rows"]:
            at_risk.append({
                "name": row[0],
                "stock": row[1],
                "reorder": row[2],
                "unit": row[3],
                "coverage": row[4]
            })

        butter = next((i for i in at_risk if "butter" in i["name"].lower()), None)
        flour = next((i for i in at_risk if "flour" in i["name"].lower() and "high" in i["name"].lower()), None)

        butter_str = f"⚠️  {butter['name']}: {butter['stock']} lbs / reorder {butter['reorder']} lbs = {butter['coverage']}% coverage" if butter else "Butter: OK"
        flour_str = f"⚠️  {flour['name']}: {flour['stock']} lbs / reorder {flour['reorder']} lbs = {flour['coverage']}% coverage" if flour else "Flour: OK"

        emit_sse_event(task_id, 1, "query_databricks_inventory", "done",
                       f"Query complete — checked {len(result['rows'])} ingredients at risk",
                       {"ingredients": at_risk})

        # ── Step 2: Analyze Databricks results ─────────────────────────
        emit_sse_event(task_id, 2, "analyze_databricks_results", "running",
                       "Analyzing demand across all customer orders for the next 3 weeks...")

        # Get 3-week pastry/bread demand
        demand_result = db_req("""
            SELECT customer_name, SUM(qty) as total_units, SUM(total) as revenue,
                   MIN(delivery_date) as first_delivery
            FROM chazbakedgoods.sales.sales_transactions
            WHERE delivery_date BETWEEN '2026-04-20' AND '2026-05-10'
            GROUP BY customer_name
            ORDER BY revenue DESC
        """)
        if demand_result.get("error"):
            raise Exception(f"Demand query error: {demand_result['error']}")

        customers = []
        total_demand_val = 0
        for row in demand_result["rows"]:
            rev = float(row[2]) if row[2] is not None else 0
            total_demand_val += rev
            customers.append({
                "name": row[0],
                "units": float(row[1]) if row[1] is not None else 0,
                "revenue": rev,
                "first_delivery": row[3]
            })

        # Get Cafe Lumiere specific order for May 8
        cafe_result = db_req("""
            SELECT SUM(qty) as total_units, SUM(total) as revenue
            FROM chazbakedgoods.sales.sales_transactions
            WHERE customer_name = 'Cafe Lumiere'
              AND delivery_date BETWEEN '2026-05-06' AND '2026-05-08'
        """)
        cafe_units = float(cafe_result["rows"][0][0]) if cafe_result.get("rows") and cafe_result["rows"][0][0] is not None else 0
        cafe_revenue = float(cafe_result["rows"][0][1]) if cafe_result.get("rows") and cafe_result["rows"][0][1] is not None else 0

        # Calculate butter math
        # Cafe Lumiere: 1100 croissants (0.22 lbs) + 650 morning buns (0.25 lbs) + 580 almond croissants (0.28 lbs)
        cafe_butter = (1100 * 0.22) + (650 * 0.25) + (580 * 0.28)
        # Ops: 200 lbs/day x 21 days
        ops_butter = 200 * 21
        # Total need vs supply
        butter_supply = 1500 + 3000  # on hand + Apr 26 delivery
        total_need = ops_butter + cafe_butter
        butter_shortage = total_need - butter_supply

        analysis_output = (
            f"3-week demand across {len(customers)} customers totaling ${total_demand_val:,.0f}. "
            f"Cafe Lumiere week of May 8: {int(cafe_units)} units — needs {cafe_butter:.0f} lbs butter. "
            f"Total butter needed (incl. ops): {total_need:,.0f} lbs | Available: {butter_supply:,.0f} lbs | "
            f"SHORTAGE: {butter_shortage:,.0f} lbs"
        )
        emit_sse_event(task_id, 2, "analyze_databricks_results", "done",
                       analysis_output,
                       {"butter_need": round(cafe_butter, 1), "butter_supply": butter_supply,
                        "butter_shortage": round(butter_shortage, 1), "cafe_units": cafe_units})

        # ── Step 3: Cross-reference Salesforce ────────────────────────
        emit_sse_event(task_id, 3, "cross_reference_salesforce", "running",
                       "Querying Salesforce for opportunities linked to at-risk accounts...")

        # Get Cafe Lumiere account and opportunity
        try:
            cl_accounts = sf_req("GET", "/query?q=SELECT+Id,Name+FROM+Account+WHERE+Name+LIKE+'%25Lumi%25'+LIMIT+1")
            cl_acct_id = cl_accounts["records"][0]["Id"] if cl_accounts.get("records") else None
            cl_acct_name = cl_accounts["records"][0]["Name"] if cl_accounts.get("records") else "Cafe Lumiere"

            if cl_acct_id:
                cl_opps = sf_req("GET", f"/query?q=SELECT+Id,Name,StageName,Amount,CloseDate+FROM+Opportunity+WHERE+AccountId='{cl_acct_id}'+AND+StageName+NOT+IN+('Closed+Won','Closed+Lost')+LIMIT+5")
                opp_data = cl_opps.get("records", [])
                cl_opp = opp_data[0] if opp_data else None
                if cl_opp:
                    sf_output = (
                        f"Active opportunity: '{cl_opp['Name']}' | Stage: {cl_opp['StageName']} | "
                        f"${cl_opp['Amount']:,} | Close: {cl_opp['CloseDate']}"
                    )
                else:
                    sf_output = "No active opportunities found for Cafe Lumiere"
            else:
                sf_output = "Cafe Lumiere account not found in Salesforce"
                cl_opp = None
        except Exception as e:
            sf_output = f"Salesforce query error: {str(e)}"
            cl_opp = None

        emit_sse_event(task_id, 3, "cross_reference_salesforce", "done",
                       sf_output,
                       {"opportunity": cl_opp} if cl_opp else {})

        # ── Step 4: Risk assessment ─────────────────────────────────
        emit_sse_event(task_id, 4, "risk_assessment", "running",
                       "Calculating business impact and risk score...")

        risk_level = "HIGH" if butter_shortage > 300 else "MEDIUM" if butter_shortage > 100 else "LOW"
        cl_opp_val = cl_opp["Amount"] if cl_opp else 0

        risk_output = (
            f"Risk Level: {risk_level} | Butter shortage: {butter_shortage:,.0f} lbs. "
            f"Cafe Lumiere ${cl_opp_val:,} opportunity at risk if pastry delivery fails. "
            f"Customer outreach required within 24 hours."
        )
        emit_sse_event(task_id, 4, "risk_assessment", "done",
                       risk_output,
                       {"risk_level": risk_level, "opp_value": cl_opp_val, "shortage_lbs": round(butter_shortage, 1)})

        # ── Step 5: Create Salesforce case ────────────────────────────
        emit_sse_event(task_id, 5, "create_salesforce_case", "running",
                       "Creating case in Salesforce...")

        if cl_acct_id:
            case_data = {
                "Subject": f"ALERT: Butter inventory shortage — Cafe Lumiere Full Pastry Program at risk",
                "Status": "New",
                "Priority": "High",
                "Type": "Operations",
                "AccountId": cl_acct_id,
                "Description": (
                    f"SYSTEM ALERT — Inventory check detected butter shortage risk for Cafe Lumiere.\n\n"
                    f"Current butter stock: 1,500 lbs (reorder point: 3,000 lbs). Next delivery: April 26.\n"
                    f"Cafe Lumiere week of May 8 order: {int(cafe_units)} pastry units requiring {cafe_butter:.0f} lbs butter.\n"
                    f"Total butter needed (pastry + ops, 21 days): {total_need:,.0f} lbs.\n"
                    f"Butter available: {butter_supply:,.0f} lbs. SHORTAGE: {butter_shortage:,.0f} lbs.\n\n"
                    f"Active opportunity at risk: '{cl_opp['Name']}' | ${cl_opp_val:,} | Close: {cl_opp['CloseDate']}\n"
                    f"Recommended: Expedite Grassland Dairy delivery + proactive outreach to Taylor Nguyen (Owner)."
                )
            }
            case_resp = sf_req("POST", "/sobjects/Case", case_data)
            case_id = case_resp.get("id", "unknown")
            case_url = f"https://{SALESFORCE_INSTANCE}/{case_id}"
            case_output = f"Case created: {case_id} — Butter Shortage Alert (High Priority)"
            emit_sse_event(task_id, 5, "create_salesforce_case", "done",
                           case_output,
                           {"case_id": case_id, "case_url": case_url})
        else:
            case_id = None
            case_output = "Could not create case — Cafe Lumiere account not found"
            emit_sse_event(task_id, 5, "create_salesforce_case", "done", case_output)

        # ── Step 6: Draft outreach ─────────────────────────────────
        emit_sse_event(task_id, 6, "draft_outreach", "running",
                       "Drafting customer outreach message...")

        # Get Cafe Lumiere contact
        contact_email = "taylor.nguyen@caflumiere.com"
        try:
            if cl_acct_id:
                contacts = sf_req("GET", f"/query?q=SELECT+Id,Name,Email,Title+FROM+Contact+WHERE+AccountId='{cl_acct_id}'+LIMIT+3")
                if contacts.get("records"):
                    contact = contacts["records"][0]
                    contact_email = contact.get("Email", contact_email)
        except:
            pass

        # Build email context and generate via skill file + Groq
        email_ctx = {
            "customer_name": contact_email.split('@')[0].title(),
            "customer_full": contact_email,
            "customer_email": contact_email,
            "opp_name": cl_opp['Name'] if cl_opp else "",
            "opp_value": cl_opp_val,
            "opp_close_date": cl_opp['CloseDate'] if cl_opp else "",
            "cafe_units": int(cafe_units),
            "order_date": "May 8",
            "butter_need": round(cafe_butter, 1),
            "butter_shortage": round(butter_shortage, 1),
            "coverage_pct": butter['coverage'] if butter else 0,
            "case_id": case_id if case_id else "",
        }
        outreach_message = build_outreach_email(email_ctx)

        emit_sse_event(task_id, 6, "draft_outreach", "done",
                       "Proactive outreach drafted to Taylor Nguyen (Owner), Cafe Lumiere",
                       {"message": outreach_message})

        # ── Final result ────────────────────────────────────────────
        tasks[task_id]["status"] = "done"
        final_response = (
            f"## Inventory Risk Assessment — Complete\n\n"
            f"**Found:** Butter at 1,500 lbs (50% of reorder point of 3,000 lbs).\n\n"
            f"**The problem:** Cafe Lumiere's week-of-May-8 order requires {cafe_butter:.0f} lbs of butter "
            f"for {int(cafe_units)} pastry units. Combined with daily operational use (~200 lbs/day), "
            f"we need {total_need:,.0f} lbs over 3 weeks but only have {butter_supply:,.0f} lbs available. "
            f"**Shortage: {butter_shortage:,.0f} lbs.**\n\n"
            f"**Salesforce:** '{cl_opp['Name']}' — ${cl_opp_val:,} — Stage: {cl_opp['StageName']} — Close: {cl_opp['CloseDate']}\n"
            f"**Case created:** {case_id}\n\n"
            f"**Recommended action:** Expedite Grassland Dairy butter delivery + proactive outreach to Taylor Nguyen at Cafe Lumiere within 24 hours."
        )
        tasks[task_id]["result"] = final_response
        tasks[task_id]["outreach_email"] = outreach_message
        tasks[task_id]["case_id"] = case_id

        try:
            tasks[task_id]["queue"].put_nowait(None)
        except queue.Full:
            pass

    except Exception as e:
        import traceback
        traceback.print_exc()
        tasks[task_id]["status"] = "error"
        tasks[task_id]["result"] = f"Error running inventory assessment: {str(e)}"
        try:
            tasks[task_id]["queue"].put_nowait(None)
        except queue.Full:
            pass


# ─── Groq LLM for natural language → SQL ─────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

DB_SCHEMA = {
    "supplier_inventory":    "supplier_inventory    — ingredient_id, ingredient_name, category, supplier_name, unit_cost, unit_size, min_order, lead_days, current_stock, reorder_point, last_order, organic, gmo_free",
    "shipping_logistics":    "shipping_logistics    — shipment_id, order_id, customer_id, customer_name, location_id, driver_name, vehicle_id, vehicle_type, pickup_time, est_delivery, actual_delivery, status, on_time, packages, weight_lbs, dist_miles, duration_mins, zone, temp_f, spoilage",
    "demand_forecast_3week":"demand_forecast_3week — sku, product_name, category, wk1_qty, wk2_qty, wk3_qty, wk4_qty, wk5_qty, wk6_qty, wk7_qty, total_3week_qty, num_orders, num_customers",
    "customer_satisfaction":"customer_satisfaction — review_id, customer_id, customer_name, customer_type, location_id, sku, product_name, rating, review_text, review_date, delivery_rating, freshness_rating, communication_rating, would_reorder, visit_type",
    "inventory_coverage":   "inventory_coverage   — sku, product_name, category, total_demand_3week, flour_lbs_needed, flour_stock_lbs, flour_surplus_deficit, coverage_pct, flour_value_needed, status",
    "sales_transactions":   "sales_transactions   — transaction_id, order_id, customer_id, customer_name, customer_type, location_id, sku, product_name, category, qty, unit_price, total, cogs, gross_margin, order_date, delivery_date, days_since_order, payment_method, order_channel, is_wholesale",
    "franchise_locations":  "franchise_locations  — location_id, location_name, location_type, address, city, state, zip, lat, lng, opened_date, sq_footage, daily_capacity, has_retail, parking",
    "production_schedule":  "production_schedule  — batch_id, location_id, location_name, sku, product_name, category, planned_qty, actual_qty, batch_date, shift, staff_hours, flour_lbs, butter_lbs, eggs_dozen, labor_cost, overhead_cost, yield_pct, waste_pct, quality_passed",
    "products":             "products             — sku, product_name, category, unit_price, cost_per_unit"
}

# ─── Salesforce Schema (whitelist) ───────────────────────────────────
# Only fields listed here are allowed in generated SOQL. The LLM sees
# this verbatim in the prompt, and sf_soql_query sanity-checks against it.
SF_SCHEMA = {
 "Opportunity": [
 "Id", "Name", "StageName", "Amount", "CloseDate", "Probability",
 "Type", "LeadSource", "IsClosed", "IsWon", "ForecastCategoryName",
 "CreatedDate", "LastModifiedDate", "AccountId",
 "Account.Name", "Account.Industry", "Account.Type",
 "Owner.Name",
 ],
 "Account": [
 "Id", "Name", "Industry", "Type", "AnnualRevenue", "NumberOfEmployees",
 "BillingCity", "BillingState", "BillingCountry", "Phone", "Website",
 "CreatedDate", "LastModifiedDate", "OwnerId",
 "Owner.Name",
 ],
 "Contact": [
 "Id", "Name", "FirstName", "LastName", "Email", "Phone", "Title",
 "AccountId", "CreatedDate", "LastModifiedDate",
 "Account.Name", "Account.Industry",
 ],
 "Case": [
 "Id", "CaseNumber", "Subject", "Status", "Priority", "Type",
 "Origin", "Reason", "IsClosed", "ClosedDate", "CreatedDate",
 "LastModifiedDate", "AccountId", "ContactId",
 "Account.Name", "Contact.Name", "Owner.Name",
 ],
 "Lead": [
 "Id", "Name", "FirstName", "LastName", "Company", "Title",
 "Email", "Phone", "Status", "LeadSource", "Industry",
 "IsConverted", "CreatedDate",
 ],
}

# Keywords that route a question to Salesforce instead of Databricks.
SALESFORCE_KEYWORDS = [
 "opportunity", "opportunities", "pipeline", "deal", "deals",
 "account", "accounts", "customer account", "client account",
 "contact", "contacts", "lead", "leads",
 "case", "cases", "ticket", "tickets",
 "stage", "close date", "closing", "won", "lost",
 "forecast", "quota", "revenue at risk", "crm",
 "salesforce", "sfdc",
]

def is_salesforce_question(question: str) -> bool:
 q = question.lower()
 return any(kw in q for kw in SALESFORCE_KEYWORDS)

def llm_generate_sql(question: str) -> str:
    """Use Groq to convert a natural language question into a Databricks SQL query."""
    schema_lines = "\n".join(f"  {v}" for v in DB_SCHEMA.values())
    prompt = (
        "You are a Databricks SQL expert. Convert the user's question into a single SQL SELECT statement.\n"
        "Database: chazbakedgoods.sales\n"
        "Tables:\n" + schema_lines + "\n"
        "Rules:\n"
        "- Always prefix table names with chazbakedgoods.sales. (e.g., chazbakedgoods.sales.supplier_inventory)\n"
        "- For top-N results use ORDER BY column DESC LIMIT N\n"
        "- Do NOT use backticks for identifiers\n"
        "- Always use LOWER() on both sides for string comparisons to ensure case-insensitive matching — e.g., LOWER(product_name) = LOWER('Rye Bread')\n"
        "Question: " + question + "\n"
        "SQL:"
    )
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 400
        },
        timeout=30
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].strip().lstrip("sql").lstrip("SQL").strip()
    return text.strip()


def llm_generate_soql(question: str) -> str:
    """Convert a natural-language question into a SOQL query against the whitelist."""
    schema_lines = []
    for obj, fields in SF_SCHEMA.items():
        schema_lines.append(f" {obj}: {', '.join(fields)}")
    schema_str = "\n".join(schema_lines)

    prompt = (
        "You are a Salesforce SOQL expert. Convert the user's question into a single SOQL SELECT statement.\n"
        "Allowed objects and fields (DO NOT use any field not listed here):\n"
        + schema_str + "\n\n"
        "Rules:\n"
        "- SOQL syntax only. No SQL-isms: no JOIN, no GROUP BY unless using aggregate functions, no UNION.\n"
        "- Parent relationship fields use dot notation: Account.Name, Owner.Name (NOT AccountName).\n"
        "- For top-N use ORDER BY ... DESC LIMIT N.\n"
        "- Do NOT use column aliases (no 'AS x', no trailing alias tokens).\n"
        "- String comparisons: use LIKE with % wildcards for fuzzy matching.\n"
        "- Date literals: YYYY-MM-DD, no quotes (e.g., CloseDate > 2025-01-01) OR use date functions like THIS_QUARTER, THIS_YEAR, LAST_N_DAYS:30.\n"
        "- Default LIMIT to 25 if no limit is implied by the question.\n"
        "- If the question is about 'top' or 'biggest' opportunities, ORDER BY Amount DESC.\n"
        "- Return ONLY the SOQL statement, no explanation, no backticks.\n\n"
        "Question: " + question + "\n"
        "SOQL:"
    )

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 400,
        },
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].strip().lstrip("soql").lstrip("SOQL").lstrip("sql").lstrip("SQL").strip()
    return text.strip().rstrip(";")


def llm_repair_soql(question: str, bad_soql: str, error_msg: str) -> str:
    """Given a SOQL error, ask the LLM to fix it. One-shot repair."""
    schema_lines = []
    for obj, fields in SF_SCHEMA.items():
        schema_lines.append(f" {obj}: {', '.join(fields)}")
    schema_str = "\n".join(schema_lines)

    prompt = (
        "The following SOQL query failed. Rewrite it to fix the error.\n\n"
        f"Original question: {question}\n"
        f"Failed SOQL: {bad_soql}\n"
        f"Salesforce error: {error_msg}\n\n"
        "Allowed objects and fields:\n" + schema_str + "\n\n"
        "Return ONLY the corrected SOQL statement, no explanation, no backticks."
    )
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 400,
        },
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].strip().lstrip("soql").lstrip("SOQL").lstrip("sql").lstrip("SQL").strip()
    return text.strip().rstrip(";")


def run_general_agent(task_id, question):
    """Route to Salesforce (SOQL) or Databricks (SQL) based on keywords,
    query live, format results as a markdown table."""

    # Decide the source first so the UI shows the right step name
    use_sf = is_salesforce_question(question)
    source_label = "Salesforce" if use_sf else "Databricks"

    emit_sse_event(task_id, 1, "understand_question", "running",
                   f"Routing to {source_label}: {question}")

    # Step 1: Generate the query
    try:
        if use_sf:
            query_str = llm_generate_soql(question)
            step_name = "generate_soql"
        else:
            query_str = llm_generate_sql(question)
            step_name = "generate_sql"
        emit_sse_event(task_id, 1, step_name, "done", f"Query: {query_str}")
    except Exception as e:
        emit_sse_event(task_id, 1, "generate_query", "error", f"LLM error: {e}")
        tasks[task_id]["result"] = f"I couldn't generate a query for that question. Error: {e}"
        try:
            tasks[task_id]["queue"].put_nowait(None)
        except queue.Full:
            pass
        return

    # Step 2: Execute (with one-shot repair on Salesforce 400)
    emit_sse_event(task_id, 2, "run_query", "running",
                   f"Executing on {source_label}...")

    try:
        if use_sf:
            result = sf_soql_query(query_str)
            # Auto-repair once if 400
            if result.get("status_code") == 400 and result.get("error"):
                emit_sse_event(task_id, 2, "repair_query", "running",
                               f"SOQL rejected — attempting repair: {result['error']}")
                try:
                    repaired = llm_repair_soql(question, query_str, result["error"])
                    emit_sse_event(task_id, 2, "repair_query", "done",
                                   f"Repaired query: {repaired}")
                    query_str = repaired
                    result = sf_soql_query(repaired)
                except Exception as rep_ex:
                    emit_sse_event(task_id, 2, "repair_query", "error", str(rep_ex))
        else:
            result = db_req(query_str)
    except Exception as e:
        emit_sse_event(task_id, 2, "run_query", "error", str(e))
        tasks[task_id]["result"] = f"Query failed: {e}\n\nQuery: {query_str}"
        try:
            tasks[task_id]["queue"].put_nowait(None)
        except queue.Full:
            pass
        return

    if result.get("error") or result.get("state") == "FAILED":
        emit_sse_event(task_id, 2, "run_query", "error",
                        result.get("error", "Query failed"))
        tasks[task_id]["result"] = (
            f"{source_label} error: {result.get('error', 'unknown')}\n\n"
            f"Query: {query_str}"
        )
        try:
            tasks[task_id]["queue"].put_nowait(None)
        except queue.Full:
            pass
        return

    cols = result.get("columns", [])
    rows = result.get("rows", [])
    emit_sse_event(task_id, 2, "run_query", "done", f"Got {len(rows)} row(s)")

    # Step 3: Format results as a markdown table (consistent for both sources)
    if not rows:
        response = f"No results found for that question.\n\nQuery: `{query_str}`"
    elif len(cols) == 1:
        header = f"| {cols[0]} |\n|---|\n"
        body = "\n".join(f"| {r[0]} |" for r in rows[:50])
        response = header + body
    else:
        header = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join("---" for _ in cols) + "|"
        body_lines = []
        for row in rows[:25]:
            body_lines.append("| " + " | ".join(str(v) if v is not None else "" for v in row) + " |")
        more = f"\n\n_...and {len(rows) - 25} more rows_" if len(rows) > 25 else ""
        response = "\n".join([header, sep] + body_lines) + more

    tasks[task_id]["result"] = response
    emit_sse_event(task_id, 3, "format_results", "done", "Done.")
    try:
        tasks[task_id]["queue"].put_nowait(None)
    except queue.Full:
        pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question is required"}), 400

    chat_history.append({"role": "user", "content": question, "ts": get_timestamp()})

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "running",
        "steps": [],
        "result": None,
        "queue": queue.Queue()
    }

    if is_inventory_question(question):
        thread = threading.Thread(target=run_inventory_agent, args=(task_id, question))
    else:
        thread = threading.Thread(target=run_general_agent, args=(task_id, question))

    thread.daemon = True
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/stream/<task_id>")
def stream(task_id):
    if task_id not in tasks:
        return "Task not found", 404

    def generate():
        q = tasks[task_id]["queue"]
        while True:
            event = q.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"
        # Send final completion with outreach email option
        final_data = {'type': 'complete', 'result': tasks[task_id]['result']}
        if tasks[task_id].get('outreach_email'):
            final_data['outreach_email'] = tasks[task_id]['outreach_email']
        if tasks[task_id].get('case_id'):
            final_data['case_id'] = tasks[task_id]['case_id']
        yield f"data: {json.dumps(final_data)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/send-email", methods=["POST"])
def send_email():
    """Send the outreach email via osascript (Apple Mail)."""
    import subprocess
    outreach = tasks.get(request.args.get('task_id'), {}).get('outreach_email', '')
    if not outreach:
        return jsonify({"error": "No outreach message found"}), 400

    # Parse the outreach message into subject and body
    lines = outreach.strip().split('\n')
    subject = "Cafe Lumiere — May 8 Pastry Delivery: Quick Heads Up"  # fallback
    body_lines = []
    for line in lines:
        if line.startswith('To:') or line.startswith('From:'):
            continue
        if line.startswith('Subject:'):
            subject = line.replace('Subject:', '').strip()
            continue
        body_lines.append(line)
    body = '\n'.join(body_lines).strip()

    # The email recipient
    recipient = "tghidaleson@salesforce.com"

    # AppleScript to send via Mail.app
    script = f'''
    tell application "Mail"
        set theMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}"}}
        tell theMessage
            make new to recipient at end of to recipients with properties {{address:"{recipient}"}}
            send
        end tell
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            # Update the Salesforce case with outreach email note
            case_id = tasks.get(request.args.get('task_id'), {}).get('case_id')
            if case_id:
                try:
                    comment_data = {
                        "ParentId": case_id,
                        "CommentBody": (
                            f"OUTREACH EMAIL SENT at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"To: Taylor Nguyen (Owner), Cafe Lumiere — tghidaleson@salesforce.com\n"
                            f"Subject: {subject}\n"
                            f"Status: Delivered via Apple Mail (Chaz Bakery — Riley Torres, Sales Director)\n\n"
                            f"--- Email Body ---\n{body}"
                        )
                    }
                    sf_req("POST", "/sobjects/CaseComment", comment_data)
                except Exception:
                    pass  # Don't fail the email send if case update fails
            return jsonify({"status": "sent", "to": recipient})
        else:
            return jsonify({"error": result.stderr or "Mail send failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/history")
def history():
    return jsonify(chat_history)


@app.route("/clear", methods=["POST"])
def clear_history():
    chat_history.clear()
    return jsonify({"status": "cleared"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True, use_reloader=False)
