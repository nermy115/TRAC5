import os
import re
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

BASE_URL = "https://www.healthjobsuk.com/job_list/s2"

# Senior grades — still listed in notifications but flagged so you can skip them
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

# ── Telegram (best-effort, never raises) ──────────────────────────────────────
def telegram_send(message: str):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
        if response.status_code != 200:
            print(f"⚠️ Telegram non-200: {response.status_code} {response.text[:200]}")
    except Exception as e:
        print(f"⚠️ Telegram send failed: {e}")

def notify_new_jobs(new_jobs):
    """Send new job listings via Telegram, chunked to stay under the 4096 char limit."""
    chunk_size = 8
    total = len(new_jobs)

    for i in range(0, total, chunk_size):
        chunk = new_jobs[i:i + chunk_size]
        header = f"🏥 New NHS Jobs ({i+1}–{min(i+chunk_size, total)} of {total})\n\n"
        body_lines = []
        for job in chunk:
            label = " [Senior — skip]" if is_excluded(job['Title']) else ""
            body_lines.append(f"• {job['Title']}{label}\n  {job['Link']}")
        telegram_send(header + "\n\n".join(body_lines))
        time.sleep(1)  # avoid Telegram rate limit between chunks

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

# ── Scrape all pages via Playwright ───────────────────────────────────────────
def scrape_all_pages():
    """Returns (jobs, ok). ok=False means fetch failed — caller must NOT
    overwrite jobs.txt in that case."""
    jobs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
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
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page_obj = context.new_page()

        try:
            page_obj.goto(
                "https://www.healthjobsuk.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            time.sleep(1.5)
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

# ── Main ──────────────────────────────────────────────────────────────────────
def monitor():
    previous_ids = load_previous_job_ids()
    print(f"📋 Loaded {len(previous_ids)} previously seen job IDs")

    current_jobs, ok = scrape_all_pages()

    if not ok:
        msg = (
            "⚠️ NHS scraper blocked (likely 403 from healthjobsuk.com). "
            "No jobs fetched; tracked state preserved. Check workflow logs."
        )
        print(msg)
        telegram_send(msg)
        return

    current_ids = {job["ID"] for job in current_jobs}
    print(f"📋 Total jobs currently listed: {len(current_ids)}")

    new_jobs = [job for job in current_jobs if job["ID"] not in previous_ids]

    if new_jobs:
        print(f"🆕 {len(new_jobs)} new job(s)!")
        notify_new_jobs(new_jobs)
    else:
        print("✅ No new jobs found")

    save_current_job_ids(current_ids)

if __name__ == "__main__":
    monitor()
    print("🏁 Done")
