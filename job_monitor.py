import os
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# --- Configuration ---
EMAIL = os.environ["EMAIL"]
APP_PASSWORD = os.environ["APP_PASSWORD"]
BASE_URL = "https://www.healthjobsuk.com/job_search/s2/Medical_Dental"

# --- Core Functions ---
def load_previous_job_ids():
    try:
        with open("jobs.txt", "r") as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_current_job_ids(job_ids):
    with open("jobs.txt", "w") as f:
        f.write("\n".join(job_ids))

def scrape_all_pages():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    })
    
    jobs = []
    page = 1
    
    while True:
        # Submit form with search parameters
        form_data = {
            "JobSearch_Submit": "Search",
            "_pg": str(page),
            "_sort": "newest",
            "JobSearch.re": "MedicalAndDental"  # Verify this in page HTML
        }
        
        print(f"\n🔍 Pressing Search (Page {page})...")
        response = session.post(BASE_URL, data=form_data)
        response.raise_for_status()
        
        # Save debug HTML for manual inspection
        with open(f"debug_page_{page}.html", "w") as f:
            f.write(response.text)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        job_listings = soup.select('li.hj-job-result')  # Update this selector
        
        print(f"📄 Found {len(job_listings)} jobs on page {page}")
        
        if not job_listings:
            break

        # Process each job listing
        for job in job_listings:
            link_tag = job.find('a', class_='hj-job-link')
            if not link_tag:
                continue
            
            href = link_tag['href']
            job_id = href.split('/')[-1]
            title = job.find('div', class_='hj-jobtitle').text.strip()
            
            jobs.append({
                "ID": job_id,
                "Title": title,
                "Link": f"https://www.healthjobsuk.com{href}"
            })

        page += 1  # Next page
    
    return jobs

def send_email(new_jobs):
    if not new_jobs:
        return

    msg = MIMEMultipart()
    msg['Subject'] = f"New NHS Jobs: {len(new_jobs)} Found!"
    msg['From'] = EMAIL
    msg['To'] = EMAIL
    
    body = "🚨 New Medical/Dental Jobs:\n\n"
    for job in new_jobs:
        body += f"- {job['Title']}\n   {job['Link']}\n\n"
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✉️ Sent email with {len(new_jobs)} jobs")
    except Exception as e:
        print(f"🚨 Email failed: {str(e)}")

def monitor():
    previous_ids = load_previous_job_ids()
    current_jobs = scrape_all_pages()
    current_ids = {job["ID"] for job in current_jobs}
    
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_ids]
    
    if new_jobs:
        send_email(new_jobs)
    else:
        print("✅ No new jobs found")
    
    save_current_job_ids(current_ids)

# --- Main ---
if __name__ == "__main__":
    monitor()
    print("🏁 Script completed")
