"""
ats_scraper.py — dynamic ATS scraper for any location, any job title.

Sources (in priority order):
  1. Greenhouse  — 20,000+ companies, public JSON API
  2. Lever       — 10,000+ companies, public JSON API
  3. Ashby       — fast-growing startups, public API (covers Naukri for India)
  4. Workday     — enterprise (Microsoft, Oracle, SAP), POST search API
  5. SmartRecruiters — Visa, IKEA etc., public search API
  6. BambooHR    — SMBs globally, per-slug API

All scrapers take a user dict and return a list of normalised job dicts.
Normalised job schema:
  title, company, url, location, description, posted, salary, source, priority
"""

import json
import time
import urllib.request
import urllib.parse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from sheet_reader import build_search_terms, build_location_filters

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

SENIORITY_INCLUDE = {
    "junior": ["junior", "graduate", "grad", "entry", "associate", "jr"],
    "mid":    ["engineer", "developer", "dev", "mid", "software", "full stack",
               "fullstack", "backend", "frontend", "sde", "swe"],
    "senior": ["senior", "sr.", "sr ", "lead", "staff", "principal", "architect",
               "engineer", "developer"],
    "lead":   ["lead", "principal", "staff", "manager", "head", "director",
               "architect", "vp", "engineer"],
}

SENIORITY_EXCLUDE = {
    "junior": ["senior", "sr.", "lead", "principal", "staff", "director", "vp", "head"],
    "mid":    ["intern", "internship", "graduate program", "director", "vp", "head of"],
    "senior": ["intern", "internship", "graduate program", "director", "vp", "head of"],
    "lead":   ["intern", "internship", "graduate program"],
}

