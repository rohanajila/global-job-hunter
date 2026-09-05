"""
ai_tailor.py — calls Claude API to tailor CV and write cover letter.

For the top N jobs per user, generates:
  1. A tailored version of their CV highlighting relevant experience
  2. A personalised cover letter for that specific job + company

Uses claude-sonnet-4-6 via the Anthropic API.
~$0.01–0.03 per user per day for 3 tailored applications.
"""

import os
import json
import urllib.request

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2000

def call_claude(prompt, system="You are an expert career coach and CV writer."):
    if not ANTHROPIC_API_KEY:
        return "[Claude API key not set — skipping AI tailoring]"
    payload = json.dumps({
        "model":      MODEL,
        "max_tokens": MAX_TOKENS,
        "system":     system,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode()
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data["content"][0]["text"].strip()
    except Exception as e:
        return f"[AI tailoring failed: {e}]"


def tailor_cv(user, job):
    """
    Rewrites the user's CV to highlight skills and experience most
    relevant to this specific job.
    """
    prompt = f"""You are helping {user['name']} tailor their CV for a specific job application.

JOB DETAILS:
- Title: {job['title']}
- Company: {job['company']}
- Location: {job['location']}
- Description: {job['desc']}

USER'S CURRENT CV:
{user['cv_text']}

USER'S KEY SKILLS: {', '.join(user['skills'])}

TASK:
Rewrite the CV to be perfectly tailored for this role. Follow these rules:
1. Keep all facts truthful — don't invent experience that isn't there
2. Reorder bullet points so the most relevant experience appears first
3. Mirror the language and keywords from the job description naturally
4. Highlight achievements that directly match what the role needs
5. Keep the same structure and length as the original
6. Use plain text format (no markdown headers, no asterisks)

Return ONLY the tailored CV text, nothing else."""

    return call_claude(prompt)


def write_cover_letter(user, job):
    """
    Writes a personalised, human-sounding cover letter for this job.
    """
    style_note = ""
    if user["cover_letter"]:
        style_note = f"""
Use the following as a style and tone reference (this is the user's existing cover letter):
{user['cover_letter'][:800]}
"""

    prompt = f"""Write a cover letter for {user['name']} applying to the following role.

JOB DETAILS:
- Title: {job['title']}
- Company: {job['company']}
- Location: {job['location']}
- Job description: {job['desc']}

USER BACKGROUND (from their CV):
{user['cv_text'][:1200]}

USER'S KEY SKILLS: {', '.join(user['skills'])}
{style_note}

REQUIREMENTS:
- 3 short paragraphs, under 250 words total
- Warm, direct, human tone — not corporate or stiff
- Paragraph 1: why this specific company and role excites them (be specific)
- Paragraph 2: one concrete achievement from their background that directly maps to the role
- Paragraph 3: brief close, expressing interest in a conversation
- No "Dear Hiring Manager" — start with "Hi [Company] team," or similar
- No buzzwords like "leverage", "synergy", "passionate about"
- End with: {user['name']}

Return ONLY the cover letter text, nothing else."""

    return call_claude(prompt)


def tailor_top_jobs(user, jobs, top_n=3):
    """
    For the top N jobs, generates tailored CV and cover letter.
    Returns the jobs list with 'tailored_cv' and 'cover_letter' fields added.
    """
    if not ANTHROPIC_API_KEY:
        print(f"  [AI] No API key — skipping tailoring for {user['name']}")
        for j in jobs:
            j["tailored_cv"] = ""
            j["cover_letter"] = ""
        return jobs

    print(f"  [AI] Tailoring top {min(top_n, len(jobs))} jobs for {user['name']}...")
    for i, job in enumerate(jobs):
        if i < top_n:
            print(f"    Tailoring: {job['title']} at {job['company']}")
            job["tailored_cv"]    = tailor_cv(user, job)
            job["cover_letter"]   = write_cover_letter(user, job)
        else:
            job["tailored_cv"]    = ""
            job["cover_letter"]   = ""

    return jobs
