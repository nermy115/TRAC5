import os
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Configuration (GitHub Secrets)
EMAIL = os.environ.get("EMAIL")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124"}
    response = requests.get(URL, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    jobs = []
    job_listings = soup.find_all('li', class_='hj-job-list-entry')
    
    for job in job_listings:
        title_tag = job.find('a', class_='hj-jobtitle')
        if title_tag:
            link = title_tag.get('href', '')
            job_id = link.split('/')[-1]
            title = title_tag.text.strip()
            jobs.append({"ID": job_id, "Title": title, "Link": link})
    
    return jobs

def send_email(new_jobs):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"New NHS Jobs: {len(new_jobs)}"
        msg['From'] = EMAIL
        msg['To'] = EMAIL

        body = "New jobs:\n\n"
        for job in new_jobs:
            body += f"Title: {job['Title']}\nLink: {job['Link']}\n\n"

        msg.attach(MIMEText(body, 'plain'))
        
        # Outlook/Hotmail SMTP
        SMTP_SERVER = "smtp-mail.outlook.com"
        SMTP_PORT = 587
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
            print("✅ Email sent successfully!")
    
    except Exception as e:
        print(f"❌ Email failed: {str(e)}")
        raise  # Fail workflow to show error

def monitor():
    previous_job_ids = load_previous_job_ids()
    current_jobs = scrape_jobs()
    current_ids = [job["ID"] for job in current_jobs]
    
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_job_ids]
    
    if new_jobs:
        print(f"🚨 Found {len(new_jobs)} new jobs!")
        send_email(new_jobs)
        save_current_job_ids(current_ids)
    else:
        print("✅ No new jobs.")
        save_current_job_ids(current_ids)

if __name__ == "__main__":
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("Missing email credentials in environment variables!")
    monitor()
