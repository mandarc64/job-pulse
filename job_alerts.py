import os
import re
import json
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote_plus
from dataclasses import dataclass, asdict

import requests

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Maximum age of jobs to include from sources (in days)
MAX_JOB_AGE_DAYS = 90  # Include jobs up to 3 months old

# Rolling window: How many days to keep showing a job in emails
# (even if no new jobs are found, you'll see the last N days of jobs)
ROLLING_WINDOW_DAYS = 10

# Minimum jobs to show per category (will pull from history if needed)
MIN_JOBS_PER_CATEGORY = 10

SOURCES = [
    # 2026 trackers / new-grad aggregators
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/master/README.md",
    "https://raw.githubusercontent.com/speedyapply/2026-SWE-College-Jobs/main/NEW_GRAD_USA.md",
    "https://raw.githubusercontent.com/speedyapply/2026-AI-College-Jobs/main/NEW_GRAD_USA.md",
]

# Job categories with keywords and emojis (DATA FIRST as requested)
CATEGORIES = {
    "data": {
        "emoji": "📊",
        "title": "Data & Analytics",
        "keywords": [
            "data science",
            "data scientist",
            "data analytics",
            "data analyst",
            "business analytics",
            "business analyst",
            "analytics engineer",
            "data engineer",
            "bi developer",
            "business intelligence",
            "quantitative",
            "biostatistician",
        ],
    },
    "ai_ml": {
        "emoji": "🤖",
        "title": "AI & Machine Learning",
        "keywords": [
            "machine learning",
            "ml engineer",
            "ai engineer",
            "deep learning",
            "nlp",
            "computer vision",
            "mlops",
            "artificial intelligence",
        ],
    },
    "software": {
        "emoji": "💻",
        "title": "Software Engineering",
        "keywords": [
            "software engineer",
            "software developer",
            "swe",
            "backend",
            "front end",
            "frontend",
            "full stack",
            "fullstack",
            "developer",
            "web developer",
            "mobile developer",
            "ios",
            "android",
        ],
    },
}

