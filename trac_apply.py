"""
NHS Trac Auto-Application Script
Dr. Nermeen Hassan - GMC 7771612
Uses Playwright to fill and submit Trac applications automatically.
Triggered by job URL, generates Template 2 supporting info via Gemini (free),
submits application, and sends Telegram confirmation.
"""

import os
import sys
import asyncio
import requests
from google import genai
from playwright.async_api import async_playwright

# ── Secrets (set in GitHub Actions Secrets) ───────────────────────────────────
TRAC_EMAIL       = os.environ["TRAC_EMAIL"]
TRAC_PASSWORD    = os.environ["TRAC_PASSWORD"]
GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ── Configure Gemini ──────────────────────────────────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY)

# ── Job title blocklist (skip consultant/senior grade posts) ──────────────────
EXCLUDE_TITLES = [
    "consultant", "associate specialist", "specialty doctor",
    "staff grade", "registrar", "spr", "gp principal",
    "gp partner", "clinical director", "medical director",
    "anaesthe", "anaesth", "surgeon", "surgery"
]

def is_excluded_job(title: str) -> bool:
    title_lower = title.lower()
    return any(word in title_lower for word in EXCLUDE_TITLES)

# ── CV & Profile ──────────────────────────────────────────────────────────────
CV_PROFILE = """
Name: Dr. Nermeen Hassan
GMC Number: 7771612
Qualifications: MBChB Mansoura University 2019, PLAB1, PLAB2, GMC registered January 2024
ALS certified. Train the Healthcare Trainer (NHSE 2025). GCP (NIHR, enrolled).
Critical Appraisal course (NHS England). Co-author Cureus peer-reviewed publication
(PMID: 41064803) on spirometry in asthmatic patients.

CLINICAL EXPERIENCE:
1. Clinical Attachment - Diabetes & Endocrinology / Stroke / AAU, Bedford Hospital
   September - November 2024
   - Clerked and presented patients on ward rounds in Diabetes & Endocrinology and Stroke units
   - Participated in AAU acute assessments, TTOs, discharge summaries
   - Used ICE and NerveCentre systems
   - Attended MDT meetings and contributed to patient management discussions

2. Clinical Attachment - Acute Medicine, Bedford Hospital
   February 2025
   - Acute medical take, clerking undifferentiated presentations
   - Worked alongside registrars and consultants in a busy AMU setting
   - Further consolidation of ICE/NerveCentre and NHS documentation standards

3. Transfusion Medicine Specialty Training - Egyptian Fellowship
   National Blood Bank, Egypt, 2020-2021
   - Specialist training in blood transfusion, haemovigilance, and blood product management
   - Completed Egyptian Fellowship in Transfusion Medicine

4. GP and Unit Management, Egypt (2019-2022)
   - GP-level consultations across a broad range of presentations
   - Managed a clinical unit overseeing a team of 22+ staff
   - Experience in patient triage, chronic disease management, referrals

SPECIALTY BRIDGES:
- Acute Medicine / AAU: Bedford AMU attachment, acute clerking, undifferentiated presentations
- Diabetes & Endocrinology: Bedford D&E attachment, chronic disease management
- Stroke: Bedford Stroke unit, MDT, rehabilitation pathway
- Haematology: Transfusion Medicine fellowship, blood product expertise
- Respiratory: Spirometry research (Cureus publication), AAU respiratory presentations
- Care of the Elderly: Stroke and AAU exposure, MDT working
- GP: Egyptian GP experience, broad primary care base

RESEARCH & AUDIT:
- Co-author: Spirometry parameters in asthmatic patients, Cureus journal (PMID: 41064803)
- GCP training (NIHR) - ongoing
- Critical Appraisal course (NHS England) completed

TEACHING & LEADERSHIP:
- Train the Healthcare Trainer certificate (NHSE 2025)
- Unit management: led team of 22+ staff in Egypt
- Committed to undergraduate and postgraduate teaching within NHS MDT

VALUES: Patient-centred care, MDT collaboration, continuous professional development,
equality and inclusion, clinical governance, evidence-based practice.
"""

# ── Template 2: 12-point system prompt ───────────────────────────────────────
TEMPLATE_2_SYSTEM = f"""
You are writing a NHS job application supporting information statement for Dr. Nermeen Hassan.
Use ONLY the CV information provided. Write in first person. Be specific, confident, and direct.
Never say she is underqualified. Never suggest aiming lower. Frame every gap as manageable.
Always amplify her potential.

IMPORTANT: Read the job specification carefully and mirror its exact language and criteria
throughout the statement. If the person spec says "excellent communication skills", use
those exact words when describing her experience. Match every essential criterion explicitly.

Structure the response as exactly 12 numbered points covering:
1. Opening hook - why this trust and role specifically (use the trust name from the job)
2. NHS clinical experience - lead with Bedford attachments (STAR format)
3. Acute and specialty clinical skills matching the person spec
4. Specialty-specific relevance matched to this job
5. Clinical systems and NHS working knowledge (ICE, NerveCentre, TTOs)
6. MDT working and communication skills
7. Audit and clinical governance
8. Research and academic contributions
9. Teaching and leadership
10. Transfusion Medicine and additional specialty value
11. Personal values alignment with trust values
12. Closing - commitment, availability, enthusiasm

Write each point as 3-5 sentences of flowing prose. No bullet points inside the points.
Total length: 600-800 words.

CV DATA:
{CV_PROFILE}
"""

