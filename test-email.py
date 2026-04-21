from dotenv import load_dotenv
load_dotenv('/Users/chaz/Documents/Coding Projects/chaz-agent-portal/.env')
import os, requests

skill = open('/Users/chaz/Documents/Coding Projects/chaz-agent-portal/skills/email-skill.md').read()
ctx = {
    'customer_name': 'Taylor', 'customer_full': 'Taylor Nguyen', 'customer_email': 'taylor@caflumiere.com',
    'opp_name': 'Cafe Lumiere Full Program', 'opp_value': 85000, 'opp_close_date': 'May 15',
    'cafe_units': 2330, 'order_date': 'May 8', 'butter_need': 500, 'butter_shortage': 420, 'coverage_pct': 50, 'case_id': 'CS-0001',
}

system_prompt = 'You are Riley Torres, Sales Director at Chaz Bakery. Use the email skill below.\n\n' + skill + '\n\nWrite the full email — subject line + body. Return ONLY the email.'

context_vars = {
    'customer_name': ctx['customer_name'], 'customer_full': ctx['customer_full'],
    'customer_email': ctx['customer_email'], 'opp_name': ctx['opp_name'],
    'opp_value': ctx['opp_value'], 'opp_close_date': ctx['opp_close_date'],
    'order_qty': int(ctx.get('cafe_units', 0) or 0), 'order_date': ctx.get('order_date', ''),
    'order_description': ctx.get('order_date', '') + ' Pastry Delivery',
    'shortage_lbs': ctx.get('butter_shortage', 0), 'shortage_pct': ctx.get('coverage_pct', 0),
    'butter_need': ctx.get('butter_need', 0), 'case_id': ctx.get('case_id', ''),
}

user_prompt = (
    'Write the outreach email for:\n' + '\n'.join(f'  - {k}: {v}' for k, v in context_vars.items())
    + '\n\nThe subject line format is defined in the skill file — follow it exactly.'
    + '\n\nContext: customer=' + context_vars['customer_name'] + ' qty=' + str(context_vars['order_qty']) + ' shortage=' + str(context_vars['shortage_lbs']) + ' opp=' + context_vars['opp_name']
    + ' Case=' + context_vars['case_id']
    + '\n\nInclude: subject line + full body, sign off as Riley Torres, Sales Director, Chaz Bakery.'
)

resp = requests.post('https://api.groq.com/openai/v1/chat/completions',
    headers={'Authorization': 'Bearer ' + os.getenv('GROQ_API_KEY'), 'Content-Type': 'application/json'},
    json={'model': 'llama-3.3-70b-versatile', 'messages': [{'role':'system','content':system_prompt},{'role':'user','content':user_prompt}], 'temperature': 0.7, 'max_tokens': 600},
    timeout=30)

output = resp.json()['choices'][0]['message']['content']
print('=== GENERATED EMAIL ===')
print(output)
print('===')
print('Subject line found:', [l for l in output.split('\n') if 'Subject:' in l or 'subject:' in l])