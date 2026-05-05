"""
D & E Finance — Weekly Backup Script
Fetches all expense data from Supabase and emails it as a JSON attachment.
The JSON can be re-imported via the app's CONFIG → Import Backup feature.
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

# ── 1. Fetch all entries from Supabase ────────────────────────────────────────
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
}

response = requests.get(
    f'{SUPABASE_URL}/rest/v1/expenses?select=*&order=date.desc',
    headers=headers,
    timeout=30,
)
response.raise_for_status()
rows = response.json()

# ── 2. Map Supabase columns → app format ──────────────────────────────────────
entries = []
for r in rows:
    entries.append({
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
    })

# ── 3. Build backup payload ───────────────────────────────────────────────────
now_utc   = datetime.now(timezone.utc)
date_str  = now_utc.strftime('%Y-%m-%d')
backup    = {
    'app':        'D & E Finance',
    'exportedAt': now_utc.isoformat(),
    'version':    '1',
    'entries':    entries,
}
backup_json = json.dumps(backup, indent=2, ensure_ascii=False)
filename    = f'de-finance-backup-{date_str}.json'

# ── 4. Compose email ──────────────────────────────────────────────────────────
total_amount = sum(e['amount'] for e in entries)

msg              = MIMEMultipart()
msg['From']      = SMTP_USER
msg['To']        = ', '.join(RECIPIENTS)
msg['Subject']   = f'D & E Finance — Weekly Backup ({date_str})'

body = f"""\
Hi Edwin & Mary,

Your weekly D & E Finance backup is attached.

  Entries backed up : {len(entries)}
  Total spend       : ₹{total_amount:,.0f}
  Backup date       : {date_str}
  File              : {filename}

HOW TO RESTORE
──────────────
1. Open the app and go to CONFIG (bottom-right gear icon).
2. Scroll to the Data section.
3. Tap "Import Backup" and select the attached .json file.
4. Confirm — all entries will be restored exactly as they were.

This backup was generated automatically every Sunday at 11 PM IST.

— D & E Finance Auto-Backup
"""
msg.attach(MIMEText(body, 'plain'))

attachment = MIMEApplication(backup_json.encode('utf-8'), _subtype='json')
attachment.add_header('Content-Disposition', 'attachment', filename=filename)
msg.attach(attachment)

# ── 5. Send via SMTP ──────────────────────────────────────────────────────────
with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
    server.ehlo()
    server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.sendmail(SMTP_USER, RECIPIENTS, msg.as_string())

print(f'✓ Backup sent — {len(entries)} entries, ₹{total_amount:,.0f} total')
