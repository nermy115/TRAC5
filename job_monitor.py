import os
import re
import time
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

EMAIL        = os.environ["EMAIL"]
APP_PASSWORD = os.environ["APP_PASSWORD"]
GITHUB_TOKEN = os.environ["GH_TOKEN"]

# Optional — used to send a failure alert if scraping breaks
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

BASE_URL = "https://www.healthjobsuk.com/job_list/s2"

# Realistic browser headers — bare User-Agent strings are getting 403'd now.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.healthjobsuk.com/",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

# ── Consultant/senior grade blocklist ─────────────────────────────────────────
EXCLUDE_TITLES = [
    "consultant",
    "associate specialist",
    "gp principal",
    "gp partner",
    "clinical director",
    "medical director",
]

def is_excluded(title: str) -> bool:
    title_lower = title.lower()
    return any(word in title_lower for word in EXCLUDE_TITLES)

# ── Telegram failure alert (best-effort, never raises) ────────────────────────
def telegram_alert(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ℹ️  Telegram not configured, skipping alert")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
    except Exception as e:
        print(f"⚠️  Could not send Telegram alert: {e}")

# ── Trigger auto-apply in TRAC5 ───────────────────────────────────────────────
def trigger_auto_apply(job):
    url = "https://api.github.com/repos/nermy115/TRAC5/dispatches"
    response = requests.post(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        },
        json={
            "event_type": "new_job_found",
            "client_payload": {"job_url": job["Link"]}
        }
    )
    if response.status_code == 204:
        print(f"🚀 Triggered auto-apply for: {job['Title']}")
    else:
        print(f"⚠️ Failed to trigger auto-apply for {job['Title']}: {response.status_code}")

# ── Load/save seen job IDs ────────────────────────────────────────────────────
def load_previous_job_ids():
    try:
        with open("jobs.txt", "r") as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_current_job_ids(job_ids):
    with open("jobs.txt", "w") as f:
        f.write("\n".join(sorted(job_ids)))

# ── Scrape all pages ──────────────────────────────────────────────────────────
# Returns (jobs, ok). `ok=False` means the fetch failed and the caller must NOT
# treat the empty list as authoritative (i.e. do not overwrite jobs.txt).
def scrape_all_pages():
    """Use a real Chromium browser via Playwright. TRAC's WAF blocks plain
    HTTP scrapers even with TLS impersonation, so we render the listing in
    an actual browser. Returns (jobs, ok)."""
    jobs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                # Hides one of the most obvious Playwright/Selenium fingerprints
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
            timezone_id="Europe/London",
        )
        # Real Chrome does NOT have navigator.webdriver === true. Strip the
        # automation flag before any page script runs.
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page_obj = context.new_page()

        # Warm up by visiting the homepage first.
        try:
            page_obj.goto(
                "https://www.healthjobsuk.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            time.sleep(1.5)  # let any anti-bot JS settle
        except Exception as e:
            print(f"⚠️  Homepage warm-up failed (continuing anyway): {e}")

        page_num = 1
        while True:
            url = f"{BASE_URL}?_ts=1" if page_num == 1 else f"{BASE_URL}?_ts=1&_pg={page_num}"
            try:
                response = page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
                status = response.status if response else 0
                if status >= 400:
                    print(f"🚨 Failed to fetch page {page_num}: HTTP {status}")
                    browser.close()
                    return [], False
                html = page_obj.content()
            except Exception as e:
                print(f"🚨 Failed to fetch page {page_num}: {e}")
                browser.close()
                return [], False

            soup = BeautifulSoup(html, 'html.parser')
            job_links = soup.find_all('a', href=re.compile(r'^/job/'))
            print(f"🔍 Found {len(job_links)} jobs on page {page_num}")

            if not job_links:
                break

            for link in job_links:
                href = link.get('href', '').split('?')[0]
                match = re.search(r'-(v\d+)$', href)
                if not match:
                    continue
                job_id = match.group(1)
                title = link.get('title') or link.text.strip().split('\n')[0]
                jobs.append({
                    "ID": job_id,
                    "Title": title,
                    "Link": f"https://www.healthjobsuk.com{href}"
                })

            if not soup.find('a', title="Next page"):
                break
            page_num += 1
            time.sleep(1.0)

        browser.close()
    return jobs, True

# ── Send email ────────────────────────────────────────────────────────────────
def send_email(new_jobs):
    msg = MIMEMultipart()
    msg['Subject'] = f"🏥 New NHS Jobs: {len(new_jobs)} new posting(s)!"
    msg['From'] = EMAIL
    msg['To'] = "nermeen1899@hotmail.com"

    body = "New Medical/Dental jobs found:\n\n"
    for job in new_jobs:
        skipped = " [SKIPPED - senior grade]" if is_excluded(job['Title']) else " [AUTO-APPLYING]"
        body += f"• {job['Title']}{skipped}\n  {job['Link']}\n\n"

    msg.attach(MIMEText(body, 'plain'))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✉️ Sent email with {len(new_jobs)} new job(s)")
    except Exception as e:
        print(f"🚨 Email failed: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
def monitor():
    previous_ids = load_previous_job_ids()
    print(f"📋 Loaded {len(previous_ids)} previously seen job IDs")

    current_jobs, ok = scrape_all_pages()

    if not ok:
        # CRITICAL: do NOT save an empty jobs.txt — that wipes our tracked
        # state and causes every job to look "new" once scraping recovers.
        msg = (
            "⚠️ NHS scraper blocked (likely 403 from healthjobsuk.com). "
            "No jobs fetched; tracked state preserved. Check workflow logs."
        )
        print(msg)
        telegram_alert(msg)
        return

    current_ids = {job["ID"] for job in current_jobs}
    print(f"📋 Total jobs currently listed: {len(current_ids)}")

    new_jobs = [job for job in current_jobs if job["ID"] not in previous_ids]

    if new_jobs:
        print(f"🆕 {len(new_jobs)} new job(s)!")
        send_email(new_jobs)

        for job in new_jobs:
            if is_excluded(job["Title"]):
                print(f"⏭ Skipping (senior grade): {job['Title']}")
            else:
                trigger_auto_apply(job)
                time.sleep(2)
    else:
        print("✅ No new jobs found")

    save_current_job_ids(current_ids)

if __name__ == "__main__":
    monitor()
    print("🏁 Done")
