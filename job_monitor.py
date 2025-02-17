import os
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Configuration
EMAIL = os.environ["EMAIL"]
APP_PASSWORD = os.environ["APP_PASSWORD"]
BASE_URL = "https://www.healthjobsuk.com/job_search/s2/Medical_Dental"

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
    """Scrape jobs with debug logging and HTML validation"""
    session = requests.Session()
    
    # NEW: Enhanced headers to mimic browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": BASE_URL,
        "Accept-Language": "en-US,en;q=0.9"
    }
    session.headers.update(headers)
    
    # NEW: Initial request to set cookies
    session.get(BASE_URL)
    
    jobs = []
    page = 1
    
    while True:
        url = f"{BASE_URL}?_pg={page}&_sort=newest"
        print(f"\n🕵️‍♂️ DEBUG: Attempting to scrape {url}")  # NEW
        
        try:
            response = session.get(url)
            response.raise_for_status()
            
            # NEW: Save HTML for manual inspection 
            with open(f"debug_page_{page}.html", "w") as f:
                f.write(response.text)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_listings = soup.find_all('li', class_=lambda x: x and x.startswith('hj-job'))
            
            print(f"🔍 DEBUG: Found {len(job_listings)} jobs on page {page}")  # NEW
            
            if not job_listings:
                print("⏹️ DEBUG: Stopping pagination (no jobs found)")
                break

            # Process jobs with ID validation
            for job_li in job_listings:
                link_tag = job_li.find('a')
                if not link_tag:
                    continue
                
                href = link_tag.get('href', '')
                job_id = href.split('/')[-1].split('?')[0].strip()
                title = link_tag.find('div', class_='hj-jobtitle').text.strip() if link_tag.find('div', class_='hj-jobtitle') else "No Title"
                
                # NEW: Debug job parsing
                print(f"  🔗 Parsed: ID={job_id} | Title='{title[:30]}...'")
                
                jobs.append({
                    "ID": job_id,
                    "Title": title,
                    "Link": f"https://www.healthjobsuk.com{href}"
                })

            page += 1
            
        except Exception as e:
            print(f"❌ DEBUG ERROR: {str(e)}")
            break

    print(f"\n📊 DEBUG: Total jobs found = {len(jobs)}")  # NEW
    return jobs

def send_email(new_jobs):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"New NHS Jobs: {len(new_jobs)}"
        msg['From'] = EMAIL
        msg['To'] = EMAIL

        body = "🚨 New Medical/Dental Jobs:\n\n"
        for idx, job in enumerate(new_jobs, 1):
            body += f"{idx}. {job['Title']}\n{job['Link']}\n\n"
        body += "End of alerts \n\nBot 🤖"

        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
            print(f"✅ DEBUG: Email sent with {len(new_jobs)} jobs")
    
    except Exception as e:
        print(f"❌ DEBUG EMAIL FAILED: {str(e)}")
        raise

def monitor():
    print("🔄 DEBUG: Starting monitoring...")  # NEW
    previous_ids = load_previous_job_ids()
    print(f"🔢 DEBUG: Previous job count = {len(previous_ids)}")  # NEW
    
    current_jobs = scrape_all_pages()
    current_ids = {job["ID"] for job in current_jobs}
    
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_ids]
    print(f"🆕 DEBUG: New jobs detected = {len(new_jobs)}")  # NEW
    
    if new_jobs:
        send_email(new_jobs)
    else:
        print("✅ DEBUG: No new jobs found")
    
    save_current_job_ids(current_ids)
    print("🏁 DEBUG: Monitoring complete")  # NEW

if __name__ == "__main__":
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("Missing email credentials!")
    
    # NEW: Force fresh start when needed
    if os.path.exists("jobs.txt"):
        print("⚠️ DEBUG: Using existing jobs.txt")
    else:
        print("⚠️ DEBUG: Starting fresh (no jobs.txt)")
    
    monitor()
