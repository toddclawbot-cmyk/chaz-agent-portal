# Chaz Agent Portal — Technical Architecture

## 1. Overview

The Chaz Agent Portal is a real-time AI agent web application that connects live operational data (Databricks), CRM automation (Salesforce), and natural language intelligence (Groq LLM) into a single unified interface. It was built to demonstrate how AI agents can work across enterprise systems in real-time — not a static demo, but a fully operational application handling live queries, creating CRM records, and sending real emails.

The portal is built for a B2B bakery wholesale scenario: Chaz Bakery managing supply chain risk for its Café Lumière account. When inventory risk is detected, the agent autonomously creates a Salesforce Case and drafts a customer outreach email — all streamed live to the browser in real-time.

---

## 2. System Architecture

### Component Overview

```
                         ┌─────────────────────────────────┐
                         │         Flask Web App           │
                         │    http://192.168.1.13:5050    │
                         │                                 │
                         │  ┌─────────────┐  ┌──────────┐ │
                         │  │  Inventory  │  │  General │ │
                         │  │   Agent     │  │  Agent   │ │
                         │  │ (hardcoded) │  │  (LLM)   │ │
                         │  └──────┬──────┘  └────┬────┘ │
                         │         │              │       │
                         └─────────┼──────────────┼───────┘
                                   │              │
                    ┌──────────────┴──┐    ┌──────┴──────┐
                    │   Databricks     │    │  Groq LLM   │
                    │ chazbakedgoods. │    │   llama     │
                    │  sales.* (9 tbl) │    │ -3.3-70b   │
                    └─────────────────┘    └─────────────┘
                                   │
                    ┌──────────────┴──────────────────┐
                    │                                  │
              ┌─────┴──────┐               ┌──────────┴───┐
              │ Salesforce  │               │ Apple Mail    │
              │ Cases +     │               │  osascript    │
              │ CaseComments│               │  (Mail.app)  │
              └────────────┘               └──────────────┘
```

### Request Lifecycle

**General Query Flow:**
1. User submits question via POST `/ask`
2. Flask creates a background thread with a task ID
3. Thread: Groq LLM interprets question → generates SQL
4. Thread: Databricks SQL API executes query (with async polling)
5. Thread: Results formatted and placed in task queue
6. SSE stream (`/stream/<task_id>`) delivers events to browser as they fire
7. Final `complete` event delivered with full result payload

**Inventory Risk Flow:**
1. Same POST `/ask` submission
2. Keyword detector routes to `run_inventory_agent` instead
3. 6 sequential steps execute: Databricks inventory query → demand analysis → Salesforce lookup → risk assessment → case creation → email draft
4. Each step emits an SSE event; results stream live to the browser
5. Outreach email card appears in UI; user clicks "Send Email"
6. POST to `/send-email` fires osascript → Mail.app → email sent
7. CaseComment appended to Salesforce case with full transcript

---

## 3. Two Agent Modes

### Mode 1: Inventory Risk Agent (`run_inventory_agent`)

Triggered when the question contains inventory keywords: `["inventory", "stock", "supply", "ingredients", "butter", "flour", "shortage", "low", "looking", "next 3 weeks", "demand"]`

Executes a fixed 6-step pipeline:

| Step | Name | What it does |
|---|---|---|
| 1 | `query_databricks_inventory` | Queries `supplier_inventory` for butter/flour below reorder point |
| 2 | `analyze_databricks_results` | Cross-references `demand_forecast_3week` for 3-week butter demand |
| 3 | `cross_reference_salesforce` | Looks up Account + Opportunity in Salesforce for at-risk customers |
| 4 | `risk_assessment` | Calculates shortage vs. supply, assigns risk level |
| 5 | `create_salesforce_case` | Creates Case in Salesforce linked to the at-risk Account |
| 6 | `draft_outreach` | Generates outreach email from Riley Torres to Taylor Nguyen |

The inventory agent is deliberately a fixed pipeline — it was designed for a specific demo scenario (butter shortage risk for Café Lumière). Each step emits its own SSE event with structured `details` data.

### Mode 2: General Query Agent (`run_general_agent`)

Triggered for everything else. Uses Groq LLM to convert natural language into a live Databricks SQL query, then executes it and streams the results.

```
User: "Which franchise locations have the highest 3-week demand?"
  → Groq LLM interprets intent
  → SELECT query generated against chazbakedgoods.sales.*
  → Databricks executes
  → Results streamed back via SSE
  → Formatted table displayed in browser
```