# LinkedIn search queries organized by category
# All searches filter for: Entry Level + Posted This Week
# Industry IDs from: https://learn.microsoft.com/en-us/linkedin/shared/references/reference-tables/industry-codes-v2
# 68=Higher Ed, 67=K-12, 86=Environmental Services, 43=Financial Services, 41=Banking
# 15=Pharmaceutical Mfg, 54=Chemical Mfg, 14=Hospitals & Healthcare, 3251=Climate Tech
LINKEDIN_SEARCHES = {
    "general": {
        "title": "🎯 General Data & Tech Roles",
        "emoji": "🎯",
        "industry_ids": None,  # No industry filter - all industries
        "searches": [
            {"emoji": "📊", "title": "Data Analyst", "query": "data analyst"},
            {"emoji": "📈", "title": "Data Scientist", "query": "data scientist"},
            {
                "emoji": "🤖",
                "title": "ML Engineer",
                "query": "machine learning engineer",
            },
            {
                "emoji": "💻",
                "title": "Software Engineer",
                "query": "software engineer new grad 2026",
            },
            {"emoji": "🔧", "title": "Data Engineer", "query": "data engineer"},
        ],
    },
    "education": {
        "title": "🎓 Education & Higher Ed",
        "emoji": "🎓",
        "industry_ids": [
            "68",
            "67",
        ],  # 68=Higher Education, 67=Primary/Secondary Education
        "searches": [
            {
                "emoji": "🏫",
                "title": "Data Analyst (Education)",
                "query": "data analyst",
            },
            {
                "emoji": "📚",
                "title": "Research Analyst",
                "query": "research analyst OR research associate",
            },
            {
                "emoji": "📊",
                "title": "Institutional Research",
                "query": "institutional research analyst",
            },
            {"emoji": "📖", "title": "Education Analyst", "query": "analyst"},
        ],
    },
    "tech": {
        "title": "💻 Tech Industry",
        "emoji": "💻",
        "industry_ids": ["4", "6", "96"],  # 4=Internet, 6=Software, 96=IT Services
        "searches": [
            {"emoji": "☁️", "title": "Cloud Engineer", "query": "cloud data engineer"},
            {"emoji": "📱", "title": "Product Analyst", "query": "product analyst"},
            {
                "emoji": "🔍",
                "title": "BI Analyst",
                "query": "business intelligence analyst",
            },
            {
                "emoji": "⚡",
                "title": "Analytics Engineer",
                "query": "analytics engineer",
            },
        ],
    },
    "environmental": {
        "title": "🌿 Environmental & Sustainability",
        "emoji": "🌿",
        "industry_ids": [
            "86",
            "3251",
            "144",
        ],  # 86=Environmental Services, 3251=Climate Tech, 144=Renewable Energy
        "searches": [
            {
                "emoji": "🌍",
                "title": "Environmental Analyst",
                "query": "environmental analyst OR scientist",
            },
            {
                "emoji": "♻️",
                "title": "Sustainability Analyst",
                "query": "sustainability analyst",
            },
            {
                "emoji": "🌱",
                "title": "Climate Analyst",
                "query": "climate analyst OR scientist",
            },
            {"emoji": "💧", "title": "ESG Analyst", "query": "ESG analyst"},
        ],
    },
    "chemical": {
        "title": "🧪 Chemical & Pharmaceutical",
        "emoji": "🧪",
        "industry_ids": ["15", "54"],  # 15=Pharmaceutical Mfg, 54=Chemical Mfg
        "searches": [
            {"emoji": "💊", "title": "Pharma Analyst", "query": "data analyst"},
            {
                "emoji": "🔬",
                "title": "Clinical Data",
                "query": "clinical data analyst OR associate",
            },
            {"emoji": "⚗️", "title": "Scientist", "query": "scientist data"},
            {
                "emoji": "🧬",
                "title": "Bioinformatics",
                "query": "bioinformatics analyst",
            },
        ],
    },
    "finance": {
        "title": "💰 Finance & Banking",
        "emoji": "💰",
        "industry_ids": [
            "43",
            "41",
            "129",
        ],  # 43=Financial Services, 41=Banking, 129=Capital Markets
        "searches": [
            {
                "emoji": "🏦",
                "title": "Financial Analyst",
                "query": "financial analyst data",
            },
            {"emoji": "📊", "title": "Risk Analyst", "query": "risk analyst"},
            {"emoji": "💹", "title": "Quant Analyst", "query": "quantitative analyst"},
            {"emoji": "🏢", "title": "Business Analyst", "query": "business analyst"},
        ],
    },
    "healthcare": {
        "title": "🏥 Healthcare",
        "emoji": "🏥",
        "industry_ids": ["14", "2081"],  # 14=Hospitals & Healthcare, 2081=Hospitals
        "searches": [
            {
                "emoji": "🩺",
                "title": "Healthcare Analyst",
                "query": "healthcare data analyst",
            },
            {
                "emoji": "📋",
                "title": "Health Informatics",
                "query": "health informatics analyst",
            },
            {
                "emoji": "💉",
                "title": "Clinical Analytics",
                "query": "clinical analytics",
            },
            {"emoji": "🏨", "title": "Hospital Analyst", "query": "data analyst"},
        ],
    },
}

# Domains commonly used for application links
JOB_HOST_HINTS = (
    "greenhouse.io",
    "lever.co",
    "workdayjobs.com",
    "myworkdayjobs.com",
    "ashbyhq.com",
    "smartrecruiters.com",
    "icims.com",
    "jobs.",
    "careers.",
    "jobvite.com",
    "bamboohr.com",
    "ultipro.com",
    "jobright.ai",
)

URL_RE = re.compile(r"https?://[^\s)>\]]+")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Job:
    company: str
    title: str
    location: str
    url: str
    date_posted: str  # Original date string
    days_ago: int | None  # Computed days ago (None if unparseable)
    first_seen: str | None = None  # ISO date when we first saw this job
    category: str | None = None  # Category for storage


