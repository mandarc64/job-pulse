# Job Pulse 🎯

**Automated job alerts for new grads** — Scrapes curated GitHub job boards, categorizes roles, and delivers beautiful HTML emails daily.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Automation](https://img.shields.io/badge/Automation-Email%20Alerts-orange)

---

## Features

- **Multi-Source Scraping** — Pulls from curated GitHub job repositories:
  - [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions)
  - [speedyapply/2026-SWE-College-Jobs](https://github.com/speedyapply/2026-SWE-College-Jobs)
  - [speedyapply/2026-AI-College-Jobs](https://github.com/speedyapply/2026-AI-College-Jobs)

- **Smart Categorization** — Auto-sorts jobs into:
  - 📊 Data & Analytics
  - 🤖 AI & Machine Learning
  - 💻 Software Engineering

- **Rolling Window** — Never miss a job! Shows the last 10 days of postings even if you skip checking

- **LinkedIn Quick Search** — One-click buttons filtered by industry:
  - 🎓 Education & Higher Ed
  - 💻 Tech Industry
  - 🌿 Environmental & Sustainability
  - 🧪 Chemical & Pharmaceutical
  - 💰 Finance & Banking
  - 🏥 Healthcare

- **Beautiful HTML Emails** — Clean tabular format with NEW badges for fresh postings

---

## Sample Email

```
┌─────────────────────────────────────────────────────────────┐
│  🎯 New Grad Job Alert                                      │
│  January 26, 2026                                           │
├─────────────────────────────────────────────────────────────┤
│  📊 Data & Analytics (15 jobs, 3 new!)                      │
│  ┌──────────┬─────────────────┬──────────┬────────┬───────┐ │
│  │ Company  │ Job Title       │ Location │ In List│ Action│ │
│  ├──────────┼─────────────────┼──────────┼────────┼───────┤ │
│  │ Google   │ Data Analyst    │ NYC      │ 🆕 New!│ Apply │ │
│  │ Meta     │ Analytics Eng   │ Remote   │ 2 days │ Apply │ │
│  └──────────┴─────────────────┴──────────┴────────┴───────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/job-pulse.git
cd job-pulse
```

### 2. Install Dependencies

```bash
pip install requests
```

### 3. Set Environment Variables

```bash
# Required
export SMTP_HOST="smtp.gmail.com"            # SMTP server hostname
export SMTP_USER="your-email@gmail.com"      # SMTP login username
export SMTP_PASS="your-app-password"         # Use Gmail App Password
export TO_EMAIL="recipient@example.com"      # Primary recipient

# Optional
export FROM_NAME="Job Pulse"                 # Sender display name
export FROM_EMAIL="your-email@gmail.com"     # Sender email (defaults to SMTP_USER)
export CC_EMAIL="friend@example.com"         # CC recipients (comma-separated)
export SMTP_PORT="587"                       # Default: 587
```

> **Gmail Users**: You need an [App Password](https://support.google.com/accounts/answer/185833), not your regular password.

### 4. Run

```bash
python job_alerts.py
```

---

## Configuration

Edit the top of `job_alerts.py` to customize:

```python
# How old can jobs be? (in days)
MAX_JOB_AGE_DAYS = 90

# Rolling window - days to keep showing jobs
ROLLING_WINDOW_DAYS = 10

# Minimum jobs to show per category
MIN_JOBS_PER_CATEGORY = 10
```

### Adding Custom Job Sources

Add new GitHub raw URLs to the `SOURCES` list:

```python
SOURCES = [
    "https://raw.githubusercontent.com/.../README.md",
    # Add more sources here
]
```

### Customizing LinkedIn Searches

Modify `LINKEDIN_SEARCHES` to add industries or search queries:

```python
LINKEDIN_SEARCHES = {
    "your_category": {
        "title": "🎯 Your Category",
        "industry_ids": ["68", "67"],  # LinkedIn Industry IDs
        "searches": [
            {"emoji": "📊", "title": "Analyst", "query": "data analyst"},
        ],
    },
}
```

Industry IDs reference: [LinkedIn Industry Codes V2](https://learn.microsoft.com/en-us/linkedin/shared/references/reference-tables/industry-codes-v2)

---

## Automation

### GitHub Actions (Recommended)

Create `.github/workflows/job-alerts.yml`:

```yaml
name: Daily Job Alerts

on:
  schedule:
    - cron: '0 14 * * *'  # 9 AM EST daily
  workflow_dispatch:       # Manual trigger

jobs:
  send-alerts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests

      - name: Run job alerts
        env:
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          TO_EMAIL: ${{ secrets.TO_EMAIL }}
          CC_EMAIL: ${{ secrets.CC_EMAIL }}        # Optional
          FROM_NAME: "Job Pulse"
        run: python job_alerts.py

      - name: Commit updated history
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add seen_links.json job_history.json || true
          git diff --staged --quiet || git commit -m "Update job history"
          git push
```

Add secrets in your repo: **Settings → Secrets → Actions**

### Windows Task Scheduler

```batch
@echo off
set EMAIL_ADDRESS=your-email@gmail.com
set EMAIL_PASSWORD=your-app-password
set RECIPIENT_EMAIL=recipient@example.com
python C:\path\to\job_alerts.py
```

### Linux/Mac Cron

```bash
# Edit crontab
crontab -e

# Add (runs daily at 9 AM)
0 9 * * * cd /path/to/job-pulse && /usr/bin/python3 job_alerts.py
```

---

## File Structure

```
job-pulse/
├── job_alerts.py      # Main script
├── seen_links.json    # Tracks processed URLs (auto-generated)
├── job_history.json   # Rolling job history (auto-generated)
├── README.md
└── .github/
    └── workflows/
        └── job-alerts.yml
```

---

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  GitHub Repos   │────▶│  Parse Tables    │────▶│  Categorize     │
│  (Job Boards)   │     │  (MD + HTML)     │     │  by Keywords    │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐     ┌────────▼────────┐
│  Send Email     │◀────│  Build HTML      │◀────│  Filter & Track │
│  via SMTP       │     │  Template        │     │  Job History    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

1. **Fetch** — Downloads README files from GitHub job boards
2. **Parse** — Extracts job data from markdown/HTML tables
3. **Filter** — Removes duplicates, old jobs, non-application links
4. **Categorize** — Sorts into Data, AI/ML, or Software based on title keywords
5. **Track** — Maintains rolling history so you don't miss jobs
6. **Email** — Sends formatted HTML email with job tables + LinkedIn links

---

## Troubleshooting

### No jobs parsed?

- Check if source repos changed their table format
- Run with debug output to see parsing details

### Gmail authentication failed?

- Use an [App Password](https://support.google.com/accounts/answer/185833), not your regular password
- Enable 2FA on your Google account first

### Jobs marked "Not job link"?

- The script filters for known job platforms (Greenhouse, Lever, Workday, etc.)
- Company website links are skipped

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/new-source`)
3. Commit changes (`git commit -m 'Add new job source'`)
4. Push (`git push origin feature/new-source`)
5. Open a Pull Request

---

## License

MIT License — feel free to use and modify!

---

## Acknowledgments

- [SimplifyJobs](https://github.com/SimplifyJobs) for maintaining the new grad job list
- [speedyapply](https://github.com/speedyapply) for SWE and AI job compilations

---

**Made with ☕ for job-hunting new grads**
