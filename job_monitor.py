import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.healthjobsuk.com/job_search/s2/Medical_Dental"

def scrape_all_pages():
    session = requests.Session()
    jobs = []
    
    # 1. Load the Medical/Dental URL
    print("🌐 Loading Medical/Dental page...")
    initial_response = session.get(BASE_URL)
    initial_response.raise_for_status()
    
    # 2. Submit the "Search" form to initialize filters
    search_url = BASE_URL
    form_data = {
        "JobSearch_Submit": "Search",  # Critical: Triggers form processing
        "_pg": "1",                    # Start at page 1
        "_sort": "newest"              # Sorting as per your need
    }
    
    print("🔍 Pressing Search button...")
    search_response = session.post(
        search_url,
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    search_response.raise_for_status()
    
    # 3. Now handle pagination with GET requests
    page = 1
    while True:
        url = f"{BASE_URL}?_pg={page}&_sort=newest"
        print(f"\n🕵️ Scraping Page {page}: {url}")
        
        response = session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # TODO: Update these selectors based on your actual HTML
        job_listings = soup.select('li.hj-job')  
        
        print(f"Found {len(job_listings)} jobs on page {page}")
        if not job_listings:
            break
        
        # Job extraction logic here...
        for job in job_listings:
            # Extract ID, title, link...
            jobs.append(job)  
            
        page += 1
    
    return jobs
def send_email(new_jobs):
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
