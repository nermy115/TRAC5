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
    jobs = []
    
    # Mimic browser interaction
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.healthjobsuk.com/"
    }
    session.headers.update(headers)
    
    # --- Critical Fix: Search Form Submission ---
    print("🔍 Pressing Search button programmatically...")
    form_data = {
        "JobSearch_Submit": "Search",  # Magic value to trigger search
        "_pg": "1",
        "_sort": "newest"
    }
    response = session.post(
        BASE_URL,
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    response.raise_for_status()
    
    # --- Pagination Loop ---
    page = 1
    while True:
        url = f"{BASE_URL}?_pg={page}&_sort=newest"
        print(f"\n🕵️ Scraping Page {page}: {url}")
        
        try:
            response = session.get(url)
            
            # Save debug HTML
            with open(f"debug_page_{page}.html", "w") as f:
                f.write(response.text)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Update selector based on your HTML analysis
            job_listings = soup.select('li.hj-job-result')  
            
            print(f"📄 Page {page}: Found {len(job_listings)} jobs")
            
            if not job_listings:
                break

            for job in job_listings:
                link = job.find('a', class_='hj-job-link')
                if not link:
                    continue
                
                href = link['href']
                job_id = href.split('/')[-1].split('?')[0]
                title = job.find('div', class_='hj-jobtitle').text.strip()
                
                jobs.append({
                    "ID": job_id,
                    "Title": title,
                    "Link": f"https://www.healthjobsuk.com{href}"
                })
                
            page += 1
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            break
    
    return jobs

def send_email(new_jobs):
    msg = MIMEMultipart()
    msg['Subject'] = f"New NHS Jobs: {len(new_jobs)} Found!"
    msg['From'] = EMAIL
    msg['To'] = EMAIL
    
    body = "🚨 New Medical/Dental Jobs:\n\n"
    for idx, job in enumerate(new_jobs, 1):
        body += f"{idx}. {job['Title']}\n{job['Link']}\n\n"
    body += "\nBot by YourName 🤖"
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✉️ Email sent with {len(new_jobs)} jobs")
    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")

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

# --- Main Entry Point ---
if __name__ == "__main__":
    # Validate environment vars
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("Missing email credentials in environment variables")
    
    # Force fresh start if needed
    if "--reset" in os.sys.argv:
        try:
            os.remove("jobs.txt")
            print("🗑️ Reset job tracking")
        except FileNotFoundError:
            pass
    
    monitor()
    print("🏁 Script completed")
