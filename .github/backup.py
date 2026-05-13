"""
D & E Finance — Weekly Backup Script
Fetches all expenses, income, and accounts from Supabase and emails them as a
JSON attachment. The JSON can be re-imported via the app's CONFIG → Import
Backup feature. Backup format version 2.
"""

import json
import os
import requests
import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SUPABASE_URL  = os.environ['SUPABASE_URL'].rstrip('/')
SUPABASE_KEY  = os.environ['SUPABASE_KEY']
SMTP_HOST     = os.environ['SMTP_HOST']
SMTP_PORT     = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER     = os.environ['SMTP_USER']
SMTP_PASSWORD = os.environ['SMTP_PASSWORD']

RECIPIENTS = ['edwin@spicemore.com', 'mary.george@spicemore.com']

headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
}


def fetch(path):
    """GET a Supabase REST endpoint; return [] if the table doesn't exist."""
    r = requests.get(f'{SUPABASE_URL}/rest/v1/{path}', headers=headers, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


# ── 1. Fetch all three tables ─────────────────────────────────────────────────
expense_rows = fetch('expenses?select=*&order=date.desc')
income_rows  = fetch('income?select=*&order=date.desc')
account_rows = fetch('accounts?select=*&order=created_at.asc')

# ── 2. Map Supabase columns → app format ──────────────────────────────────────
entries = [{
    'id':       r.get('id'),
    'date':     r.get('date', ''),
    'amount':   float(r.get('amount', 0)),
    'category': r.get('category', ''),
    'type':     r.get('type', ''),
    'freq':     r.get('freq', ''),
    'forWhom':  r.get('for_whom', ''),
    'paidBy':   r.get('paid_by', ''),
    'saving':   r.get('saving', 'No'),
    'desc':     r.get('description') or r.get('desc', ''),
    'month':    r.get('month', ''),
    'addedBy':  r.get('added_by', ''),
    'account':  r.get('account'),
} for r in expense_rows]

income = [{
    'id':         r.get('id'),
    'date':       r.get('date', ''),
    'amount':     float(r.get('amount', 0)),
    'source':     r.get('source', ''),
    'receivedBy': r.get('received_by', ''),
    'account':    r.get('account'),
    'desc':       r.get('description', ''),
    'month':      r.get('month', ''),
    'addedBy':    r.get('added_by', ''),
} for r in income_rows]

accounts = [{
    'id':             r.get('id'),
    'name':           r.get('name', ''),
    'type':           r.get('type', ''),
    'openingBalance': float(r.get('opening_balance') or 0),
    'openingDate':    r.get('opening_date', '') or '',
    'currentValue':   float(r['current_value']) if r.get('current_value') is not None else None,
    'isLiability':    bool(r.get('is_liability')),
    'currency':       r.get('currency', 'INR'),
    'notes':          r.get('notes', '') or '',
    'archived':       bool(r.get('archived')),
} for r in account_rows]

# ── 3. Build backup payload ───────────────────────────────────────────────────
now_utc   = datetime.now(timezone.utc)
date_str  = now_utc.strftime('%Y-%m-%d')
backup = {
    'app':        'D & E Finance',
    'exportedAt': now_utc.isoformat(),
    'version':    '2',
    'config':     {},  # config lives in localStorage; backup carries data only
    'entries':    entries,
    'income':     income,
    'accounts':   accounts,
}
backup_json = json.dumps(backup, indent=2, ensure_ascii=False)
filename    = f'de-finance-backup-{date_str}.json'

# ── 4. Compute totals for email body ──────────────────────────────────────────
total_spend  = sum(e['amount'] for e in entries)
total_income = sum(i['amount'] for i in income)


def account_balance(a):
    if a['type'] in ('Investment', 'Asset', 'Loan'):
        return a['currentValue'] if a['currentValue'] is not None else a['openingBalance']
    inflow  = sum(i['amount'] for i in income  if i['account'] == a['id'])
    outflow = sum(e['amount'] for e in entries if e['account'] == a['id'])
    return a['openingBalance'] + inflow - outflow


active_accounts = [a for a in accounts if not a['archived']]
net_worth = sum(account_balance(a) * (-1 if a['isLiability'] else 1) for a in active_accounts)

# ── 5. Compose email ──────────────────────────────────────────────────────────
msg            = MIMEMultipart()
msg['From']    = SMTP_USER
msg['To']      = ', '.join(RECIPIENTS)
msg['Subject'] = f'D & E Finance — Weekly Backup ({date_str})'

body = f"""\
Hi Edwin & Mary,

Your weekly D & E Finance backup is attached.

  Expenses backed up : {len(entries)}    (₹{total_spend:,.0f})
  Income backed up   : {len(income)}    (₹{total_income:,.0f})
  Accounts tracked   : {len(active_accounts)}
  Net worth (today)  : ₹{net_worth:,.0f}
  Backup date        : {date_str}
  File               : {filename}

HOW TO RESTORE
──────────────
1. Open the app and go to CONFIG (bottom-right gear icon).
2. Scroll to the Data section.
3. Tap "Import Backup" and select the attached .json file.
4. Confirm — all data will be restored exactly as it was.

This backup was generated automatically every Sunday at 11 PM IST.

— D & E Finance Auto-Backup
"""
msg.attach(MIMEText(body, 'plain'))

attachment = MIMEApplication(backup_json.encode('utf-8'), _subtype='json')
attachment.add_header('Content-Disposition', 'attachment', filename=filename)
msg.attach(attachment)

# ── 6. Send via SMTP ──────────────────────────────────────────────────────────
with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
    server.ehlo()
    server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.sendmail(SMTP_USER, RECIPIENTS, msg.as_string())

print(f'✓ Backup sent — {len(entries)} expenses, {len(income)} income, '
      f'{len(active_accounts)} accounts, net worth ₹{net_worth:,.0f}')