# ═══════════════════════════════════════════════════════════════════════════════
# LINKEDIN URL BUILDER
# ═══════════════════════════════════════════════════════════════════════════════


def build_linkedin_search_url(
    query: str, experience_level: str = "entry", industry_ids: list[str] | None = None
) -> str:
    """
    Build LinkedIn job search URL with filters.
    f_TPR=r604800 means posted in past week (604800 seconds = 7 days)
    f_E: 1=Internship, 2=Entry level, 3=Associate, 4=Mid-Senior
    f_I: Industry IDs (e.g., "68" for Higher Education)

    Industry IDs (from LinkedIn V2):
    - 68 = Higher Education
    - 67 = Primary/Secondary Education (K-12)
    - 86 = Environmental Services
    - 43 = Financial Services
    - 41 = Banking
    - 15 = Pharmaceutical Manufacturing
    - 54 = Chemical Manufacturing
    - 14 = Hospitals & Healthcare
    - 3251 = Climate Technology
    - 144 = Renewable Energy
    - 129 = Capital Markets
    """
    base = "https://www.linkedin.com/jobs/search/"

    # Experience level mapping
    exp_map = {
        "entry": "2",  # Entry level only
        "entry_associate": "2,3",  # Entry + Associate (1-2 years)
    }

    params = {
        "keywords": query,
        "f_TPR": "r604800",  # Posted this week
        "f_E": exp_map.get(experience_level, "2"),
        "sortBy": "DD",  # Sort by date
    }

    # Add industry filter if specified
    if industry_ids:
        params["f_I"] = ",".join(industry_ids)

    query_string = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
    return f"{base}?{query_string}"


# ═══════════════════════════════════════════════════════════════════════════════
# DATE PARSING
# ═══════════════════════════════════════════════════════════════════════════════


def parse_relative_date(age_str: str) -> int | None:
    """Parse relative date strings like '2d', '3d', '1mo', '2w'."""
    age_str = age_str.strip().lower()
    match = re.match(r"(\d+)\s*(d|day|days|w|week|weeks|mo|month|months)", age_str)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if unit in ("d", "day", "days"):
            return num
        elif unit in ("w", "week", "weeks"):
            return num * 7
        elif unit in ("mo", "month", "months"):
            return num * 30
    return None


def parse_absolute_date(date_str: str) -> int | None:
    """Parse absolute date strings like 'Jan 26', 'Jan 25'."""
    date_str = date_str.strip()
    today = datetime.now()
    current_year = today.year

    for fmt in ["%b %d", "%B %d"]:
        try:
            parsed = datetime.strptime(date_str, fmt)
            parsed = parsed.replace(year=current_year)
            if parsed > today:
                parsed = parsed.replace(year=current_year - 1)
            delta = today - parsed
            return delta.days
        except ValueError:
            continue
    return None


def parse_date(date_str: str) -> int | None:
    """Parse either relative ('2d') or absolute ('Jan 26') date strings."""
    if not date_str:
        return None
    result = parse_relative_date(date_str)
    if result is not None:
        return result
    return parse_absolute_date(date_str)


def is_within_days(days_ago: int | None, max_days: int) -> bool:
    """Check if job is within the specified number of days."""
    if days_ago is None:
        return True
    return days_ago <= max_days


# ═══════════════════════════════════════════════════════════════════════════════
# JOB HISTORY (Rolling Window)
# ═══════════════════════════════════════════════════════════════════════════════


def load_job_history(path="job_history.json") -> dict[str, list[dict]]:
    """Load job history with first_seen dates."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"data": [], "ai_ml": [], "software": []}


def save_job_history(history: dict[str, list[dict]], path="job_history.json") -> None:
    """Save job history."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def cleanup_old_jobs(
    history: dict[str, list[dict]], max_days: int
) -> dict[str, list[dict]]:
    """Remove jobs older than max_days from history."""
    today = datetime.now().date()
    cleaned = {}

    for category, jobs in history.items():
        cleaned[category] = []
        for job in jobs:
            first_seen = job.get("first_seen")
            if first_seen:
                try:
                    seen_date = datetime.fromisoformat(first_seen).date()
                    days_in_history = (today - seen_date).days
                    if days_in_history <= max_days:
                        cleaned[category].append(job)
                except ValueError:
                    cleaned[category].append(job)
            else:
                cleaned[category].append(job)

    return cleaned


