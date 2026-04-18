"""
NHS Trac Auto-Application Script
Dr. Nermeen Hassan - GMC 7771612
Uses Playwright to fill and submit Trac applications automatically.
Triggered by job URL, generates Template 2 supporting info via Claude API,
submits application, and sends Telegram confirmation.
"""

import os
import sys
import asyncio
import requests
import anthropic
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ── Secrets (set these in GitHub Actions or .env) ────────────────────────────
TRAC_EMAIL    = os.environ["TRAC_EMAIL"]       # your Trac login email
TRAC_PASSWORD = os.environ["TRAC_PASSWORD"]    # your Trac password
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]  # 8673926039:AAHEol1MyfmNjWWF9Cj1_3VOxOSSdKkq3FQ
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]  # 6068450979

# ── CV & Profile ─────────────────────────────────────────────────────────────
CV_PROFILE = """
Name: Dr. Nermeen Hassan
GMC Number: 7771612
Email: (your email)
Qualifications: MBChB Mansoura University 2019, PLAB1, PLAB2, GMC registered January 2024
ALS certified. Train the Healthcare Trainer (NHSE 2025). GCP (NIHR, enrolled).
Critical Appraisal course (NHS England). Co-author Cureus peer-reviewed publication
(PMID: 41064803) on spirometry in asthmatic patients.

CLINICAL EXPERIENCE:
1. Clinical Attachment – Diabetes & Endocrinology / Stroke / AAU, Bedford Hospital
   September – November 2024
   - Clerked and presented patients on ward rounds in Diabetes & Endocrinology and Stroke units
   - Participated in AAU acute assessments, TTOs, discharge summaries
   - Used ICE and NerveCentre systems
   - Attended MDT meetings and contributed to patient management discussions

2. Clinical Attachment – Acute Medicine, Bedford Hospital
   February 2025
   - Acute medical take, clerking undifferentiated presentations
   - Worked alongside registrars and consultants in a busy AMU setting
   - Further consolidation of ICE/NerveCentre and NHS documentation standards

3. Transfusion Medicine Specialty Training – Egyptian Fellowship
   National Blood Bank, Egypt, 2020–2021
   - Specialist training in blood transfusion, haemovigilance, and blood product management
   - Completed Egyptian Fellowship in Transfusion Medicine

4. GP and Unit Management, Egypt (2019–2022)
   - GP-level consultations across a broad range of presentations
   - Managed a clinical unit overseeing a team of 22+ staff
   - Experience in patient triage, chronic disease management, referrals

SPECIALTY BRIDGES (use whichever matches the job):
- Acute Medicine / AAU: Bedford AMU attachment, acute clerking, undifferentiated presentations
- Diabetes & Endocrinology: Bedford D&E attachment, chronic disease management
- Stroke: Bedford Stroke unit, MDT, rehabilitation pathway
- Haematology: Transfusion Medicine fellowship, blood product expertise
- Infectious Diseases: Broad acute medicine base, public health awareness
- Respiratory: Spirometry research (Cureus publication), AAU respiratory presentations
- Care of the Elderly: Stroke and AAU exposure, MDT working
- GP: Egyptian GP experience, broad primary care base

RESEARCH & AUDIT:
- Co-author: "Spirometry parameters in asthmatic patients" Cureus journal (PMID: 41064803)
- GCP training (NIHR) — ongoing
- Critical Appraisal course (NHS England) completed

TEACHING & LEADERSHIP:
- Train the Healthcare Trainer certificate (NHSE 2025)
- Unit management: led team of 22+ staff in Egypt
- Committed to undergraduate and postgraduate teaching within NHS MDT

VALUES: Patient-centred care, MDT collaboration, continuous professional development,
equality and inclusion, clinical governance, evidence-based practice.
"""

# ── Template 2: 12-point detailed system prompt ───────────────────────────────
TEMPLATE_2_SYSTEM = f"""
You are writing a NHS job application supporting information statement for Dr. Nermeen Hassan.
Use ONLY the CV information provided. Write in first person. Be specific, confident, and direct.
Never say she is underqualified. Never suggest aiming lower. Frame every gap as manageable.
Always amplify her potential.

Structure the response as exactly 12 numbered points covering:
1. Opening hook — why this trust/role specifically (use trust name from job spec)
2. NHS clinical experience — lead with Bedford attachments (STAR format)
3. Acute/specialty clinical skills matching the person spec
4. Specialty-specific relevance (match to the job specialty)
5. Clinical systems and NHS working knowledge (ICE, NerveCentre, TTOs)
6. MDT working and communication
7. Audit and clinical governance
8. Research and academic contributions
9. Teaching and leadership
10. Transfusion Medicine / additional specialty value
11. Personal values alignment with trust values
12. Closing — commitment, availability, enthusiasm

Write each point as 3-5 sentences. Total length: 600-800 words.
Do not use bullet points inside the points. Flowing prose only.

CV DATA:
{CV_PROFILE}
"""

# ── Generate supporting information ──────────────────────────────────────────
def generate_supporting_info(job_title: str, trust_name: str, job_spec_text: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = f"""
Job Title: {job_title}
Trust: {trust_name}
Job Specification Extract:
{job_spec_text[:3000]}

Write the 12-point supporting information statement for this specific job.
"""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=TEMPLATE_2_SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── Send Telegram message ─────────────────────────────────────────────────────
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })

