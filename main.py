"""
main.py — orchestrator for the global job hunting platform.

Run order:
  1. Load all users from Google Sheet
  2. For each user: scrape ATS platforms filtered to their location + role
  3. Score and rank jobs per user
  4. AI-tailor CV + cover letter for top 3 matches
  5. Send personalised email digest
  6. Save seen jobs cache so no duplicates tomorrow
"""

import os
import json
import hashlib
import datetime

from sheet_reader import load_users
from ats_scraper   import scrape_all_for_user
from ai_tailor     import tailor_top_jobs
from email_sender  import send_all

ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")
SEEN_FILE      = "seen_jobs.json"

def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def job_hash(job):
    raw = f"{job['title'].lower()}|{job['company'].lower()}|{job['url']}"
    return hashlib.md5(raw.encode()).hexdigest()

def filter_seen(jobs, seen):
    new, new_ids = [], set()
    for j in jobs:
        jid = job_hash(j)
        if jid not in seen and jid not in new_ids:
            j["id"] = jid
            new.append(j)
            new_ids.add(jid)
    return new, new_ids

def main():
    run_date = datetime.datetime.now(datetime.UTC).strftime("%d %b %Y")
    print(f"\n{'='*60}")
    print(f"  Global Job Hunter — {run_date}")
    print(f"{'='*60}")

    users = load_users()
    if not users:
        print("[main] No users found — exiting.")
        return

    seen = load_seen()
    print(f"[main] {len(seen)} jobs in seen cache\n")

    all_seen_ids = set()
    results = []

    for user in users:
        print(f"\n[user] {user['name']} · {user['job_title']} · {user['city']}, {user['country_name']}")

        raw_jobs = scrape_all_for_user(user, ADZUNA_APP_ID, ADZUNA_APP_KEY)

        new_jobs, new_ids = filter_seen(raw_jobs, seen)
        all_seen_ids.update(new_ids)

        print(f"  → {len(raw_jobs)} total, {len(new_jobs)} new (not seen before)")

        tailored = tailor_top_jobs(user, new_jobs, top_n=3)

        results.append((user, tailored))

    seen.update(all_seen_ids)
    save_seen(seen)
    print(f"\n[cache] Saved {len(seen)} total seen jobs")

    print(f"\n[email] Sending digests...")
    send_all(results, run_date)

    print(f"\n{'='*60}")
    print(f"  Done — {len(users)} user(s) processed")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
