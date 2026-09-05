"""
sheet_reader.py — reads user profiles from Google Sheet (published as CSV).

How to set up your Google Sheet:
  1. Create a Google Sheet with the exact column headers below
  2. File → Share → Publish to web → Sheet1 → CSV → Publish
  3. Copy the published CSV URL into your GitHub Secret: SHEET_CSV_URL

Column headers (copy-paste this as Row 1 of your sheet):
  Timestamp | Full name | Email | Country code | City | Remote preference |
  Job title | Seniority | Skills | Employment type | Min salary | Max jobs per email |
  CV text | Cover letter | Digest frequency | Active
"""

import csv
import urllib.request
import os

SHEET_CSV_URL = os.environ.get("SHEET_CSV_URL", "")

COUNTRY_CONFIG = {
    "ie": {"name": "Ireland",       "currency": "EUR", "adzuna_code": "ie"},
    "gb": {"name": "United Kingdom","currency": "GBP", "adzuna_code": "gb"},
    "us": {"name": "United States", "currency": "USD", "adzuna_code": "us"},
    "in": {"name": "India",         "currency": "INR", "adzuna_code": "in"},
    "de": {"name": "Germany",       "currency": "EUR", "adzuna_code": "de"},
    "fr": {"name": "France",        "currency": "EUR", "adzuna_code": "fr"},
    "au": {"name": "Australia",     "currency": "AUD", "adzuna_code": "au"},
    "ca": {"name": "Canada",        "currency": "CAD", "adzuna_code": "ca"},
    "nz": {"name": "New Zealand",   "currency": "NZD", "adzuna_code": "nz"},
    "za": {"name": "South Africa",  "currency": "ZAR", "adzuna_code": "za"},
    "pl": {"name": "Poland",        "currency": "PLN", "adzuna_code": "pl"},
    "br": {"name": "Brazil",        "currency": "BRL", "adzuna_code": "br"},
}

def load_users():
    """
    Fetches all active user profiles from the published Google Sheet CSV.
    Returns a list of user dicts, one per row.
    """
    if not SHEET_CSV_URL:
        print("[sheet] No SHEET_CSV_URL set — loading sample user for testing")
        return [_sample_user()]

    print(f"[sheet] Fetching user profiles...")
    try:
        req = urllib.request.Request(
            SHEET_CSV_URL,
            headers={"User-Agent": "JobHunterBot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read().decode("utf-8")
    except Exception as e:
        print(f"[sheet] Failed to fetch sheet: {e}")
        return []

    users = []
    reader = csv.DictReader(content.splitlines())
    for row in reader:
        active = row.get("Active", "yes").strip().lower()
        if active in ("no", "false", "0", "inactive", "pause"):
            continue

        country_code = row.get("Country code", "ie").strip().lower()
        country_info = COUNTRY_CONFIG.get(country_code, COUNTRY_CONFIG["ie"])

        skills_raw = row.get("Skills", "").strip()
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()]

        max_jobs = int(row.get("Max jobs per email", "10").strip() or 10)
        min_salary_raw = row.get("Min salary", "").strip()
        min_salary = int(min_salary_raw) if min_salary_raw.isdigit() else 0

        user = {
            "name":            row.get("Full name", "").strip(),
            "email":           row.get("Email", "").strip(),
            "country_code":    country_code,
            "country_name":    country_info["name"],
            "currency":        country_info["currency"],
            "adzuna_code":     country_info["adzuna_code"],
            "city":            row.get("City", "").strip(),
            "remote_pref":     row.get("Remote preference", "Remote OK").strip(),
            "job_title":       row.get("Job title", "").strip(),
            "seniority":       row.get("Seniority", "mid").strip().lower(),
            "skills":          skills,
            "employment_type": row.get("Employment type", "Permanent").strip(),
            "min_salary":      min_salary,
            "max_jobs":        max_jobs,
            "cv_text":         row.get("CV text", "").strip(),
            "cover_letter":    row.get("Cover letter", "").strip(),
            "digest_freq":     row.get("Digest frequency", "Daily at 8 AM").strip(),
        }

        if user["email"] and user["job_title"]:
            users.append(user)

    print(f"[sheet] Loaded {len(users)} active user(s)")
    return users


def _sample_user():
    """Returns a sample user for local testing without a real sheet."""
    return {
        "name":            "Rohan Ajila",
        "email":           os.environ.get("NOTIFY_EMAIL", "test@test.com"),
        "country_code":    "ie",
        "country_name":    "Ireland",
        "currency":        "EUR",
        "adzuna_code":     "ie",
        "city":            "Dublin",
        "remote_pref":     "Remote OK",
        "job_title":       "Software Engineer",
        "seniority":       "mid",
        "skills":          ["React", "Node.js", "TypeScript", "C#", ".NET", "Azure"],
        "employment_type": "Permanent",
        "min_salary":      75000,
        "max_jobs":        10,
        "cv_text":         "Software Engineer with 5 years experience in fintech and payments.",
        "cover_letter":    "",
        "digest_freq":     "Daily at 8 AM",
    }


def build_search_terms(user):
    """
    Generates a list of search queries tailored to this user's profile.
    Used by every ATS scraper and Adzuna.
    """
    title = user["job_title"]
    skills = user["skills"][:5]

    terms = [title]

    skill_terms = [f"{s} developer" for s in skills if len(s) > 2]
    terms.extend(skill_terms[:4])

    seniority_map = {
        "junior": ["junior", "graduate", "entry level"],
        "mid":    ["mid-level", "software engineer", "developer"],
        "senior": ["senior", "lead"],
        "lead":   ["lead", "principal", "staff engineer", "engineering manager"],
    }
    level_terms = seniority_map.get(user["seniority"], [])
    for lt in level_terms[:2]:
        terms.append(f"{lt} {title}")

    seen = set()
    unique = []
    for t in terms:
        key = t.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique[:8]


def build_location_filters(user):
    """
    Returns location strings to match against job location fields.
    Covers the user's city, country name, and remote variants.
    """
    filters = [
        user["city"].lower(),
        user["country_name"].lower(),
        user["country_code"].lower(),
    ]

    remote_pref = user["remote_pref"].lower()
    if "remote" in remote_pref:
        filters.extend(["remote", "anywhere", "worldwide", "global"])
    if "hybrid" in remote_pref:
        filters.append("hybrid")

    country_aliases = {
        "ie": ["ireland", "dublin", "cork", "galway", "limerick"],
        "us": ["united states", "usa", "new york", "san francisco", "seattle", "austin", "remote"],
        "in": ["india", "bangalore", "bengaluru", "mumbai", "hyderabad", "pune", "delhi", "chennai"],
        "gb": ["united kingdom", "uk", "london", "manchester", "edinburgh", "bristol"],
        "de": ["germany", "berlin", "munich", "hamburg", "frankfurt"],
        "au": ["australia", "sydney", "melbourne", "brisbane", "perth"],
        "ca": ["canada", "toronto", "vancouver", "montreal", "ottawa"],
    }
    extras = country_aliases.get(user["country_code"], [])
    filters.extend(extras)

    return list(set(filters))


if __name__ == "__main__":
    users = load_users()
    for u in users:
        print(f"\n--- {u['name']} ({u['email']}) ---")
        print(f"  Location: {u['city']}, {u['country_name']} ({u['currency']})")
        print(f"  Looking for: {u['seniority']} {u['job_title']}")
        print(f"  Skills: {', '.join(u['skills'])}")
        print(f"  Search terms: {build_search_terms(u)}")
        print(f"  Location filters: {build_location_filters(u)}")
