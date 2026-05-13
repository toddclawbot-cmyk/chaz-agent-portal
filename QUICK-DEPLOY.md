# 🚀 Quick Deploy — Chaz Agent Portal

## One-Click Blueprint Deploy to Render

**GitHub Repo:** `https://github.com/toddclawbot-cmyk/chaz-agent-portal`
**Render Blueprint:** `https://dashboard.render.com/blueprints`

---

## Step 1 — Deploy via Blueprint (Takes ~2 min)

1. Open: **[dashboard.render.com/blueprints](https://dashboard.render.com/blueprints)**
2. Click **"New Blueprint Instance"**
3. Under "Connect a repository":
   - **Owner:** `toddclawbot-cmyk`
   - **Repository:** `chaz-agent-portal`
4. Click **"Apply"**
5. Render will auto-detect the `render.yaml` and pre-fill:
   - Name: `chaz-agent-portal`
   - Region: Oregon
   - Plan: Free
6. Click **"Create Blueprint"**

---

## Step 2 — Add Your Secrets (Critical!)

After the blueprint deploys (or even before — you can edit env vars anytime):

Go to your service → **Environment** tab. Add these:

### ✅ I Have These (you can copy directly):

| Key | Value |
|-----|-------|
| `DATABRICKS_SERVER` | `dbc-7178ded3-3dd3.cloud.databricks.com` |
| `DATABRICKS_WAREHOUSE` | `095b4b50e2976a51` |
| `SALESFORCE_INSTANCE` | `https://orgfarm-23393c2d11-dev-ed.develop.my.salesforce.com` |

### 🔑 Get These from the Respective Services:

#### `GROQ_API_KEY`
- Log into [console.groq.com](https://console.groq.com)
- Go to **API Keys** → Create or copy existing key

#### `DATABRICKS_TOKEN` ⚠️ REQUIRED for the demo flow
1. Open: `https://dbc-7178ded3-3dd3.cloud.databricks.com`
2. Click avatar → **Settings** → **Developer** → **Access Tokens**
3. Click **"Generate New Token"**
4. Give it a name (e.g. "Chaz Agent Portal")
5. Copy the token string and paste into Render

#### `SALESFORCE_TOKEN` ⚠️ May work as-is
Your local sfdx credentials are at `~/.sfdx/todd.ghidaleson.9a6f7118d805@agentforce.com.json`. The access token there *may* work directly. If Salesforce queries fail after deploy, regenerate a token in Salesforce Setup → Apps → Connected Apps → OAuth and OpenID Connect Settings.

---

## Step 3 — Redeploy After Adding Secrets

Once all env vars are filled:
- Go to **Deployments** tab
- Click **"Deploy latest commit"**

---

## Your URL After Deploy

`https://chaz-agent-portal.onrender.com`

Rename anytime: **Settings** → **Name** → `chaz-agent-portal`

---

## ⚠️ Important Notes

**Databricks Token is the key missing piece.** Without it, the inventory/supplier queries won't work. Everything else (Salesforce, Groq LLM) should work fine.

**Free tier spins down** after 15 min idle. Keep the tab open during your demo, or hit the `/test-llm` route before presenting to wake it up.

**If queries fail on first try** — the Databricks serverless warehouse may have cold-start lag (~10s). Wait and retry.

---

## What the Demo Does

The portal connects 3 systems:
1. **Groq LLM** — interprets your natural language query
2. **Databricks** — runs live inventory SQL on `chazbakedgoods.sales`
3. **Salesforce** — creates a Case for at-risk inventory items

Try: *"Which suppliers have butter below the reorder point?"*