This mode is fully dynamic — no hardcoded queries, no fixed flows. The LLM handles any question the schema supports.

---

## 4. API Integrations

### Databricks SQL API

**Endpoint:** `POST https://{server}/api/2.0/sql/statements`

**Authentication:** Bearer token (`DATABRICKS_TOKEN`)

**Pattern:** The API is asynchronous — most queries return `PENDING` and require polling.

```python
def db_req(statement: str) -> dict:
    url = f"https://{DATABRICKS_SERVER}/api/2.0/sql/statements"
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"statement": statement, "warehouse_id": DATABRICKS_WAREHOUSE}
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    data = resp.json()

    if data.get("status", {}).get("state") == "SUCCEEDED":
        cols = [c["name"] for c in data["manifest"]["schema"]["columns"]]
        rows = data["result"]["data_array"]
        return {"columns": cols, "rows": rows, "state": "SUCCEEDED"}
    elif data.get("status", {}).get("state") == "PENDING":
        stmt_id = data["statement_id"]
        for _ in range(40):          # poll up to 80 seconds
            time.sleep(2)
            check = requests.get(f"{url}/{stmt_id}", headers=headers, timeout=30)
            result = check.json()
            if result.get("status", {}).get("state") == "SUCCEEDED":
                cols = [c["name"] for c in result["manifest"]["schema"]["columns"]]
                rows = result["result"]["data_array"]
                return {"columns": cols, "rows": rows, "state": "SUCCEEDED"}
            elif result.get("status", {}).get("state") == "FAILED":
                return {"error": result["status"]["error"]["error_message"], "state": "FAILED"}
        return {"error": "Query timed out", "state": "TIMEOUT"}
```

**Database:** `chazbakedgoods.sales` — 9 operational tables

---

### Salesforce REST API

**Base URL:** `https://{SALESFORCE_INSTANCE}/services/data/v66.0`

**Authentication:** Bearer token (`SALESFORCE_TOKEN`)

**Key operations used:**

| Operation | Endpoint | Purpose |
|---|---|---|
| Query accounts | `GET /query?q=SELECT+Id,Name+FROM+Account+...` | Find customer accounts |
| Query opportunities | `GET /query?q=SELECT+...+FROM+Opportunity+WHERE+AccountId=...` | Link opportunity to account |
| Create case | `POST /sobjects/Case` | Create inventory risk case |
| Create comment | `POST /sobjects/CaseComment` | Append email transcript to case |
| Delete cases | `DELETE /sobjects/Case/{id}` | Clean up demo data |

```python
def sf_req(method, path, data=None):
    base = f"https://{SALESFORCE_INSTANCE}/services/data/v66.0"
    headers = {
        "Authorization": f"Bearer {SALESFORCE_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{base}{path}"
    if method == "GET":
        return requests.get(url, headers=headers, timeout=15).json()
    elif method == "POST":
        return requests.post(url, headers=headers, json=data, timeout=15).json()
    elif method == "DELETE":
        return requests.delete(url, headers=headers, timeout=15)
```

---

### Groq LLM API

**Endpoint:** `POST https://api.groq.com/openai/v1/chat/completions`

**Model:** `llama-3.3-70b-versatile`

**Purpose:** Convert natural language questions into Databricks SQL queries

```python
def llm_generate_sql(question: str) -> str:
    schema_lines = "\n".join(f"  {v}" for v in DB_SCHEMA.values())
    prompt = (
        "You are a Databricks SQL expert. Convert the user's question into a single SQL SELECT statement.\n"
        "Database: chazbakedgoods.sales\n"
        "Tables:\n" + schema_lines + "\n"
        "Rules:\n"
        "- Always prefix table names with chazbakedgoods.sales.\n"
        "- For top-N results use ORDER BY column DESC LIMIT N\n"
        "- Do NOT use backticks for identifiers\n"
        "- Return ONLY the SQL query. No markdown.\n\n"
        f"Question: {question}\n"
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
    text = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown fences if LLM returns them
    if text.startswith("```"):
        text = text.split("```")[1].strip().lstrip("sql").lstrip("SQL").strip()
    return text
