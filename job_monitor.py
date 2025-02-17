import os
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Configuration
EMAIL = os.environ["EMAIL"]
APP_PASSWORD = os.environ["APP_PASSWORD"]

def load_previous_job_ids():
    try:
        with open("jobs.txt", "r") as f:
            return set(f.read().splitlines())  # Use set for faster lookups
    except FileNotFoundError:
        return set()

def save_current_job_ids(job_ids):
    with open("jobs.txt", "w") as f:
        f.write("\n".join(job_ids))

def init_session():
    """Submit category form to filter Medical/Dental jobs"""
    session = requests.Session()
    
    # Configure headers to mimic browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # Submit category selection form (HealthcareSector=14 → Medical+Dental)
    form_data = {
        "HealthcareSector": "14",
        "JobType": "",
        "Country": "",
        "JobLevel": "",
        "Keyword": ""
    }
    
    session.post(
        "https://www.healthjobsuk.com/select_sector",
        data=form_data,
        headers=headers
    )
    
    return session

def scrape_all_pages(session):
    """Scrape jobs from all paginated results"""
    base_url = "https://www.healthjobsuk.com/job_list?JobSearch_re=MedicalAndDental&_sort=newest&_pg={page}"
    jobs = []
    page = 1
    
    while True:
        url = base_url.format(page=page)
        try:
            response = session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_elements = soup.find_all('li', class_=lambda x: x and x.startswith('hj-job'))
            
            if not job_elements:
                break  # No more pages

            # Extract job details
            for job_li in job_elements:
                link = job_li.find('a')
                if not link:
                    continue
                
                href = link.get('href', '')
                job_id = href.split('/')[-1].split('?')[0].strip()
                title = link.find('div', class_='hj-jobtitle').text.strip() if link.find('div', class_='hj-jobtitle') else "No Title"
                
                jobs.append({
                    "ID": job_id,
                    "Title": title,
                    "Link": f"https://www.healthjobsuk.com{href}"
                })

            print(f"Scraped {len(job_elements)} jobs from page {page}")
            page += 1
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page}: {e}")
            break
    
    return jobs

def send_email(new_jobs):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"New NHS Medical/Dental Jobs: {len(new_jobs)}"
        msg['From'] = EMAIL
        msg['To'] = EMAIL

        body = "📌 **Medical & Dental Job Alerts**\n\n"
        for idx, job in enumerate(new_jobs, 1):
            body += f"{idx}. {job['Title']}\n{job['Link']}\n\n"
        body += "End of alerts 🚨"

        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
            print(f"⚠️ Alert: Sent {len(new_jobs)} new jobs!")
    
    except Exception as e:
        print(f"Email failed: {str(e)}")
        raise

def monitor():
    # Initialize session with Medical/Dental filter
    session = init_session()
    
    # Get previous and current jobs
    previous_ids = load_previous_job_ids()
    current_jobs = scrape_all_pages(session)
    current_ids = {job["ID"] for job in current_jobs}
    
    # Find new jobs
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_ids]
    
    if new_jobs:
        send_email(new_jobs)
    else:
        print("✅ All jobs are up-to-date in Medical/Dental")
    
    save_current_job_ids(current_ids)

if __name__ == "__main__":
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("Missing EMAIL or APP_PASSWORD in environment variables")
    monitor()
