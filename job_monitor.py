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
    """Send a Telegram message. Respects 429 retry_after once, then gives up."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 429:
            try:
                retry_after = response.json().get("parameters", {}).get("retry_after", 30)
            except Exception:
                retry_after = 30
            # Cap our wait at 90s — beyond that, we just give up on this message
            # rather than blocking the whole workflow for minutes.
            if retry_after <= 90:
                print(f"⏸  Telegram rate limited; sleeping {retry_after}s then retrying once")
                time.sleep(retry_after + 1)
                response = requests.post(url, json=payload, timeout=10)
            else:
                print(f"⏸  Telegram rate limit too long ({retry_after}s) — skipping this message")
                return
        if response.status_code != 200:
            print(f"⚠️ Telegram non-200: {response.status_code} {response.text[:200]}")
    except Exception as e:
        print(f"⚠️ Telegram send failed: {e}")

def notify_new_jobs(new_jobs):
    """Send ALL new job listings via Telegram, chunked under the 4096 char limit.
    Sleep is only inserted BETWEEN messages — single-message runs have zero
    added delay. The 429 retry logic in telegram_send() handles any actual
    rate limits."""
    total = len(new_jobs)
    chunk_size = 8
    chunks = [new_jobs[i:i + chunk_size] for i in range(0, total, chunk_size)]

    for idx, chunk in enumerate(chunks):
        i = idx * chunk_size
        header = f"🏥 New NHS Jobs ({i+1}–{min(i+chunk_size, total)} of {total})\n\n"
        body_lines = [f"• {job['Title']}\n  {job['Link']}" for job in chunk]
        telegram_send(header + "\n\n".join(body_lines))
        # Only sleep if there's another message coming
        if idx < len(chunks) - 1:
            time.sleep(3)

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

# Sort by start date, descending — newest job on page 1.
# (TRAC's UI uses _sd=a for ascending; _sd=d should be descending. If a future
# run shows we're scraping in the wrong direction, flip this to 'a' and scrape
# backwards instead — but 'd' is the universal convention so we try that first.)
SORT_QUERY = "_ts=1&_srt=startdate&_sd=d"

# ── Scrape pages via Playwright ───────────────────────────────────────────────
def scrape_all_pages(stop_at_known_ids=None):
    """Walk pages newest-first. If `stop_at_known_ids` is provided, return as
    soon as we encounter a job ID in that set — everything past that point is
    older and we already know about it. Massive speedup vs. scraping all 24+
    pages every run.
    Returns (jobs, ok). ok=False means fetch failed — caller must NOT
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

        # Walk pages newest-first. Stop when either:
        #   (a) we hit a job we've already seen (everything beyond is older)
        #   (b) the page returns zero job links — past the last page
        #   (c) max_pages safety cap
        page_num = 1
        max_pages = 50
        seen_ids = set()
        hit_known = False
        while page_num <= max_pages:
            url = f"{BASE_URL}?{SORT_QUERY}" if page_num == 1 else f"{BASE_URL}?{SORT_QUERY}&_pg={page_num}"
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
                break  # past the last page

            new_this_page = 0
            for link in job_links:
                href = link.get('href', '').split('?')[0]
                match = re.search(r'-(v\d+)$', href)
                if not match:
                    continue
                job_id = match.group(1)

                # Newest-first sort means: the moment we see an ID we already
                # know about, everything past this point is older and already
                # tracked. Stop here.
                if stop_at_known_ids is not None and job_id in stop_at_known_ids:
                    print(f"  ✋ Reached previously-seen job on page {page_num} — stopping")
                    hit_known = True
                    break

                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                new_this_page += 1
                title = link.get('title') or link.text.strip().split('\n')[0]
                jobs.append({
                    "ID": job_id,
                    "Title": title,
                    "Link": f"https://www.healthjobsuk.com{href}"
                })

            if hit_known:
                break

            if new_this_page == 0:
                print(f"  (page {page_num} returned only duplicates — stopping)")
                break

            page_num += 1
            time.sleep(1.0)

        if page_num > max_pages:
            print(f"⚠️  Hit page safety cap ({max_pages}). May have missed jobs.")

        browser.close()
    return jobs, True

# ── Main ──────────────────────────────────────────────────────────────────────
def monitor():
    previous_ids = load_previous_job_ids()
    print(f"📋 Loaded {len(previous_ids)} previously seen job IDs")

    # Newest-first scrape that stops as soon as it hits a known job.
    # Returns ONLY the new jobs (not all 1188).
    new_jobs, ok = scrape_all_pages(stop_at_known_ids=previous_ids)

    if not ok:
        msg = (
            "⚠️ NHS scraper blocked (likely 403 from healthjobsuk.com). "
            "No jobs fetched; tracked state preserved. Check workflow logs."
        )
        print(msg)
        telegram_send(msg)
        return

    print(f"🆕 {len(new_jobs)} new job(s) found before hitting known territory")

    # Filter senior grades from notifications (still saved to jobs.txt so they
    # don't re-appear next run).
    notification_jobs = [job for job in new_jobs if not is_excluded(job["Title"])]
    senior_filtered = len(new_jobs) - len(notification_jobs)

    if notification_jobs:
        print(f"📨 Notifying about {len(notification_jobs)} non-senior job(s) "
              f"({senior_filtered} senior jobs filtered out)")
        notify_new_jobs(notification_jobs)
    elif new_jobs:
        print(f"✅ No new non-senior jobs ({senior_filtered} senior jobs filtered out)")
    else:
        print("✅ No new jobs found")

    # Append the new IDs to our tracked set (preserves all previously-seen IDs).
    if new_jobs:
        all_ids = previous_ids | {job["ID"] for job in new_jobs}
        save_current_job_ids(all_ids)

if __name__ == "__main__":
    monitor()
    print("🏁 Done")
