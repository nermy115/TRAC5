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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(URL, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    jobs = []
    job_listings = soup.find_all('li', class_=lambda x: x and x.startswith('hj-job'))
    
    for job_li in job_listings:
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
        msg['Subject'] = f"New NHS Jobs: {len(new_jobs)}"
        msg['From'] = EMAIL
        msg['To'] = EMAIL

        body = "🚨 New Job Alerts:\n\n"
        for job in new_jobs:
            body += f"▸ {job['Title']}\n{job['Link']}\n\n"
        body += "Cheers,\nYour Job Monitor 🤖"

        msg.attach(MIMEText(body, 'plain'))
        
        # Gmail SMTP configuration
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
            print("✅ Email notification sent!")
    
    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        raise

def monitor():
    previous_job_ids = load_previous_job_ids()
    current_jobs = scrape_jobs()
    current_ids = [job["ID"] for job in current_jobs]
    
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_job_ids]
    
    if new_jobs:
        print(f"Found {len(new_jobs)} new positions")
        send_email(new_jobs)
    else:
        print("No new jobs detected")
    
    save_current_job_ids(current_ids)

if __name__ == "__main__":
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("Missing email credentials in environment variables")
    monitor()
