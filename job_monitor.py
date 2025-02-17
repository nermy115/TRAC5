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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(URL, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    jobs = []
    # Find all <li> elements starting with "hj-job" in class
    job_listings = soup.find_all('li', class_=lambda x: x and x.startswith('hj-job'))
    
    for job_li in job_listings:
        # Get the direct <a> tag within the list item
        link_tag = job_li.find('a')
        if not link_tag:
            continue
            
        # Extract job ID and title
        href = link_tag.get('href', '')
        job_id = href.split('/')[-1].split('?')[0]  # Remove query parameters
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

        body = "New jobs found:\n\n"
        for job in new_jobs:
            body += f"★ {job['Title']}\n🔗 {job['Link']}\n\n"

        msg.attach(MIMEText(body, 'plain'))
        
        # Outlook/Hotmail SMTP configuration
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
        raise  # Fail workflow for visibility

def monitor():
    previous_job_ids = load_previous_job_ids()
    current_jobs = scrape_jobs()
    current_ids = [job["ID"] for job in current_jobs]
    
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_job_ids]
    
    if new_jobs:
        print(f"🚨 Found {len(new_jobs)} new jobs!")
        send_email(new_jobs)
    else:
        print("✅ No new jobs.")
    
    # Always update the tracking file
    save_current_job_ids(current_ids)

if __name__ == "__main__":
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("❌ Missing email credentials in environment variables!")
    monitor()