```

**Temperature 0.1** keeps SQL generation deterministic — important for repeatable demo behavior.

---

## 5. Email Automation — osascript + Apple Mail

**How it works:** The Flask app runs `osascript` via Python's `subprocess` module to command Apple Mail (Messages.app is not used — Mail.app handles email).

**The pattern:**
```python
script = f'''
tell application "Mail"
    set theMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}"}}
    tell theMessage
        make new to recipient at end of to recipients with properties {{address:"{recipient}"}}
        send
    end tell
end tell
'''
result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=30)
```

**Key detail:** Curly braces `{{}}` are used inside the f-string to escape literal braces — osascript's AppleScript syntax requires braces for record literals like `{subject:"...", content:"..."}`.

**After send:** A `CaseComment` is appended to the Salesforce case with the full email transcript — timestamp, recipient, subject, and body. This gives the case a complete audit trail of all outreach.

---

## 6. Real-Time Streaming — Server-Sent Events (SSE)

Flask routes an SSE stream at `/stream/<task_id>`. Each agent step fires an event as it completes:

```python
@app.route("/stream/<task_id>")
def stream(task_id):
    def generate():
        q = tasks[task_id]["queue"]
        while True:
            event = q.get()          # blocks until an event is available
            if event is None:        # None = stream complete
                break
            yield f"data: {json.dumps(event)}\n\n"
        # Send final completion payload
        final_data = {"type": "complete", "result": tasks[task_id]["result"]}
        if tasks[task_id].get("outreach_email"):
            final_data["outreach_email"] = tasks[task_id]["outreach_email"]
        if tasks[task_id].get("case_id"):
            final_data["case_id"] = tasks[task_id]["case_id"]
        yield f"data: {json.dumps(final_data)}\n\n"
    return Response(generate(), mimetype="text/event-stream")
```

**Client-side (JavaScript):**
```javascript
eventSource = new EventSource(`/stream/${taskId}`);
eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.type === 'complete') {
        addMessageToChat('agent', data.result);
        // Show email card if outreach exists
        if (data.outreach_email) showEmailActionCard(data);
        eventSource.close();
    } else {
        addCliEntry(data);   // stream step to CLI log
    }
};
```

**Why SSE and not WebSocket?** SSE is unidirectional — the browser only needs to receive, not send. Simpler implementation, works over HTTP, and is natively supported by all modern browsers. For a chat interface where the client only receives, SSE is the right tool.

---

## 7. Database Schema — `chazbakedgoods.sales`

All 9 tables are real operational data for the Chaz Bakery wholesale business.

### `supplier_inventory`
```
ingredient_id, ingredient_name, category, supplier_name, unit_cost,
unit_size, min_order, lead_days, current_stock, reorder_point,
last_order, organic, gmo_free
```
**Answers:** Which ingredients are below reorder point? Who are our suppliers? What are our lead times?

### `shipping_logistics`
```
shipment_id, order_id, customer_id, customer_name, location_id,
driver_name, vehicle_id, vehicle_type, pickup_time, est_delivery,
actual_delivery, status, on_time, packages, weight_lbs, dist_miles,
duration_mins, zone, temp_f, spoilage
```
**Answers:** Which deliveries are late? Which zones have highest spoilage? Driver performance?

### `demand_forecast_3week`
```
sku, product_name, category, wk1_qty, wk2_qty, wk3_qty, wk4_qty,
wk5_qty, wk6_qty, wk7_qty, total_3week_qty, num_orders, num_customers
```
**Answers:** Which SKUs have highest forecasted demand? Which products are growing?

### `customer_satisfaction`
```
review_id, customer_id, customer_name, customer_type, location_id,
sku, product_name, rating, review_text, review_date, delivery_rating,
freshness_rating, communication_rating, would_reorder, visit_type
```
**Answers:** Which products have the lowest ratings? Which locations have delivery issues?

### `inventory_coverage`
```
sku, product_name, category, total_demand_3week, flour_lbs_needed,
flour_stock_lbs, flour_surplus_deficit, coverage_pct, flour_value_needed, status
```
**Answers:** Do we have enough flour to cover 3-week demand? Which SKUs are at risk?

### `sales_transactions`
```
transaction_id, order_id, customer_id, customer_name, customer_type,
location_id, sku, product_name, category, qty, unit_price, total,
cogs, gross_margin, order_date, delivery_date, days_since_order,
payment_method, order_channel, is_wholesale, notes
```
**Answers:** What are our top products by revenue? Which customers generate most margin?

### `franchise_locations`
```
location_id, location_name, location_type, address, city, state, zip,
lat, lng, opened_date, sq_footage, daily_capacity, has_retail, parking
```
**Answers:** Which cities have our locations? Which franchises have capacity to grow?

### `production_schedule`
```
batch_id, location_id, location_name, sku, product_name, category,
planned_qty, actual_qty, batch_date, shift, staff_hours, flour_lbs,
butter_lbs, eggs_dozen, labor_cost, overhead_cost, yield_pct, waste_pct,
quality_passed, notes
```
**Answers:** What are our yield rates? Where is waste highest? Are we hitting planned quantities?

### `products`
```
sku, product_name, category, unit_price, cost_per_unit
```
**Answers:** What is our full product catalog? Which products have best margin?

---

## 8. Setup and Configuration

### Prerequisites

```bash
# Clone the repo
git clone https://github.com/toddclawbot-cmyk/chaz-agent-portal.git
cd chaz-agent-portal

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with credentials (see below)
```

### Environment Variables

```env
# Databricks — get from Databricks workspace > Settings > Access Tokens
DATABRICKS_TOKEN=your_databricks_token_here
DATABRICKS_SERVER=dbc-7178ded3-3dd3.cloud.databricks.com
DATABRICKS_WAREHOUSE=095b4b50e2976a51

