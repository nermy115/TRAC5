import os
import re
import time
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

EMAIL = os.environ["EMAIL"]
APP_PASSWORD = os.environ["APP_PASSWORD"]
BASE_URL = "https://www.healthjobsuk.com/job_list/s2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def load_previous_job_ids():
    try:
        with open("jobs.txt", "r") as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_current_job_ids(job_ids):
    with open("jobs.txt", "w") as f:
        f.write("\n".join(sorted(job_ids)))

def scrape_all_pages():
    jobs = []
    page = 1

    while True:
        url = f"{BASE_URL}?_ts=1" if page == 1 else f"{BASE_URL}?_ts=1&_pg={page}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
        except Exception as e:
            print(f"🚨 Failed to fetch page {page}: {e}")
            break

        soup = BeautifulSoup(response.text, 'html.parser')
        job_links = soup.find_all('a', href=re.compile(r'^/job/'))
        print(f"🔍 Found {len(job_links)} jobs on page {page}")

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
        page += 1
        time.sleep(0.5)  # polite crawling

    return jobs

def send_email(new_jobs):
    msg = MIMEMultipart()
    msg['Subject'] = f"🏥 New NHS Jobs: {len(new_jobs)} new posting(s)!"
    msg['From'] = EMAIL
    msg['To'] = "nermeen1899@hotmail.com"

    body = "New Medical/Dental jobs found:\n\n"
    for job in new_jobs:
        body += f"• {job['Title']}\n  {job['Link']}\n\n"
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✉️ Sent email with {len(new_jobs)} new job(s)")
    except Exception as e:
        print(f"🚨 Email failed: {e}")

def monitor():
    previous_ids = load_previous_job_ids()
    print(f"📋 Loaded {len(previous_ids)} previously seen job IDs")

    current_jobs = scrape_all_pages()
    current_ids = {job["ID"] for job in current_jobs}
    print(f"📋 Total jobs currently listed: {len(current_ids)}")

    new_jobs = [job for job in current_jobs if job["ID"] not in previous_ids]

    if new_jobs:
        print(f"🆕 {len(new_jobs)} new job(s)!")
        send_email(new_jobs)
    else:
        print("✅ No new jobs found")

    save_current_job_ids(current_ids)

if __name__ == "__main__":
    monitor()
    print("🏁 Done")