# ── Generate supporting information via Gemini ────────────────────────────────
def generate_supporting_info(job_title: str, trust_name: str, job_spec_text: str) -> str:
    prompt = (
        f"{TEMPLATE_2_SYSTEM}\n\n"
        f"Job Title: {job_title}\n"
        f"Trust: {trust_name}\n"
        f"Job Specification (use this to mirror language and match criteria):\n"
        f"{job_spec_text[:4000]}\n\n"
        f"Write the 12-point supporting information statement for this specific job."
    )
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text

# ── Send Telegram message ─────────────────────────────────────────────────────
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })
    print(f"Telegram response: {response.status_code} - {response.text}")

# ── Scrape job details ────────────────────────────────────────────────────────
async def scrape_job_details(page, job_url: str) -> dict:
    await page.goto(job_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    job_title = await page.title()
    job_title = job_title.replace("Job vacancy:", "").replace("| trac.jobs", "").strip()

    try:
        trust_name = await page.locator(".nhsuk-card__heading, h1, .job-title").first.inner_text()
    except:
        trust_name = "NHS Trust"

    try:
        spec_text = await page.locator("main").first.inner_text()
    except:
        spec_text = ""

    return {
        "title": job_title,
        "trust": trust_name.strip(),
        "spec": spec_text
    }

# ── Log into Trac ─────────────────────────────────────────────────────────────
async def login_trac(page):
    await page.goto("https://www.jobs.nhs.uk/candidate/login", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    await page.fill('input[name="username"], input[type="email"], #username', TRAC_EMAIL)
    await page.fill('input[name="password"], input[type="password"], #password', TRAC_PASSWORD)
    await page.click('button[type="submit"], input[type="submit"]')
    await page.wait_for_timeout(3000)

    if "login" in page.url.lower():
        raise Exception("Trac login failed - check TRAC_EMAIL and TRAC_PASSWORD secrets")

    print("Logged into Trac successfully")

# ── Click Apply button ────────────────────────────────────────────────────────
async def click_apply(page, job_url: str):
    await page.goto(job_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    for selector in [
        'a:has-text("Apply")',
        'button:has-text("Apply")',
        'a:has-text("Apply for this job")',
        'a:has-text("Apply online")',
        '.apply-button',
        '#apply-button'
    ]:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(3000)
                print("Clicked apply button")
                return
        except:
            continue

    raise Exception("Could not find Apply button")

# ── Fill supporting information ───────────────────────────────────────────────
async def fill_application(page, supporting_info: str):
    await page.wait_for_timeout(2000)

    for selector in [
        'textarea[name*="supporting"]',
        'textarea[name*="personal"]',
        'textarea[name*="statement"]',
        'textarea[id*="supporting"]',
        'textarea[id*="personal"]',
        'textarea[id*="statement"]',
        '#supportingInformation',
        '.supporting-information textarea',
        'textarea'
    ]:
        try:
            field = page.locator(selector).first
            if await field.is_visible():
                await field.click()
                await field.fill(supporting_info)
                print("Filled supporting information")
                break
        except:
            continue

    for selector in [
        'button:has-text("Save and continue")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'input[value="Save and continue"]',
        'input[value="Next"]'
    ]:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(2000)
                print("Clicked continue")
                break
        except:
            continue

# ── Submit application ────────────────────────────────────────────────────────
async def submit_application(page):
    for selector in [
        'button:has-text("Submit application")',
        'button:has-text("Submit")',
        'input[value="Submit application"]',
        'input[value="Submit"]',
        '.submit-btn'
    ]:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(4000)
                print("Application submitted")
                return
        except:
            continue

    raise Exception("Could not find Submit button")

# ── Main orchestrator ─────────────────────────────────────────────────────────
async def apply_to_job(job_url: str):
    print(f"\nStarting application for: {job_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("Scraping job details...")
            job = await scrape_job_details(page, job_url)
            print(f"Title: {job['title']}")
            print(f"Trust: {job['trust']}")

            # Check if job should be skipped
            if is_excluded_job(job["title"]):
                msg = (
                    f"⏭ *Job Skipped*\n\n"
                    f"*Job:* {job['title']}\n"
                    f"*Reason:* Title matches exclusion list\n"
                    f"*URL:* {job_url}"
                )
                send_telegram(msg)
                print(f"Skipped: {job['title']} (excluded title)")
                return

            print("Generating supporting information via Gemini...")
            supporting_info = generate_supporting_info(
                job["title"], job["trust"], job["spec"]
            )
            print(f"Generated {len(supporting_info)} characters")

            print("Logging into Trac...")
            await login_trac(page)

            print("Clicking apply...")
            await click_apply(page, job_url)

            print("Filling application form...")
            await fill_application(page, supporting_info)

            print("Submitting...")
            await submit_application(page)

            send_telegram(
                f"✅ *Application Submitted*\n\n"
                f"*Job:* {job['title']}\n"
                f"*Trust:* {job['trust']}\n"
                f"*URL:* {job_url}\n\n"
                f"_Preview:_\n{supporting_info[:400]}..."
            )
            print("Telegram confirmation sent")

        except Exception as e:
            send_telegram(
                f"❌ *Application Failed*\n\n"
                f"*URL:* {job_url}\n"
                f"*Error:* {str(e)}"
            )
            print(f"ERROR: {e}")
            raise

        finally:
            await browser.close()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python trac_apply.py <job_url>")
        sys.exit(1)

    asyncio.run(apply_to_job(sys.argv[1]))