# Salesforce — OAuth web server flow
SALESFORCE_TOKEN=your_salesforce_access_token
SALESFORCE_INSTANCE=orgfarm-23393c2d11-dev-ed.develop.my.salesforce.com

# Groq — free at console.groq.com (llama-3.3-70b-versatile)
GROQ_API_KEY=gsk_QFUYVyejrvB2YsZRV00nWGdyb...
```

### Databricks Setup

1. Log into Databricks workspace
2. Go to **Settings → Access Tokens → Generate New Token**
3. Copy token to `DATABRICKS_TOKEN`
4. **Warehouse ID:** SQL Warehouses → Serverless Starter → copy ID from URL or warehouse details
5. **Server:** Copy from browser URL: `https://{server}.cloud.databricks.com`

### Salesforce OAuth

```bash
# Install sf CLI
npm install -g sf-cli

# Authenticate
sf org login web --alias my-org

# Get access token and instance
sf org display --alias my-org
```

### Groq API Key

1. Go to [console.groq.com](https://console.groq.com)
2. Create account (free tier includes `llama-3.3-70b-versatile`)
3. Create API key and paste into `GROQ_API_KEY`

### Running

```bash
python3 app.py
# → Running on http://0.0.0.0:5050
```

For macOS auto-start, use `start.sh` or set up a launchd service (see Guest Home Interface docs for launchd pattern).

---

## 9. Deployment Considerations

### Secrets Management
**Never commit `.env` to git.** The repo uses `.env.example` as a template. In production, use environment variables or a secrets manager (AWS Secrets Manager, HashiCorp Vault, or Databricks secret scopes).

The GitHub repo has GitHub Push Protection enabled — it will block any push containing detected secrets.

### Databricks Warehouse
The serverless warehouse auto-stops after 10 minutes of inactivity. Cold starts take ~5–10 seconds. Set `wait_until_integrated` in Databricks workspace settings if cold-start latency is a concern for demos.

### Salesforce Token Expiry
Salesforce OAuth access tokens expire. For long-running demos, implement token refresh using the refresh token flow. For a simple demo, re-authenticate with `sf org login web` when API calls start returning 401s.

### Apple Mail Requirement
Email sending requires Mail.app to be running on the host machine. The osascript command sends through the local Mail instance — no SMTP configuration needed. This is a macOS-only approach.

### Flask in Production
The app runs with Flask's built-in dev server (`debug=off`) for simplicity. For production deployment, swap to Gunicorn or uWSGI behind a reverse proxy (nginx):

```bash
gunicorn -w 4 -b 0.0.0.0:5050 app:app
```

### Scaling
The current architecture is single-process with background threads per request. For multi-user scaling:
- Move agent execution to a task queue (Celery, RQ)
- Use Redis for shared task state across workers
- Add WebSocket support for true bidirectional communication

For a demo tool, the current single-server design is sufficient and keeps complexity low.

---

## 10. Project Structure

```
chaz-agent-portal/
├── app.py                  # Flask app, all routes, agent logic, API clients
├── requirements.txt        # pip install -r requirements.txt
├── start.sh                # macOS launch script
├── .env.example             # Credential template (safe to commit)
├── .gitignore               # Ignores .env
├── templates/
│   └── index.html          # Full web UI (HTML/CSS/JS + SSE client)
└── docs/
    └── ARCHITECTURE.md     # This document
```
