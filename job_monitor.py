import os
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Configuration
EMAIL = os.environ["EMAIL"]
APP_PASSWORD = os.environ["APP_PASSWORD"]
URL = "https://www.healthjobsuk.com/job_list?JobSearch_re=MedicalAndDental&_sort=newest&_pg=1"

def load_previous_job_ids():
    try:
        with open("jobs.txt", "r") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return []

def save_current_job_ids(job_ids):
    with open("jobs.txt", "w") as f:
        f.write("\n".join(job_ids))

def scrape_jobs():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    response = requests.get(URL, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    jobs = []
    job_listings = soup.find_all('li', class_=lambda x: x and x.startswith('hj-job'))
    
    for job_li in job_listings:
        # Check category first
        category_div = job_li.find('div', class_='hj-sector')
        if not category_div:
            continue  # Skip jobs without category info
            
        category = category_div.text.strip().lower()
        allowed_keywords = ['medical', 'dental', 'doctor', 'dentist']
        if not any(keyword in category for keyword in allowed_keywords):
            print(f"⚠️ Skipped non-medical/dental job: {category}")
            continue

        # Extract job details
        link_tag = job_li.find('a')
        if not link_tag:
            continue
            
        href = link_tag.get('href', '')
        job_id = href.split('/')[-1].split('?')[0]
        title_div = link_tag.find('div', class_='hj-jobtitle')
        title = title_div.text.strip() if title_div else "Untitled Position"
        
        jobs.append({
            "ID": job_id,
            "Title": title,
            "Link": f"https://www.healthjobsuk.com{href}"
        })
    
    return jobs

def send_email(new_jobs):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"New NHS Medical/Dental Jobs: {len(new_jobs)}"
        msg['From'] = EMAIL
        msg['To'] = EMAIL

        body = "📌 **Medical/Dental Job Alerts**\n\n"
        for job in new_jobs:
            body += f"► {job['Title']}\n{job['Link']}\n{'─'*40}\n"
        body += "\nEnd of alerts 🎯"

        msg.attach(MIMEText(body, 'plain'))
        
        # Gmail SMTP
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
            print(f"✅ Sent {len(new_jobs)} medical/dental jobs!")
    
    except Exception as e:
        print(f"❌ Critical error: {str(e)}")
        raise

def monitor():
    previous_job_ids = load_previous_job_ids()
    current_jobs = scrape_jobs()
    current_ids = [job["ID"] for job in current_jobs]
    
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_job_ids]
    
    if new_jobs:
        send_email(new_jobs)
    else:
        print("✅ No new medical/dental jobs detected")
    
    save_current_job_ids(current_ids)

if __name__ == "__main__":
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("Missing credentials in environment variables")
    monitor()