def fetch(url, method="GET", data=None, timeout=15):
    try:
        body = json.dumps(data).encode() if data else None
        req  = urllib.request.Request(url, data=body, headers={
            **HEADERS,
            **({"Content-Type": "application/json"} if data else {})
        }, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return None

def normalise(title, company, url, location, desc="", posted="", salary="", source="", priority=1):
    return {
        "title":    title.strip(),
        "company":  company.strip(),
        "url":      url.strip(),
        "location": location.strip(),
        "desc":     desc.strip()[:400],
        "posted":   posted.strip(),
        "salary":   salary.strip(),
        "source":   source,
        "priority": priority,
    }

def location_matches(job_location, loc_filters):
    loc = job_location.lower()
    return any(f in loc for f in loc_filters) or not loc

def seniority_ok(title, seniority):
    t = title.lower()
    include = SENIORITY_INCLUDE.get(seniority, [])
    exclude = SENIORITY_EXCLUDE.get(seniority, [])
    if exclude and any(e in t for e in exclude):
        return False
    return True

def score_job(job, user):
    """Score a job 0–100 based on match with user profile."""
    score = 50
    title = job["title"].lower()
    desc  = job["desc"].lower()
    combined = title + " " + desc

    job_title = user["job_title"].lower()
    if job_title in title:
        score += 20
    elif any(w in title for w in job_title.split()):
        score += 10

    skill_hits = sum(1 for s in user["skills"] if s.lower() in combined)
    score += min(skill_hits * 5, 25)

    if user["min_salary"] and job.get("salary"):
        try:
            nums = re.findall(r'\d[\d,]+', job["salary"])
            if nums:
                low = int(nums[0].replace(",", ""))
                if low >= user["min_salary"]:
                    score += 5
        except Exception:
            pass

    return min(score, 100)


# ── GREENHOUSE ────────────────────────────────────────────────────────────────

GH_COMPANIES = [
    "stripe","hubspot","intercom","zendesk","figma","notion","ramp","brex",
    "checkr","rippling","lattice","gusto","chime","plaid","coinbase","robinhood",
    "gitlab","hashicorp","netlify","vercel","cloudflare","datadog","segment",
    "mixpanel","amplitude","pagerduty","snyk","1password","airtable","asana",
    "calendly","canva","carta","carta","clio","confluent","databricks","deel",
    "discord","doordash","dropbox","duolingo","epic","faire","fenergo","flexport",
    "github","gong","greenhouse","grubhub","handshake","heap","hotjar","hubspot",
    "instacart","intercom","ironclad","jasper","klaviyo","knock","loom","lyft",
    "mailchimp","managed","marqeta","matterport","melio","mercury","modern",
    "mongodb","mparticle","netsuite","notion","navan","okta","opendoor","outreach",
    "papaya","persona","posthog","postman","productboard","qualified","recurly",
    "recharge","remote","retool","rippling","salesforce","sapling","sentry",
    "shipbob","shortcut","slab","slack","snyk","sourcegraph","square","squarespace",
    "stripe","superhuman","thoughtworks","tipalti","toast","tonal","typeform",
    "underdog","vanta","vercel","verkada","vouch","waymo","webflow","whimsical",
    "workato","workhuman","teamwork","zapier","zendesk","zoom",
]

def scrape_greenhouse(user):
    jobs = []
    loc_filters = build_location_filters(user)
    terms = build_search_terms(user)

    def fetch_company(slug):
        data = fetch(f"https://api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
        if not data:
            return []
        found = []
        for r in data.get("jobs", []):
            title = r.get("title", "")
            loc   = r.get("location", {}).get("name", "")
            url   = r.get("absolute_url", "")
            desc  = re.sub(r'<[^>]+>', ' ', r.get("content", ""))[:400]
            if (location_matches(loc, loc_filters) and
                seniority_ok(title, user["seniority"]) and
                any(t.lower().split()[0] in title.lower() for t in terms[:3])):
                found.append(normalise(title, slug.title(), url, loc, desc, source="Greenhouse", priority=1))
        return found

    with ThreadPoolExecutor(max_workers=30) as ex:
        futures = {ex.submit(fetch_company, s): s for s in GH_COMPANIES}
        for f in as_completed(futures):
            try:
                jobs.extend(f.result())
            except Exception:
                pass

    print(f"  [Greenhouse] {len(jobs)} matching job(s)")
    return jobs


# ── LEVER ─────────────────────────────────────────────────────────────────────

LEVER_COMPANIES = [
    "revolut","scale","anthropic","notion","figma","benchling","brex","census",
    "chainalysis","checkr","chime","chord","chronicle","circle","clickup",
    "close","cockroachdb","coinbase","contentful","cube","dbt","deepgram",
    "deel","descope","descript","dialpad","digit","discord","dremio","dropbox",
    "dwolla","easypost","elastic","fenergo","flatiron","flexport","fountain",
    "gem","genome","gopuff","gov2go","grafana","grindr","gusto","harbor",
    "headway","heap","herald","hootsuite","humanloop","hunter","incode",
    "ironclad","iterable","jeli","jellyfish","jumpcloud","kata","khoros",
    "kion","klaviyo","klarity","limeade","lob","lokalise","loop","lucid",
    "lunchclub","lyric","mattermost","maxwell","maze","medable","mercury",
    "miro","modern","momentive","moveworks","mutiny","mynd","netlify","netsol",
    "newfront","nextdoor","noogata","norm","numerator","nuro","nylas","olo",
    "ontic","openphone","opentable","orbit","outreach","overmind","pagerduty",
    "papaya","pathlight","patriarch","pave","personio","pilot","pipeline",
    "plaid","platform","playground","plenty","podium","prefect","privy",
    "productboard","productiv","prophet","prose","puppet","pushpay","qualified",
    "ramp","ray","recharge","recurly","redfin","replit","retool","ridge",
    "ridgeline","ripple","roam","rockset","runway","segment","sendbird","sentry",
    "shortcut","silverfort","slab","slice","sourcegraph","sprig","square",
    "squarespace","stackhawk","staffbase","stord","streamyard","sublime",
    "superhuman","syndigo","tailscale","tandem","tapcart","taxjar","together",
    "tooljet","trackunit","trained","tray","tremendous","trueaccord","truework",
    "tuva","twilio","ultra","unqork","usermind","vanta","varicent","vendr",
    "veritone","vetcove","via","vidyard","vimeo","vise","voyager","watershed",
    "waymark","webflow","wefunder","whoop","wisely","wonder","workato","workvivo",
    "x0pa","xactly","yotpo","yteam","zapier","zenput","zippier","zuora",
]

def scrape_lever(user):
    jobs = []
    loc_filters = build_location_filters(user)
    terms = build_search_terms(user)

    def fetch_company(slug):
        data = fetch(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        if not isinstance(data, list):
            return []
        found = []
        for r in data:
            title = r.get("text", "")
            loc   = r.get("categories", {}).get("location", "")
            url   = r.get("hostedUrl", "")
            desc  = r.get("descriptionPlain", "")[:400]
            if (location_matches(loc, loc_filters) and
                seniority_ok(title, user["seniority"]) and
                any(t.lower().split()[0] in title.lower() for t in terms[:3])):
                found.append(normalise(title, slug.title(), url, loc, desc, source="Lever", priority=1))
        return found

    with ThreadPoolExecutor(max_workers=30) as ex:
        futures = {ex.submit(fetch_company, s): s for s in LEVER_COMPANIES}
        for f in as_completed(futures):
            try:
                jobs.extend(f.result())
            except Exception:
                pass

    print(f"  [Lever] {len(jobs)} matching job(s)")
    return jobs


# ── ASHBY ────────────────────────────────────────────────────────────────────

def scrape_ashby(user):
    """Ashby has a single search endpoint that covers all companies."""
    jobs = []
    loc_filters = build_location_filters(user)
    terms = build_search_terms(user)

    for term in terms[:4]:
        payload = {"jobPostingTitleSearch": term, "locationSearch": user["city"]}
        data = fetch(
            "https://jobs.ashbyhq.com/api/non-user-facing/job-board/job-postings",
            method="POST", data=payload
        )
        if not data:
            continue
        for r in (data.get("jobPostings") or []):
            title   = r.get("title", "")
            company = r.get("organizationName", "")
            loc     = r.get("primaryLocationDisplayText", "")
            url     = f"https://jobs.ashbyhq.com/{r.get('boardName','')}/{r.get('id','')}"
            if (location_matches(loc, loc_filters) and
                seniority_ok(title, user["seniority"])):
                jobs.append(normalise(title, company, url, loc, source="Ashby", priority=1))
        time.sleep(0.3)

    print(f"  [Ashby] {len(jobs)} matching job(s)")
    return jobs


# ── SMARTRECRUITERS ───────────────────────────────────────────────────────────

def scrape_smartrecruiters(user):
    jobs = []
    loc_filters = build_location_filters(user)
    terms = build_search_terms(user)

    for term in terms[:3]:
        params = urllib.parse.urlencode({
            "q": term,
            "country": user["country_code"].upper(),
            "limit": 100,
        })
        data = fetch(f"https://jobs.smartrecruiters.com/CompanySearch/search?{params}")
        if not data:
            continue
        for r in (data.get("content") or []):
            title   = r.get("name", "")
            company = r.get("company", {}).get("name", "")
            loc     = r.get("location", {}).get("city", "")
            url     = r.get("ref", "")
            if seniority_ok(title, user["seniority"]) and location_matches(loc, loc_filters):
                jobs.append(normalise(title, company, url, loc, source="SmartRecruiters", priority=1))
        time.sleep(0.3)

    print(f"  [SmartRecruiters] {len(jobs)} matching job(s)")
    return jobs


# ── ADZUNA (fallback) ─────────────────────────────────────────────────────────

def scrape_adzuna(user, app_id, app_key):
    if not app_id or not app_key:
        return []
    jobs = []
    terms = build_search_terms(user)
    country = user["adzuna_code"]

    for term in terms[:5]:
        params = urllib.parse.urlencode({
            "app_id":           app_id,
            "app_key":          app_key,
            "results_per_page": 50,
            "what":             term,
            "where":            user["city"],
            "sort_by":          "date",
            "max_days_old":     1,
        })
        url  = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?{params}"
        data = fetch(url)
        if not data:
            continue
        for r in (data.get("results") or []):
            title   = r.get("title", "").strip()
            company = r.get("company", {}).get("display_name", "")
            link    = r.get("redirect_url", "")
            loc     = r.get("location", {}).get("display_name", user["city"])
            desc    = r.get("description", "")[:400]
            sal_min = r.get("salary_min")
            sal_max = r.get("salary_max")
            salary  = f"{user['currency']} {int(sal_min):,}–{int(sal_max):,}" if sal_min and sal_max else ""
            created = r.get("created", "")
            if seniority_ok(title, user["seniority"]):
                jobs.append(normalise(title, company, link, loc, desc, created, salary, "Adzuna", priority=3))
        time.sleep(0.2)

    print(f"  [Adzuna] {len(jobs)} matching job(s)")
    return jobs


# ── MASTER RUNNER ─────────────────────────────────────────────────────────────

def scrape_all_for_user(user, adzuna_app_id="", adzuna_app_key=""):
    """
    Runs all scrapers for a single user and returns deduplicated,
    scored, sorted job list capped at user's max_jobs preference.
    """
    print(f"\n  Scraping jobs for {user['name']} ({user['city']}, {user['country_name']})")
    all_jobs = []

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [
            ex.submit(scrape_greenhouse,      user),
            ex.submit(scrape_lever,           user),
            ex.submit(scrape_ashby,           user),
            ex.submit(scrape_smartrecruiters, user),
        ]
        for f in as_completed(futures):
            try:
                all_jobs.extend(f.result())
            except Exception as e:
                print(f"    Scraper error: {e}")

    adzuna_jobs = scrape_adzuna(user, adzuna_app_id, adzuna_app_key)
    all_jobs.extend(adzuna_jobs)

    seen_keys = set()
    unique = []
    for j in all_jobs:
        key = f"{j['title'].lower()}|{j['company'].lower()}"
        if key not in seen_keys:
            seen_keys.add(key)
            j["score"] = score_job(j, user)
            unique.append(j)

    unique.sort(key=lambda j: (j["priority"], -j["score"]))

    top = unique[:user["max_jobs"]]
    print(f"  Total: {len(unique)} unique jobs → top {len(top)} selected")
    return top
