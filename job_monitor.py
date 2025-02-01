import os
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Configuration (GitHub Secrets)
EMAIL = os.environ.get("EMAIL")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
URL = "https://www.healthjobsuk.com/job_list?JobSearch_re=MedicalAndDental&_sort=newest&_pg=1"  # Replace with your filtered URL

# Track jobs in memory (resets on each GitHub Actions run)
previous_job_ids = []

def scrape_jobs():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    response = requests.get(URL, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    jobs = []
    job_listings = soup.find_all('li', class_='hj-job-list-entry')  # Update selector
    
    for job in job_listings:
        # Extract unique job ID (adjust based on HTML)
        title_tag = job.find('a', class_='hj-jobtitle')
        link = title_tag['href']
        job_id = link.split('/')[-1]  # Example: Extract from URL
        
        title = title_tag.text.strip()
        jobs.append({"ID": job_id, "Title": title, "Link": link})
    
    return jobs

def send_email(new_jobs):
    msg = MIMEMultipart()
    msg['Subject'] = f"New Job Postings: {len(new_jobs)}"
    msg['From'] = EMAIL
    msg['To'] = EMAIL

    body = "New jobs:\n\n"
    for job in new_jobs:
        body += f"Title: {job['Title']}\nLink: {job['Link']}\n\n"

    msg.attach(MIMEText(body, 'plain'))
    
    # Hotmail SMTP
    SMTP_SERVER = "smtp-mail.outlook.com"
    SMTP_PORT = 587
    
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)
        server.send_message(msg)

def monitor():
    global previous_job_ids
    current_jobs = scrape_jobs()
    current_ids = [job["ID"] for job in current_jobs]
    
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_job_ids]
    
    if new_jobs:
        print(f"Found {len(new_jobs)} new jobs!")
        send_email(new_jobs)
        previous_job_ids = current_ids  # Update for this run

if __name__ == "__main__":
    monitor()
