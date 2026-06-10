import os
import re
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Cloudflare Worker relay. healthjobsuk.com's WAF blocks GitHub Actions'
# Azure IP ranges, so we fetch through a Worker running on Cloudflare IPs.
# If these env vars are missing, we fall back to direct fetching (works
# locally; usually 403s from GitHub Actions).
PROXY_URL   = os.environ.get("PROXY_URL", "").rstrip("/")
PROXY_TOKEN = os.environ.get("PROXY_TOKEN", "")

BASE_URL = "https://www.healthjobsuk.com/job_list/s2"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Senior grades — filtered out of notifications (but still tracked)
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

# ── Page fetching ─────────────────────────────────────────────────────────────
def fetch_html(url: str):
    """Fetch a page, preferring the Worker relay. Returns (html, status)."""
    try:
        if PROXY_URL:
            r = requests.get(
                PROXY_URL,
                params={"token": PROXY_TOKEN, "url": url},
                timeout=30,
            )
        else:
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
        return r.text, r.status_code
    except Exception as e:
        print(f"Fetch error for {url}: {e}")
        return "", 0

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
            if retry_after <= 90:
                print(f"Telegram rate limited; sleeping {retry_after}s then retrying once")
                time.sleep(retry_after + 1)
                response = requests.post(url, json=payload, timeout=10)
            else:
                print(f"Telegram rate limit too long ({retry_after}s) — skipping this message")
                return
        if response.status_code != 200:
            print(f"Telegram non-200: {response.status_code} {response.text[:200]}")
    except Exception as e:
        print(f"Telegram send failed: {e}")

def notify_new_jobs(new_jobs):
    """Send ALL new job listings via Telegram, chunked under the 4096 char limit."""
    total = len(new_jobs)
    chunk_size = 8
    chunks = [new_jobs[i:i + chunk_size] for i in range(0, total, chunk_size)]

    for idx, chunk in enumerate(chunks):
        i = idx * chunk_size
        header = f"\U0001F3E5 New NHS Jobs ({i+1}-{min(i+chunk_size, total)} of {total})\n\n"
        body_lines = [f"• {job['Title']}\n  {job['Link']}" for job in chunk]
        telegram_send(header + "\n\n".join(body_lines))
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

# ── Failure-state flag (alert cooldown) ───────────────────────────────────────
# Committed to the repo so state persists between runs:
# - scraping starts failing -> ONE Telegram alert, flag created
# - flag exists -> stay silent on further failures
# - scraping recovers -> "recovered" alert, flag deleted
FAILURE_FLAG = ".scraper_failing"

def is_in_failure_state():
    return os.path.exists(FAILURE_FLAG)

def mark_failure_state():
    with open(FAILURE_FLAG, "w") as f:
        f.write(datetime.utcnow().isoformat() + "Z\n")

def clear_failure_state():
    if os.path.exists(FAILURE_FLAG):
        os.remove(FAILURE_FLAG)

# NOTE on ordering: the server REDIRECTS sorted URLs (?_srt=...) back to plain
# /job_list/s2 and drops the params, so we make no ordering assumptions and do
# a full sweep of all pages (~23) every run. The site is server-rendered, so
# plain HTTP GETs are enough — no Playwright/browser needed.

# ── Scrape all pages ──────────────────────────────────────────────────────────
def scrape_all_pages():
    """Scrape EVERY page of the job list.
    Returns (jobs, ok). ok=False means a fetch failed — caller must NOT
    overwrite jobs.txt in that case."""
    jobs = []
    page_num = 1
    max_pages = 50
    seen_ids = set()

    while page_num <= max_pages:
        url = BASE_URL if page_num == 1 else f"{BASE_URL}?_pg={page_num}"
        html, status = fetch_html(url)
        if status != 200 or not html:
            print(f"Failed to fetch page {page_num}: HTTP {status}")
            return [], False

        soup = BeautifulSoup(html, "html.parser")
        job_links = soup.find_all("a", href=re.compile(r"^/job/"))
        print(f"Found {len(job_links)} jobs on page {page_num}")

        if not job_links:
            break  # past the last page

        new_this_page = 0
        for link in job_links:
            href = link.get("href", "").split("?")[0]
            match = re.search(r"-(v\d+)$", href)
            if not match:
                continue
            job_id = match.group(1)

            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            new_this_page += 1
            title = link.get("title") or link.text.strip().split("\n")[0]
            jobs.append({
                "ID": job_id,
                "Title": title,
                "Link": f"https://www.healthjobsuk.com{href}",
            })

        if new_this_page == 0:
            # Site repeats the last page for out-of-range page numbers
            print(f"  (page {page_num} returned only duplicates — stopping)")
            break

        page_num += 1
        time.sleep(0.5)

    if page_num > max_pages:
        print(f"Hit page safety cap ({max_pages}). May have missed jobs.")

    return jobs, True

# ── Retry wrapper ─────────────────────────────────────────────────────────────
def scrape_with_retries(max_attempts=3):
    for attempt in range(1, max_attempts + 1):
        jobs, ok = scrape_all_pages()
        if ok:
            if attempt > 1:
                print(f"Succeeded on attempt {attempt}/{max_attempts}")
            return jobs, True
        if attempt < max_attempts:
            wait = 20 * attempt
            print(f"Attempt {attempt}/{max_attempts} failed. Waiting {wait}s before retry...")
            time.sleep(wait)
    return [], False

# ── Main ──────────────────────────────────────────────────────────────────────
def monitor():
    if PROXY_URL:
        print("Fetching via Cloudflare Worker relay")
    else:
        print("PROXY_URL not set — fetching directly (may 403 on GitHub Actions)")

    previous_ids = load_previous_job_ids()
    print(f"Loaded {len(previous_ids)} previously seen job IDs")

    all_jobs, ok = scrape_with_retries()

    if not ok:
        if is_in_failure_state():
            print("Scraper still failing. Alert already sent — staying silent.")
        else:
            msg = (
                "⚠️ NHS scraper failing (fetch errors from healthjobsuk.com) — all "
                "retries failed. Tracked state preserved. You'll get one "
                "'recovered' message when it's working again."
            )
            print(msg)
            telegram_send(msg)
            mark_failure_state()
        return

    if is_in_failure_state():
        telegram_send("✅ NHS scraper recovered and is working again.")
        clear_failure_state()

    new_jobs = [job for job in all_jobs if job["ID"] not in previous_ids]
    print(f"{len(new_jobs)} new job(s) out of {len(all_jobs)} scraped")

    # First-ever run (empty jobs.txt): seed silently, don't spam ~1,100 jobs.
    if not previous_ids:
        print("First run — seeding jobs.txt without notifications")
        save_current_job_ids({job["ID"] for job in all_jobs})
        return

    notification_jobs = [job for job in new_jobs if not is_excluded(job["Title"])]
    senior_filtered = len(new_jobs) - len(notification_jobs)

    if notification_jobs:
        print(f"Notifying about {len(notification_jobs)} non-senior job(s) "
              f"({senior_filtered} senior jobs filtered out)")
        notify_new_jobs(notification_jobs)
    elif new_jobs:
        print(f"No new non-senior jobs ({senior_filtered} senior jobs filtered out)")
    else:
        print("No new jobs found")

    if new_jobs:
        all_ids = previous_ids | {job["ID"] for job in new_jobs}
        save_current_job_ids(all_ids)

if __name__ == "__main__":
    monitor()
    print("Done")
