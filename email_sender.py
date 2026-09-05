"""
email_sender.py — builds and sends a personalised email digest per user.

Each email contains:
  - Job listings ranked by match score
  - For the top 3: inline tailored CV + cover letter the user can copy-paste
  - Source badges (company portal / LinkedIn / Adzuna)
  - Salary info where available
"""

import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "")

SOURCE_COLORS = {
    "Greenhouse":      ("#1e40af", "#dbeafe"),
    "Lever":           ("#6d28d9", "#ede9fe"),
    "Ashby":           ("#065f46", "#d1fae5"),
    "SmartRecruiters": ("#92400e", "#fef3c7"),
    "Adzuna":          ("#374151", "#f3f4f6"),
}

def badge(source):
    fg, bg = SOURCE_COLORS.get(source, ("#374151", "#f3f4f6"))
    return (f"<span style='background:{bg};color:{fg};font-size:11px;"
            f"padding:3px 9px;border-radius:12px;font-weight:500'>{source}</span>")

def score_bar(score):
    color = "#166534" if score >= 75 else "#92400e" if score >= 50 else "#374151"
    bg    = "#dcfce7" if score >= 75 else "#fef3c7" if score >= 50 else "#f3f4f6"
    return (f"<span style='background:{bg};color:{color};font-size:11px;"
            f"padding:3px 9px;border-radius:12px'>{score}% match</span>")

def cv_section(job):
    if not job.get("tailored_cv"):
        return ""
    return f"""
    <div style="margin-top:16px;background:#f8fafc;border-left:3px solid #378ADD;
                border-radius:0 8px 8px 0;padding:14px 16px">
      <p style="font-size:12px;font-weight:600;color:#1e40af;margin:0 0 8px;
                text-transform:uppercase;letter-spacing:.04em">
        Tailored CV for this role
      </p>
      <pre style="font-size:12px;color:#374151;white-space:pre-wrap;
                  font-family:Georgia,serif;line-height:1.6;margin:0">{job['tailored_cv']}</pre>
    </div>"""

def cover_letter_section(job):
    if not job.get("cover_letter"):
        return ""
    return f"""
    <div style="margin-top:12px;background:#f0fdf4;border-left:3px solid #16a34a;
                border-radius:0 8px 8px 0;padding:14px 16px">
      <p style="font-size:12px;font-weight:600;color:#166534;margin:0 0 8px;
                text-transform:uppercase;letter-spacing:.04em">
        Cover letter
      </p>
      <pre style="font-size:12px;color:#374151;white-space:pre-wrap;
                  font-family:Georgia,serif;line-height:1.6;margin:0">{job['cover_letter']}</pre>
    </div>"""

def job_card(job, idx):
    sal   = (f"<span style='background:#fefce8;color:#92400e;font-size:11px;"
             f"padding:3px 9px;border-radius:12px'>{job['salary']}</span>") if job.get("salary") else ""
    desc  = (f"<p style='margin:8px 0 0;font-size:13px;color:#6b7280;"
             f"line-height:1.5'>{job['desc']}…</p>") if job.get("desc") else ""
    top3_label = (" <span style='background:#dbeafe;color:#1e40af;font-size:10px;"
                  "padding:2px 7px;border-radius:8px;margin-left:6px'>Top pick — CV + letter below</span>"
                  if idx < 3 and (job.get("tailored_cv") or job.get("cover_letter")) else "")

    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
                padding:16px 18px;margin-bottom:12px">
      <a href="{job['url']}" target="_blank"
         style="font-size:15px;font-weight:600;color:#111827;text-decoration:none">
        {job['title']}{top3_label}
      </a>
      <p style="margin:3px 0 0;font-size:13px;color:#6b7280">
        {job['company']} &nbsp;·&nbsp; {job['location']}
      </p>
      <div style="margin:8px 0 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
        {badge(job.get('source',''))}
        {score_bar(job.get('score', 50))}
        {sal}
      </div>
      {desc}
      {cv_section(job)}
      {cover_letter_section(job)}
    </div>"""

def build_email(user, jobs, run_date):
    job_cards_html = "".join(job_card(j, i) for i, j in enumerate(jobs))
    empty = ("<p style='color:#9ca3af;text-align:center;padding:2rem'>"
             "No new matching jobs today. Check back tomorrow!</p>")

    return f"""
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                 max-width:660px;margin:0 auto;padding:24px 16px;background:#f9fafb">

      <div style="background:#fff;border-radius:12px;padding:24px;
                  margin-bottom:20px;border:1px solid #e5e7eb">
        <p style="margin:0 0 2px;font-size:13px;color:#9ca3af">{run_date}</p>
        <h1 style="margin:0 0 4px;font-size:22px;font-weight:700;color:#111827">
          Hi {user['name'].split()[0]}, here are your jobs
        </h1>
        <p style="margin:0;font-size:13px;color:#9ca3af">
          {len(jobs)} matching roles in {user['city']}, {user['country_name']}
          &nbsp;·&nbsp; {user['job_title']} &nbsp;·&nbsp; {user['seniority'].title()} level
        </p>
      </div>

      {job_cards_html if jobs else empty}

      <p style="text-align:center;font-size:12px;color:#d1d5db;margin-top:24px">
        Your job tracker · running daily · 
        reply "unsubscribe" to stop
      </p>
    </body>
    </html>"""

def send_to_user(user, jobs, run_date):
    if not GMAIL_USER or not GMAIL_PASS:
        print(f"  [email] No Gmail credentials — skipping {user['name']}")
        return

    html = build_email(user, jobs, run_date)
    msg  = MIMEMultipart("alternative")
    msg["Subject"] = (f"[Jobs] {len(jobs)} roles for you in {user['city']} — {run_date}"
                      if jobs else f"[Jobs] No new roles today — {run_date}")
    msg["From"]    = GMAIL_USER
    msg["To"]      = user["email"]
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, user["email"], msg.as_string())
        print(f"  [email] Sent to {user['name']} ({user['email']}) — {len(jobs)} jobs")
    except Exception as e:
        print(f"  [email] Failed for {user['name']}: {e}")

def send_all(users_with_jobs, run_date):
    for user, jobs in users_with_jobs:
        send_to_user(user, jobs, run_date)