# ── Scrape job details from Trac ─────────────────────────────────────────────
async def scrape_job_details(page, job_url: str) -> dict:
    await page.goto(job_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    job_title = await page.title()

    # Try to extract trust name and spec text
    try:
        trust_name = await page.locator("text=/NHS|Trust|Hospital/i").first.inner_text()
    except:
        trust_name = "NHS Trust"

    try:
        spec_text = await page.locator(".job-description, .jobDescription, #jobDescription, main").first.inner_text()
    except:
        spec_text = ""

    return {
        "title": job_title.replace(" | NHS Jobs", "").strip(),
        "trust": trust_name.strip(),
        "spec": spec_text[:3000]
    }

# ── Log into Trac ─────────────────────────────────────────────────────────────
async def login_trac(page):
    await page.goto("https://www.jobs.nhs.uk/candidate/login", wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)

    # Fill login form
    await page.fill('input[name="username"], input[type="email"], #username', TRAC_EMAIL)
    await page.fill('input[name="password"], input[type="password"], #password', TRAC_PASSWORD)
    await page.click('button[type="submit"], input[type="submit"], .login-btn')
    await page.wait_for_timeout(3000)

    if "login" in page.url.lower():
        raise Exception("Trac login failed — check TRAC_EMAIL and TRAC_PASSWORD secrets")

    print("✓ Logged into Trac")

# ── Find and click Apply button ───────────────────────────────────────────────
async def click_apply(page, job_url: str):
    await page.goto(job_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Try various apply button selectors
    apply_selectors = [
        'a:has-text("Apply")',
        'button:has-text("Apply")',
        'a:has-text("Apply for this job")',
        'a:has-text("Apply online")',
        '.apply-button',
        '#apply-button'
    ]

    for selector in apply_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(3000)
                print(f"✓ Clicked apply button")
                return
        except:
            continue

    raise Exception("Could not find Apply button on job page")

# ── Fill application form ─────────────────────────────────────────────────────
async def fill_application(page, supporting_info: str):
    await page.wait_for_timeout(2000)

    # Supporting information text area — Trac uses various field names
    si_selectors = [
        'textarea[name*="supporting"], textarea[name*="personal"], textarea[name*="statement"]',
        'textarea[id*="supporting"], textarea[id*="personal"], textarea[id*="statement"]',
        'textarea[placeholder*="supporting"], textarea[placeholder*="personal"]',
        '.supporting-information textarea',
        '#supportingInformation',
        'textarea'
    ]

    filled = False
    for selector in si_selectors:
        try:
            field = page.locator(selector).first
            if await field.is_visible():
                await field.click()
                await field.fill(supporting_info)
                print(f"✓ Filled supporting information field")
                filled = True
                break
        except:
            continue

    if not filled:
        raise Exception("Could not find supporting information text field")

    await page.wait_for_timeout(1000)

    # Handle any "Save and continue" steps
    continue_selectors = [
        'button:has-text("Save and continue")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'input[value="Save and continue"]',
        'input[value="Next"]'
    ]

    for selector in continue_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(2000)
                print(f"✓ Clicked continue")
                break
        except:
            continue

# ── Final submit ──────────────────────────────────────────────────────────────
async def submit_application(page):
    submit_selectors = [
        'button:has-text("Submit application")',
        'button:has-text("Submit")',
        'input[value="Submit application"]',
        'input[value="Submit"]',
        '.submit-btn'
    ]

    for selector in submit_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(4000)
                print("✓ Application submitted")
                return
        except:
            continue

    raise Exception("Could not find Submit button")

# ── Main orchestrator ─────────────────────────────────────────────────────────
async def apply_to_job(job_url: str):
    print(f"\n🚀 Starting application for: {job_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Step 1: Scrape job details (before login, page is public)
            print("📄 Scraping job details...")
            job = await scrape_job_details(page, job_url)
            print(f"   Title: {job['title']}")
            print(f"   Trust: {job['trust']}")

            # Step 2: Generate supporting information
            print("✍️  Generating supporting information...")
            supporting_info = generate_supporting_info(
                job["title"], job["trust"], job["spec"]
            )
            print(f"   Generated {len(supporting_info)} characters")

            # Step 3: Log in
            print("🔐 Logging into Trac...")
            await login_trac(page)

            # Step 4: Navigate back to job and click Apply
            print("📝 Clicking apply...")
            await click_apply(page, job_url)

            # Step 5: Fill the form
            print("📋 Filling application form...")
            await fill_application(page, supporting_info)

            # Step 6: Submit
            print("🚀 Submitting...")
            await submit_application(page)

            # Step 7: Telegram confirmation
            msg = (
                f"✅ *Application Submitted*\n\n"
                f"*Job:* {job['title']}\n"
                f"*Trust:* {job['trust']}\n"
                f"*URL:* {job_url}\n\n"
                f"Supporting info preview:\n_{supporting_info[:300]}..._"
            )
            send_telegram(msg)
            print("📱 Telegram confirmation sent")

        except Exception as e:
            error_msg = (
                f"❌ *Application Failed*\n\n"
                f"*URL:* {job_url}\n"
                f"*Error:* {str(e)}"
            )
            send_telegram(error_msg)
            print(f"ERROR: {e}")
            raise

        finally:
            await browser.close()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python trac_apply.py <job_url>")
        sys.exit(1)

    job_url = sys.argv[1]
    asyncio.run(apply_to_job(job_url))
