#!/usr/bin/env python3
"""
MassCEC Job Board -> daily email alert.

Scrapes https://www.masscec.com/job-board with a fixed set of filters
(Job Type + Job Category), tracks which listings it has already seen so it
can flag brand-new ones, and emails a formatted HTML digest.

Configure the filters in the FILTERS section below. IDs come straight from
the site's own <select> options, so adding/removing a filter is just editing
the dicts.
"""

import os
import re
import ssl
import json
import html
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlencode

import requests

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

BASE_URL = "https://www.masscec.com/job-board"

# Filters — value = the option's numeric term id on the site, key = label.
# Selecting several within a group is an OR (matches the site's Apply button).
JOB_TYPES = {
    "Full Time": 797,
    "Part Time": 798,
    # "Seasonal": 799,
    # "Contract": 800,
}

CATEGORIES = {
    "Analyst": 3,
    "Data Analysis/Management": 9,
    "Software Development": 26,
}

# Optional extra filter groups you can enable later (ids from the site):
REGIONS = {}   # e.g. {"Boston Metro": 34}
SECTORS = {}   # e.g. {"Solar": 60, "Offshore Wind": 899}
DEGREES = {}   # degree option ids if you ever want to constrain those

# Only include listings whose "Date Posted" is within this many days.
# Set to 0 (or None) to keep every match regardless of age.
MAX_AGE_DAYS = 10

# Own tracker file so it never collides with job-pulse's seen_links.json.
SEEN_FILE = os.path.join(os.path.dirname(__file__), "masscec_seen.json")
REQUEST_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (compatible; MassCEC-JobAlert/1.0)"


# ═══════════════════════════════════════════════════════════════════════════
# SCRAPING
# ═══════════════════════════════════════════════════════════════════════════

def build_filter_url(page=0):
    params = []
    for tid in JOB_TYPES.values():
        params.append(("job_type[]", tid))
    for tid in CATEGORIES.values():
        params.append(("category[]", tid))
    for tid in REGIONS.values():
        params.append(("region[]", tid))
    for tid in SECTORS.values():
        params.append(("sector[]", tid))
    for tid in DEGREES.values():
        params.append(("degree[]", tid))
    if page:
        params.append(("page", page))
    return f"{BASE_URL}?{urlencode(params)}"


def _cell(row_html, field):
    """Pull the text of a views-field-<field> table cell.

    The class may carry extra tokens (e.g. 'views-field-created is-active'),
    so match the field name followed by a space or the closing quote.
    """
    m = re.search(
        r'views-field-' + re.escape(field) + r'[ "][^>]*>(.*?)</td>',
        row_html, re.S)
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_posted_date(text):
    """Parse 'May 1, 2026' -> date. Returns None if it can't be parsed."""
    text = (text or "").strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_jobs(page_html):
    jobs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, re.S):
        if "views-field-title" not in row:
            continue
        link_m = re.search(r'href="(/job/[^"]+)"', row)
        title = _cell(row, "title")
        if not title:
            continue
        jobs.append({
            "title": title,
            "employer": _cell(row, "label"),
            "location": _cell(row, "field-job-location"),
            "type": _cell(row, "field-job-type"),
            "posted": _cell(row, "created"),
            "url": ("https://www.masscec.com" + link_m.group(1)) if link_m else BASE_URL,
        })
    return jobs


def fetch_all_jobs():
    """Fetch every page of the filtered result set."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    all_jobs, seen_urls, page = [], set(), 0
    while page < 20:  # hard cap, safety
        url = build_filter_url(page)
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        jobs = parse_jobs(resp.text)
        new = [j for j in jobs if j["url"] not in seen_urls]
        if not new:
            break
        for j in new:
            seen_urls.add(j["url"])
            all_jobs.append(j)
        # Only paginate if the site actually paged us; single-page results stop here.
        if 'rel="next"' not in resp.text and "pager__item--next" not in resp.text:
            break
        page += 1
    return all_jobs


def filter_recent(jobs, max_age_days=MAX_AGE_DAYS):
    """Keep only jobs posted within max_age_days. Jobs whose date can't be
    parsed are kept (better to surface than silently drop)."""
    if not max_age_days:
        return jobs
    today = datetime.now().date()
    kept = []
    for j in jobs:
        d = parse_posted_date(j.get("posted"))
        j["age_days"] = (today - d).days if d else None
        if d is None or 0 <= (today - d).days <= max_age_days:
            kept.append(j)
    return kept


# ═══════════════════════════════════════════════════════════════════════════
# SEEN-LINK TRACKING
# ═══════════════════════════════════════════════════════════════════════════

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, sort_keys=True)


# ═══════════════════════════════════════════════════════════════════════════
# EMAIL
# ═══════════════════════════════════════════════════════════════════════════

def build_html(jobs, new_urls):
    today = datetime.now().strftime("%B %d, %Y")
    new_count = len(new_urls)
    filter_summary = " · ".join([
        "Type: " + ", ".join(JOB_TYPES),
        "Category: " + ", ".join(CATEGORIES),
    ])

    rows = []
    for j in jobs:
        is_new = j["url"] in new_urls
        badge = ('<span style="background:#16a34a;color:#fff;font-size:11px;'
                 'padding:2px 7px;border-radius:10px;font-weight:600;">NEW</span>'
                 if is_new else '<span style="color:#94a3b8;font-size:12px;">—</span>')
        rows.append(f"""
        <tr style="border-bottom:1px solid #e2e8f0;">
          <td style="padding:12px 10px;">
            <a href="{html.escape(j['url'])}" style="color:#0f2b3d;font-weight:600;
               text-decoration:none;">{html.escape(j['title'])}</a><br>
            <span style="color:#64748b;font-size:13px;">{html.escape(j['employer'])}</span>
          </td>
          <td style="padding:12px 10px;color:#334155;font-size:13px;">{html.escape(j['type'])}</td>
          <td style="padding:12px 10px;color:#334155;font-size:13px;">{html.escape(j['location'])}</td>
          <td style="padding:12px 10px;color:#334155;font-size:13px;">{html.escape(j.get('posted',''))}</td>
          <td style="padding:12px 10px;text-align:center;">{badge}</td>
          <td style="padding:12px 10px;text-align:center;">
            <a href="{html.escape(j['url'])}" style="background:#0f2b3d;color:#fff;
               padding:6px 14px;border-radius:6px;text-decoration:none;font-size:13px;
               font-weight:600;">View</a>
          </td>
        </tr>""")

    body_rows = "".join(rows) if rows else (
        '<tr><td colspan="6" style="padding:24px;text-align:center;color:#64748b;">'
        'No jobs currently match your filters.</td></tr>')

    return f"""\