def add_jobs_to_history(
    history: dict[str, list[dict]], new_jobs: dict[str, list[Job]]
) -> dict[str, list[dict]]:
    """Add new jobs to history with first_seen date."""
    today = datetime.now().isoformat()

    for category, jobs in new_jobs.items():
        existing_urls = {j["url"] for j in history.get(category, [])}

        for job in jobs:
            if job.url not in existing_urls:
                job_dict = asdict(job)
                job_dict["first_seen"] = today
                job_dict["category"] = category
                history.setdefault(category, []).insert(
                    0, job_dict
                )  # Add to front (newest first)

    return history


def get_jobs_from_history(
    history: dict[str, list[dict]], category: str, limit: int
) -> list[Job]:
    """Get jobs from history, respecting the limit."""
    jobs = []
    for job_dict in history.get(category, [])[:limit]:
        jobs.append(
            Job(
                company=job_dict["company"],
                title=job_dict["title"],
                location=job_dict["location"],
                url=job_dict["url"],
                date_posted=job_dict.get("date_posted", ""),
                days_ago=job_dict.get("days_ago"),
                first_seen=job_dict.get("first_seen"),
                category=job_dict.get("category"),
            )
        )
    return jobs


# ═══════════════════════════════════════════════════════════════════════════════
# MARKDOWN TABLE PARSING
# ═══════════════════════════════════════════════════════════════════════════════


def extract_text_from_cell(cell: str) -> str:
    """Extract plain text from a markdown cell (supports markdown and HTML)."""
    # Remove HTML tags but keep text content
    # Handle <a href="..."><strong>Text</strong></a> -> Text
    cell = re.sub(r"<a[^>]*>", "", cell, flags=re.IGNORECASE)
    cell = re.sub(r"</a>", "", cell, flags=re.IGNORECASE)
    cell = re.sub(r"<strong>", "", cell, flags=re.IGNORECASE)
    cell = re.sub(r"</strong>", "", cell, flags=re.IGNORECASE)
    cell = re.sub(r"<img[^>]*>", "", cell, flags=re.IGNORECASE)
    cell = re.sub(r"<[^>]+>", "", cell)  # Remove any remaining HTML tags
    # Remove markdown links [text](url) -> text
    cell = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cell)
    # Remove bold/italic
    cell = re.sub(r"\*+([^*]+)\*+", r"\1", cell)
    return cell.strip()


def extract_url_from_cell(cell: str) -> str | None:
    """Extract first URL from a markdown cell (supports markdown and HTML links)."""
    # Try HTML anchor tags first: <a href="url">
    match = re.search(r'<a\s+href=["\']([^"\']+)["\']', cell, re.IGNORECASE)
    if match:
        return match.group(1)
    # Try markdown links: [text](url)
    match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", cell)
    if match:
        return match.group(2)
    # Try bare URLs
    match = URL_RE.search(cell)
    if match:
        return match.group(0).rstrip('.,;:!?)"]')
    return None


def parse_html_table(text: str) -> list[dict]:
    """Parse HTML tables (used by SimplifyJobs)."""
    jobs = []

    # Find all table rows
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.DOTALL | re.IGNORECASE)

    for row in rows:
        # Skip header rows
        if "<th" in row.lower():
            continue

        # Extract all cells
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 4:
            continue

        # Expected format: Company | Role | Location | Application | Age
        company = extract_text_from_cell(cells[0]) if len(cells) > 0 else ""
        title = extract_text_from_cell(cells[1]) if len(cells) > 1 else ""
        location = extract_text_from_cell(cells[2]) if len(cells) > 2 else ""

        # Find the application URL (usually in cell 3 or 4)
        url = None
        for cell in cells[3:]:
            # Look for job platform URLs first
            extracted = extract_url_from_cell(cell)
            if extracted and any(hint in extracted.lower() for hint in JOB_HOST_HINTS):
                url = extracted
                break

        # Get age from last cell
        age = extract_text_from_cell(cells[-1]) if cells else ""

        if company and url:
            jobs.append(
                {
                    "company": company,
                    "title": title or "New Grad Position",
                    "location": location or "USA",
                    "url": url,
                    "date": age,
                }
            )

    return jobs


