# Chaz Agent Portal

A real-time AI agent web app connecting **Salesforce**, **Databricks**, and **Groq LLM** — demonstrating live operational data + CRM automation for a B2B bakery wholesale business.

Live at **http://192.168.1.13:5050**

---

## What it does

The portal is a Flask web app with a real-time chat interface. You ask questions in plain English and the agent:

1. **Understands the question** — Groq LLM interprets intent
2. **Generates live SQL** — queries `chazbakedgoods.sales` in Databricks in real-time
3. **Streams results via SSE** — data comes back as it's computed
4. **For inventory risk queries** — automatically creates a Salesforce Case and drafts a customer outreach email

---

## Architecture

```
┌─────────────────────────────────────────────┐
│            Chaz Agent Portal               │
│         Flask + SSE streaming               │
│              :5050                          │
└───────────────┬─────────────────────────────┘
                │
        ┌───────┴───────┐
        ▼               ▼
┌──────────────┐  ┌──────────────────┐
│   Groq LLM   │  │   Databricks     │
│  (llama-3.3) │  │ chazbakedgoods.  │
│              │  │ sales.* (9 tbls) │
└──────────────┘  └──────────────────┘
                          │
                ┌─────────┴──────────┐
                ▼                    ▼
        ┌──────────────┐    ┌────────────────┐
        │ Salesforce   │    │  Apple Mail    │
        │ Cases +      │    │  osascript     │
        │ CaseComments │    │  outreach email│
        └──────────────┘    └────────────────┘
```

---

## Data Sources

### Databricks — `chazbakedgoods.sales`

| Table | Description |
|---|---|
| `supplier_inventory` | Ingredient stock, reorder points, suppliers |
| `shipping_logistics` | Delivery tracking, on-time performance |
| `demand_forecast_3week` | 3-week rolling demand by SKU |
| `customer_satisfaction` | Reviews and ratings |
| `inventory_coverage` | Flour coverage % vs. demand |
| `sales_transactions` | Full transaction ledger |
| `franchise_locations` | Location details, capacity |
| `production_schedule` | Batch data, yields, waste |
| `products` | SKU catalog, pricing |

### Salesforce
- **Account:** Café Lumière (`001gK00000oKeseQAC`)
- **Opportunity:** Full Pastry Program — $85,000 (closing May 15)
- **Case** created automatically on inventory shortage

---

## Key Features

### Natural Language → Live SQL
Ask anything about the data:
- *"What are the top 5 products by revenue?"*
- *"Which franchise location has the highest demand for croissants?"*
- *"Show me flour coverage across all SKUs"*

The Groq LLM generates a Databricks SQL query in real-time and streams results back.

### Inventory Risk Automation
When inventory risk is detected:
1. Databricks identifies shortage vs. reorder points
2. Salesforce Case created with account context
3. Outreach email auto-drafted (Riley Torres → Taylor Nguyen)
4. User clicks **Send Email** → Apple Mail fires via osascript
5. CaseComment appended with full email transcript

### Real-time Streaming (SSE)
All query steps stream live to the browser as they happen — no polling, no loading spinners.

---

## Setup

```bash
# 1. Clone
git clone https://github.com/toddclawbot-cmyk/chaz-agent-portal.git
cd chaz-agent-portal

# 2. Install deps
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env with your credentials (see below)

# 4. Run
python3 app.py
# → http://localhost:5050
```

### Environment Variables

```env
DATABRICKS_TOKEN=       # Databricks access token
DATABRICKS_SERVER=      # e.g. dbc-xxxx.cloud.databricks.com
DATABRICKS_WAREHOUSE=   # Warehouse ID
SALESFORCE_TOKEN=       # Salesforce OAuth access token
SALESFORCE_INSTANCE=     # e.g. orgfarm-xxxx.my.salesforce.com
GROQ_API_KEY=           # Groq API key (llama-3.3-70b-versatile)
```

### Salesforce OAuth Setup

```bash
sf org login web --alias my-org
sf org display --alias my-org  # copy access token
```

### Groq API Key

Get a free key at [console.groq.com](https://console.groq.com) — `llama-3.3-70b-versatile` works out of the box.

---

## Project Structure

```
chaz-agent-portal/
├── app.py              # Flask app, all routes, agent logic
├── requirements.txt   # pip deps
├── start.sh           # macOS launch script
├── .env.example       # credential template
├── .gitignore
└── templates/
    └── index.html     # Full web UI + SSE client
```

---

## API Routes

| Route | Method | Description |
|---|---|---|
| `/` | GET | Portal web UI |
| `/ask` | POST | Submit a question → returns task_id |
| `/stream/<task_id>` | GET | SSE stream of agent progress |
| `/send-email` | POST | Send outreach email via Apple Mail |
| `/history` | GET | Chat history |
| `/clear` | POST | Clear chat history |

---

## Tech Stack

- **Flask** — web framework
- **SSE (Server-Sent Events)** — real-time streaming
- **Groq API** — `llama-3.3-70b-versatile` for natural language → SQL
- **Databricks SQL API** — live data queries
- **Salesforce REST API** — CRM case management
- **AppleScript (`osascript`)** — native Mail.app integration for sending emails

---

## Use Cases

| Question | Flow |
|---|---|
| Top products by revenue? | Groq → SQL → Databricks → SSE results |
| Inventory coverage? | Groq → SQL → Databricks → formatted table |
| Butter shortage risk? | Inventory agent → Databricks → Salesforce Case → email |
| Franchise performance? | Groq → SQL → Databricks → ranked results |

---

## Notes

- Apple Mail must be running on the host for email sending (`osascript` via Mail.app)
- Databricks queries use the serverless warehouse with async polling (up to 90s timeout)
- Salesforce tokens expire — re-authenticate with `sf org login web` if API calls fail
