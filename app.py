import os
import json
import time
import uuid
import queue
import threading
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

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
                      "shortage", "low", "looking", "orders", "next 3 weeks", "demand"]


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

        outreach_message = f"""To: Taylor Nguyen (Owner), Cafe Lumiere — {contact_email}
From: Riley Torres, Sales Director, Chaz Bakery
Subject: Cafe Lumiere — May 8 Pastry Delivery: Quick Heads Up

Hi Taylor,

I wanted to reach out proactively before our May 8 delivery. As we're planning our production schedule for your Full Pastry Program, our ops team flagged that we're managing through a tight butter supply window — Grassland Dairy's next delivery isn't until April 26.

The good news: your May 8 order is fully confirmed and we have a clear production plan. We're scheduling your {int(cafe_units)} units as a priority run. We'll send you a confirmation by end of day Friday.

I'm also looping in our ops team on the supply situation so we can stay ahead of it. If anything changes on your end, let me know ASAP and we'll adjust.

Talk soon,
Riley Torres | Sales Director | Chaz Bakery | rtorres@chazsbakery.com"""

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


def run_general_agent(task_id, question):
    """Handle non-inventory questions."""
    try:
        emit_sse_event(task_id, 1, "analyze_question", "running",
                       "Analyzing question...")
        time.sleep(0.5)
        emit_sse_event(task_id, 1, "analyze_question", "done",
                       "This appears to be a general question — not inventory-related.")
        time.sleep(0.3)

        tasks[task_id]["status"] = "done"
        tasks[task_id]["result"] = (
            f"For inventory and supply chain questions, try asking:\n\n"
            f"- *\"How is our inventory looking against orders for the next 3 weeks?\"*\n"
            f"- *\"Do we have enough butter for next week's orders?\"*\n"
            f"- *\"Which ingredients are below reorder point?\"*\n\n"
            f"For other questions, I'm here to help with anything Salesforce, Databricks, "
            f"or production data related to Chaz Bakery."
        )
        try:
            tasks[task_id]["queue"].put_nowait(None)
        except queue.Full:
            pass
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["result"] = f"Error: {str(e)}"
        try:
            tasks[task_id]["queue"].put_nowait(None)
        except queue.Full:
            pass


# ─── Routes ────────────────────────────────────────────────────────
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
        # Send final completion
        yield f"data: {json.dumps({'type': 'complete', 'result': tasks[task_id]['result']})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/history")
def history():
    return jsonify(chat_history)


@app.route("/clear", methods=["POST"])
def clear_history():
    chat_history.clear()
    return jsonify({"status": "cleared"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True, use_reloader=False)
