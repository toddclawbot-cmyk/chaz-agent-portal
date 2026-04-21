# Email Voice — Chaz Bakery Outreach

## Sender Info
**From:** Riley Torres | Sales Director | Chaz Bakery | rtorres@chazsbakery.com

## Voice & Tone
- Warm but professional — personal, not corporate
- Concise and direct — never filler, no generic pleasantries
- Lead with the key point — don't bury the lede
- Proactive, not defensive — we caught something, we're on it, we're reaching out first
- Reassuring — customer should feel confident, not worried

## Email Structure

**Subject:** `{customer_name} — {order_description}: We have your back!`

**Opening (1-2 sentences):**
- Reference the specific customer and order
- Get to the point immediately — no "I hope this finds you well"

**Body:**
- State the supply/situation issue clearly but reassuringly
- Lead with what's confirmed and protected
- Mention the specific order numbers/volume if relevant
- Give a clear next step or action

**Sign Off:**
Riley Torres
Sales Director | Chaz Bakery
rtorres@chazsbakery.com

## Tone Modifiers

### When shortage > 200 lbs OR opportunity > $50K (Urgent):
- Acknowledge the risk directly, don't downplay
- Emphasize what's being done to protect the customer
- Make the action step concrete ("I'll send a formal confirmation by Friday")

### When returning customer / no risk detected (Warm):
- Shorter, lighter
- Acknowledge the relationship
- Can be more casual in opening

## Dynamic Variables Available
- `{customer_name}` — contact first name (Taylor)
- `{customer_full}` — full name with title (Taylor Nguyen, Owner)
- `{customer_email}` — their email address
- `{opp_name}` — Salesforce opportunity name
- `{opp_value}` — opportunity dollar amount
- `{opp_close_date}` — close date
- `{order_qty}` — number of units in order
- `{order_date}` — delivery/order date
- `{shortage_lbs}` — butter shortage in lbs
- `{shortage_pct}` — coverage percentage
- `{butter_need}` — total butter needed in lbs
- `{case_id}` — Salesforce case ID

## Example Output

**Subject:** Cafe Lumiere — May 8 Pastry Delivery: Quick Heads Up

**Body:**
Hi Taylor,

Quick note from your Chaz Bakery account team — our ops team flagged a tight supply window on your May 8 pastry order. Your Full Pastry Program is fully confirmed and scheduled as a priority run, but I wanted to give you a heads up proactively.

Grassland Dairy's next butter delivery isn't until April 26, and we're managing production carefully to protect your order. Your May 8 delivery of 2,330 pastry units is locked in — we'll send a formal confirmation by end of week.

If anything changes on your end, let me know and we'll adjust immediately.

Talk soon,
Riley Torres
Sales Director | Chaz Bakery | rtorres@chazsbakery.com