def parse_markdown_table(text: str) -> list[dict]:
    """Parse markdown tables and extract job data."""
    jobs = []
    lines = text.split("\n")
    header_indices = {}
    in_table = False

    for line in lines:
        line = line.strip()

        if not line:
            in_table = False
            header_indices = {}
            continue

        if not line.startswith("|"):
            in_table = False
            header_indices = {}
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c or cells.index(c) not in (0, len(cells) - 1)]
        if not cells:
            continue

        if all(re.match(r"^[-:]+$", c) for c in cells):
            continue

        header_lower = [c.lower() for c in cells]
        if not in_table and (
            "company" in header_lower
            or "role" in header_lower
            or "job title" in header_lower
        ):
            in_table = True
            for idx, h in enumerate(header_lower):
                if "company" in h:
                    header_indices["company"] = idx
                elif "role" in h or "title" in h or "job" in h:
                    header_indices["title"] = idx
                elif "location" in h:
                    header_indices["location"] = idx
                elif "application" in h or "apply" in h:
                    header_indices["url"] = idx
                elif "age" in h or "date" in h or "posted" in h:
                    header_indices["date"] = idx
            continue

        if in_table and header_indices:
            job_data = {}

            # Extract company name (text only, not URL)
            if "company" in header_indices and header_indices["company"] < len(cells):
                cell = cells[header_indices["company"]]
                job_data["company"] = extract_text_from_cell(cell)

            # Extract title
            if "title" in header_indices and header_indices["title"] < len(cells):
                cell = cells[header_indices["title"]]
                job_data["title"] = extract_text_from_cell(cell)

            # Extract location
            if "location" in header_indices and header_indices["location"] < len(cells):
                job_data["location"] = extract_text_from_cell(
                    cells[header_indices["location"]]
                )

            # Extract date
            if "date" in header_indices and header_indices["date"] < len(cells):
                job_data["date"] = extract_text_from_cell(cells[header_indices["date"]])

            # Extract URL - PRIORITY: dedicated URL column first
            if "url" in header_indices and header_indices["url"] < len(cells):
                url = extract_url_from_cell(cells[header_indices["url"]])
                if url:
                    job_data["url"] = url

            # If no URL column found, scan ALL cells for job platform URLs
            if not job_data.get("url"):
                for cell in cells:
                    url = extract_url_from_cell(cell)
                    if url and any(hint in url.lower() for hint in JOB_HOST_HINTS):
                        job_data["url"] = url
                        break

            # Last resort: get URL from title cell (often has the application link)
            if not job_data.get("url") and "title" in header_indices:
                cell = cells[header_indices["title"]]
                url = extract_url_from_cell(cell)
                if url:
                    job_data["url"] = url

            if job_data.get("company") and job_data.get("url"):
                jobs.append(
                    {
                        "company": job_data.get("company", "Unknown"),
                        "title": job_data.get("title", "New Grad Position"),
                        "location": job_data.get("location", "USA"),
                        "url": job_data["url"],
                        "date": job_data.get("date", ""),
                    }
                )

    return jobs


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_text(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "newgrad-alerts/1.0"})
    r.raise_for_status()
    return r.text


def looks_like_job_link(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in JOB_HOST_HINTS)


def categorize_job(job: Job) -> str | None:
    """Return category key if matches, with DATA checked first."""
    text = f"{job.company} {job.title} {job.location}".lower()
    for cat_key in ["data", "ai_ml", "software"]:
        cat = CATEGORIES[cat_key]
        if any(kw in text for kw in cat["keywords"]):
            return cat_key
    return None