<!DOCTYPE html>
<html><body style="margin:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
  <div style="max-width:720px;margin:0 auto;padding:24px;">
    <div style="background:#0f2b3d;color:#fff;padding:24px;border-radius:12px 12px 0 0;">
      <h1 style="margin:0;font-size:22px;">🌱 MassCEC Job Alert</h1>
      <p style="margin:6px 0 0;color:#cbd5e1;font-size:14px;">{today}</p>
    </div>
    <div style="background:#fff;padding:16px 20px;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0;">
      <p style="margin:0;color:#334155;font-size:14px;">
        <strong>{len(jobs)}</strong> matching job{'s' if len(jobs)!=1 else ''} ·
        <strong style="color:#16a34a;">{new_count} new</strong> since last check
      </p>
      <p style="margin:6px 0 0;color:#94a3b8;font-size:12px;">{html.escape(filter_summary)}</p>
    </div>
    <table style="width:100%;border-collapse:collapse;background:#fff;
      border:1px solid #e2e8f0;border-radius:0 0 12px 12px;overflow:hidden;">
      <thead>
        <tr style="background:#f8fafc;text-align:left;">
          <th style="padding:10px;font-size:12px;color:#64748b;text-transform:uppercase;">Role</th>
          <th style="padding:10px;font-size:12px;color:#64748b;text-transform:uppercase;">Type</th>
          <th style="padding:10px;font-size:12px;color:#64748b;text-transform:uppercase;">Location</th>
          <th style="padding:10px;font-size:12px;color:#64748b;text-transform:uppercase;">Posted</th>
          <th style="padding:10px;font-size:12px;color:#64748b;text-transform:uppercase;text-align:center;">Status</th>
          <th style="padding:10px;font-size:12px;color:#64748b;text-transform:uppercase;text-align:center;">Link</th>
        </tr>
      </thead>
      <tbody>{body_rows}</tbody>
    </table>
    <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:16px;">
      Source: <a href="{html.escape(build_filter_url())}" style="color:#64748b;">masscec.com/job-board</a>
      · automated daily digest
    </p>
  </div>
</body></html>"""


def send_email(subject, html_body):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to_email = os.environ["TO_EMAIL"]
    from_email = os.environ.get("FROM_EMAIL", user)
    from_name = os.environ.get("FROM_NAME", "MassCEC Job Alert")
    cc_email = os.environ.get("CC_EMAIL", "").strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    recipients = [a.strip() for a in to_email.split(",") if a.strip()]
    if cc_email:
        msg["Cc"] = cc_email
        recipients += [a.strip() for a in cc_email.split(",") if a.strip()]
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.sendmail(from_email, recipients, msg.as_string())
    print(f"Email sent to {', '.join(recipients)}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    jobs = fetch_all_jobs()
    print(f"Fetched {len(jobs)} jobs matching filters.")
    if MAX_AGE_DAYS:
        jobs = filter_recent(jobs)
        print(f"{len(jobs)} posted within the last {MAX_AGE_DAYS} days.")

    seen = load_seen()
    now_iso = datetime.now(timezone.utc).isoformat()
    new_urls = {j["url"] for j in jobs if j["url"] not in seen}
    for j in jobs:
        seen.setdefault(j["url"], now_iso)

    subject = f"🌱 MassCEC Jobs — {len(jobs)} matching, {len(new_urls)} new"
    html_body = build_html(jobs, new_urls)

    # Only email when there are NEW listings (set ALWAYS_SEND=1 to override).
    if new_urls or os.environ.get("ALWAYS_SEND"):
        send_email(subject, html_body)
    else:
        print("No new jobs since last run — no email sent.")

    save_seen(seen)
    print(f"Tracked {len(seen)} total seen listings; {len(new_urls)} new this run.")


if __name__ == "__main__":
    main()
