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
    """Scrape jobs from all paginated Medical/Dental search results"""
    session = requests.Session()
    jobs = []
    page = 1
    
    while True:
        # Generate paginated URL with sorting by newest
        url = f"{BASE_URL}?_pg={page}&_sort=newest"
        
        try:
            response = session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find job listings
            job_listings = soup.find_all('li', class_=lambda x: x and x.startswith('hj-job'))
            
            if not job_listings:
                break  # No more pages
                
            # Process current page
            for job_li in job_listings:
                link_tag = job_li.find('a')
                if not link_tag:
                    continue
                
                href = link_tag.get('href', '')
                job_id = href.split('/')[-1].split('?')[0]
                title = link_tag.find('div', class_='hj-jobtitle').text.strip()
                
                jobs.append({
                    "ID": job_id,
                    "Title": title,
                    "Link": f"https://www.healthjobsuk.com{href}"
                })

            print(f"📄 Page {page}: Found {len(job_listings)} jobs")
            page += 1
            
        except Exception as e:
            print(f"⚠️ Error on page {page}: {str(e)}")
            break
    
    return jobs

def send_email(new_jobs):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"New NHS Medical/Dental Jobs: {len(new_jobs)}"
        msg['From'] = EMAIL
        msg['To'] = EMAIL

        body = "🚨 New Medical/Dental Job Alerts:\n\n"
        for job in new_jobs:
            body += f"► {job['Title']}\n🔗 {job['Link']}\n\n"
        body += "End of listings.\n\nBest,\nYour Job Bot 🤖"

        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
            print(f"✅ Email sent with {len(new_jobs)} new jobs!")
    
    except Exception as e:
        print(f"❌ Email failed: {str(e)}")
        raise

def monitor():
    previous_ids = load_previous_job_ids()
    current_jobs = scrape_all_pages()
    current_ids = {job["ID"] for job in current_jobs}
    
    new_jobs = [job for job in current_jobs if job["ID"] not in previous_ids]
    
    if new_jobs:
        send_email(new_jobs)
    else:
        print("✨ All Medical/Dental jobs are up-to-date")
    
    save_current_job_ids(current_ids)

if __name__ == "__main__":
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("Missing email credentials in environment variables")
    monitor()