def load_seen(path="seen_links.json") -> set[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen(seen: set[str], path="seen_links.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════


def build_email_html(
    categorized_jobs: dict[str, list[Job]], new_job_urls: set[str]
) -> str:
    """Build HTML email with tabular format and LinkedIn search sections."""

    today = datetime.now().strftime("%B %d, %Y")
    total_jobs = sum(len(jobs) for jobs in categorized_jobs.values())
    new_count = len(new_job_urls)

    # Build job sections (DATA FIRST)
    job_sections = ""
    category_order = ["data", "ai_ml", "software"]

    for cat_key in category_order:
        jobs = categorized_jobs.get(cat_key, [])
        if not jobs:
            continue

        cat = CATEGORIES[cat_key]
        new_in_category = sum(1 for j in jobs if j.url in new_job_urls)

        job_rows = ""
        for job in jobs:
            company_display = (
                job.company[:35] + "..." if len(job.company) > 35 else job.company
            )
            title_display = job.title[:55] + "..." if len(job.title) > 55 else job.title
            location_display = (
                job.location[:30] + "..." if len(job.location) > 30 else job.location
            )

            # Show days in your list (from first_seen) or posting age
            if job.first_seen:
                try:
                    seen_date = datetime.fromisoformat(job.first_seen).date()
                    days_in_list = (datetime.now().date() - seen_date).days
                    if days_in_list == 0:
                        date_display = "🆕 New!"
                    else:
                        date_display = f"Day {days_in_list + 1}"
                except ValueError:
                    date_display = job.date_posted or "Recent"
            elif job.days_ago is not None:
                if job.days_ago == 0:
                    date_display = "Today"
                elif job.days_ago == 1:
                    date_display = "1d ago"
                else:
                    date_display = f"{job.days_ago}d ago"
            else:
                date_display = job.date_posted or "Recent"

            # Highlight new jobs
            is_new = job.url in new_job_urls
            row_style = "background: #ecfdf5;" if is_new else ""
            new_badge = (
                '<span style="background: #10b981; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-left: 4px;">NEW</span>'
                if is_new
                else ""
            )

            job_rows += f"""
                <tr style="{row_style}">
                    <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; font-weight: 600; color: #1f2937;">
                        {company_display}{new_badge}
                    </td>
                    <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; color: #374151;">
                        {title_display}
                    </td>
                    <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; color: #6b7280; font-size: 13px;">
                        {location_display}
                    </td>
                    <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; text-align: center;">
                        {date_display}
                    </td>
                    <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: center;">
                        <a href="{job.url}" style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; padding: 6px 14px; border-radius: 6px; text-decoration: none; font-weight: 500; font-size: 12px;">
                            Apply
                        </a>
                    </td>
                </tr>
            """

        job_sections += f"""
            <div style="margin-bottom: 32px;">
                <h2 style="color: #1f2937; font-size: 20px; margin: 0 0 16px 0; padding-bottom: 8px; border-bottom: 2px solid #e5e7eb;">
                    {cat["emoji"]} {cat["title"]}
                    <span style="color: #6b7280; font-weight: normal;">({len(jobs)} jobs</span>
                    {f'<span style="color: #10b981; font-weight: 600;">, {new_in_category} new!</span>' if new_in_category else ''}
                    <span style="color: #6b7280; font-weight: normal;">)</span>
                </h2>
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 900px;">
                        <thead>
                            <tr style="background: #f9fafb;">
                                <th style="padding: 12px; text-align: left; font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb; font-size: 13px;">Company</th>
                                <th style="padding: 12px; text-align: left; font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb; font-size: 13px;">Job Title</th>
                                <th style="padding: 12px; text-align: left; font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb; font-size: 13px;">Location</th>
                                <th style="padding: 12px; text-align: center; font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb; font-size: 13px;">In List</th>
                                <th style="padding: 12px; text-align: center; font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb; font-size: 13px;">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {job_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        """

    # Build LinkedIn search sections by industry
    linkedin_sections = ""
    for section_data in LINKEDIN_SEARCHES.values():
        links = ""
        industry_ids = section_data.get("industry_ids")
        for search in section_data["searches"]:
            url = build_linkedin_search_url(
                search["query"], "entry_associate", industry_ids
            )
            links += f"""
                <a href="{url}" style="display: inline-block; background: #0a66c2; color: white; padding: 8px 14px; border-radius: 20px; text-decoration: none; font-size: 12px; margin: 3px;">
                    {search["emoji"]} {search["title"]}
                </a>
            """

        linkedin_sections += f"""
            <div style="margin-bottom: 16px;">
                <h4 style="color: #374151; margin: 0 0 8px 0; font-size: 14px;">{section_data["title"]}</h4>
                <div>{links}</div>
            </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
        <div style="max-width: 1100px; margin: 0 auto; padding: 20px;">

            <!-- Header -->
            <div style="background: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #06b6d4 100%); border-radius: 16px 16px 0 0; padding: 32px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">
                    🎯 New Grad Job Alert
                </h1>
                <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0; font-size: 16px;">
                    {today}
                </p>
            </div>

            <!-- Stats Banner -->
            <div style="background: white; padding: 20px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                <div style="display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 12px 24px; border-radius: 50px; font-size: 18px; font-weight: 600;">
                    ✨ {total_jobs} Opportunities | 🆕 {new_count} New Today!
                </div>
                <p style="color: #6b7280; margin: 10px 0 0 0; font-size: 13px;">
                    Jobs stay in your list for {ROLLING_WINDOW_DAYS} days so you don't miss any!
                </p>
            </div>

            <!-- Main Content -->
            <div style="background: #f9fafb; padding: 24px; border-radius: 0 0 16px 16px;">

                {job_sections}

                <!-- LinkedIn Quick Searches by Industry -->
                <div style="background: white; border-radius: 12px; padding: 24px; margin-top: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <h3 style="color: #1f2937; margin: 0 0 20px 0; font-size: 18px;">
                        🔍 LinkedIn Quick Searches <span style="color: #6b7280; font-weight: normal; font-size: 14px;">(Entry Level + 1-2 Years, Posted This Week)</span>
                    </h3>
                    {linkedin_sections}
                </div>

                <!-- Tips Section -->
                <div style="background: #fef3c7; border-radius: 12px; padding: 20px; margin-top: 24px; border-left: 4px solid #f59e0b;">
                    <h4 style="color: #92400e; margin: 0 0 8px 0; font-size: 16px;">💡 Pro Tips</h4>
                    <ul style="color: #78350f; margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.6;">
                        <li>🆕 NEW jobs are highlighted in green - apply to these first!</li>
                        <li>Jobs stay in your list for {ROLLING_WINDOW_DAYS} days, then drop off</li>
                        <li>Apply within 48 hours of posting for best results</li>
                        <li>Follow up on LinkedIn after applying</li>
                    </ul>
                </div>

            </div>

            <!-- Footer -->
            <div style="text-align: center; padding: 24px; color: #6b7280; font-size: 13px;">
                <p style="margin: 0;">
                    🚀 You got this! Good luck with your applications!
                </p>
                <p style="margin: 8px 0 0 0; color: #9ca3af;">
                    Automated job alerts • Data roles listed first • Rolling {ROLLING_WINDOW_DAYS}-day window
                </p>
            </div>

        </div>
    </body>
    </html>
    """

    return html


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL SENDING
# ═══════════════════════════════════════════════════════════════════════════════


def send_email(subject: str, html_body: str) -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_email = os.environ["TO_EMAIL"]
    cc_email = os.environ.get("CC_EMAIL", "")  # Optional: comma-separated CC addresses
    from_email = os.environ.get("FROM_EMAIL", smtp_user)
    from_name = os.environ.get("FROM_NAME", "Job Alerts")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f'"{from_name}" <{from_email}>'
    msg["To"] = to_email

    # Add CC if provided
    if cc_email:
        msg["Cc"] = cc_email

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Build recipient list (To + CC)
    recipients = [to_email]
    if cc_email:
        recipients.extend([addr.strip() for addr in cc_email.split(",")])

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, recipients, msg.as_string())


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    seen = load_seen()
    history = load_job_history()

    # Clean up old jobs from history (older than ROLLING_WINDOW_DAYS)
    history = cleanup_old_jobs(history, ROLLING_WINDOW_DAYS)

    # Track new jobs found in this run
    new_jobs: dict[str, list[Job]] = {"data": [], "ai_ml": [], "software": []}
    new_job_urls: set[str] = set()

    for src in SOURCES:
        try:
            text = fetch_text(src)
        except Exception as e:
            print(f"❌ Failed to fetch {src}: {e}")
            continue

        # Try both markdown and HTML table parsing
        parsed_jobs = parse_markdown_table(text)
        if len(parsed_jobs) == 0:
            # Try HTML table parsing (for SimplifyJobs)
            parsed_jobs = parse_html_table(text)

        print(f"📥 Parsed {len(parsed_jobs)} jobs from {src.split('/')[-1]}")

        # Debug: Print first 3 URLs to see what we're getting
        if parsed_jobs:
            print(f"   🔍 Sample URLs:")
            for job in parsed_jobs[:3]:
                print(f"      {job['url'][:80]}...")

        # Debug counters
        skipped_seen = 0
        skipped_not_job_link = 0
        skipped_too_old = 0
        skipped_no_category = 0
        added = 0

        for job_data in parsed_jobs:
            url = job_data["url"]

            if url in seen:
                skipped_seen += 1
                continue

            if not looks_like_job_link(url):
                skipped_not_job_link += 1
                continue

            days_ago = parse_date(job_data["date"])
            if not is_within_days(days_ago, MAX_JOB_AGE_DAYS):
                skipped_too_old += 1
                continue

            job = Job(
                company=job_data["company"],
                title=job_data["title"],
                location=job_data["location"],
                url=url,
                date_posted=job_data["date"],
                days_ago=days_ago,
            )

            category = categorize_job(job)
            if not category:
                skipped_no_category += 1
                continue

            new_jobs[category].append(job)
            new_job_urls.add(url)
            seen.add(url)
            added += 1

        # Print debug info
        print(
            f"   ✅ Added: {added} | ⏭️ Seen: {skipped_seen} | 🔗 Not job link: {skipped_not_job_link} | 📅 Too old: {skipped_too_old} | ❓ No category: {skipped_no_category}"
        )

        time.sleep(1)

    # Add new jobs to history
    history = add_jobs_to_history(history, new_jobs)

    # Build final job lists from history (ensuring minimum jobs per category)
    final_jobs: dict[str, list[Job]] = {}
    for category in ["data", "ai_ml", "software"]:
        final_jobs[category] = get_jobs_from_history(
            history, category, max(MIN_JOBS_PER_CATEGORY, len(new_jobs[category]))
        )

    # Sort by newest first (based on first_seen)
    for cat_key in final_jobs:
        final_jobs[cat_key].sort(key=lambda j: j.first_seen or "", reverse=True)

    total_jobs = sum(len(jobs) for jobs in final_jobs.values())
    new_count = len(new_job_urls)

    if total_jobs == 0:
        print("📭 No jobs in history. Run again after jobs are found.")
        return

    # Build counts for subject
    data_count = len(final_jobs["data"])
    swe_count = len(final_jobs["software"])
    ai_count = len(final_jobs["ai_ml"])

    # Build email
    html_body = build_email_html(final_jobs, new_job_urls)

    # Subject line
    if new_count > 0:
        subject = f"🎯 {new_count} New Jobs!💻 "
    else:
        subject = f"🎯 Daily Job Links 💻"

    send_email(subject=subject, html_body=html_body)
    save_seen(seen)
    save_job_history(history)

    print(f"✅ Emailed {total_jobs} jobs ({new_count} new)!")
    print(f"   📊 Data: {data_count} | 🤖 AI/ML: {ai_count} | 💻 SWE: {swe_count}")


if __name__ == "__main__":
    main()
