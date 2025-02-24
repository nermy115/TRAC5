import os
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuration ---
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
    jobs = []
    
    # --- Selenium Setup ---
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    
    # Try installing ChromeDriver using webdriver-manager.
    try:
        driver_path = ChromeDriverManager().install()
    except ValueError as e:
        print("🚨 ChromeDriverManager error:", e)
        # Fallback to a specific version known to work.
        driver_path = ChromeDriverManager(version="132.0.0").install()
    
    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    
    # Open the base URL
    driver.get(BASE_URL)
    time.sleep(2)  # Allow page to load

    # --- Simulate Clicking the Search Button ---
    try:
        # Adjust the XPath if needed; this looks for an input with type "submit" and value "Search".
        search_button = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Search']")
        search_button.click()
        print("✅ Clicked the Search button.")
    except Exception as e:
        print("🚨 Error finding or clicking the search button:", e)
        driver.quit()
        return jobs

    # Wait for the results page to load
    time.sleep(3)

    # --- Pagination and Scraping ---
    page = 1
    while True:
        time.sleep(2)
        html = driver.page_source

        # Save debug HTML for manual inspection
        debug_filename = f"debug_page_{page}.html"
        with open(debug_filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"📄 Saved debug HTML for page {page} as '{debug_filename}'.")

        soup = BeautifulSoup(html, 'html.parser')
        # Update this selector if the page structure changes
        job_listings = soup.select('li.hj-job-result')
        print(f"🔍 Found {len(job_listings)} jobs on page {page}")

        if not job_listings:
            break

        for job in job_listings:
            link_tag = job.find('a', class_='hj-job-link')
            if not link_tag:
                continue

            href = link_tag.get('href', '')
            job_id = href.split('/')[-1]
            title_div = job.find('div', class_='hj-jobtitle')
            title = title_div.text.strip() if title_div else "No Title"

            jobs.append({
                "ID": job_id,
                "Title": title,
                "Link": f"https://www.healthjobsuk.com{href}"
            })

        # Try to click the "next" page button; adjust the selector if needed.
        try:
            next_button = driver.find_element(By.XPATH, "//a[contains(@class, 'next')]")
            next_button.click()
            print(f"➡️ Navigating to page {page + 1}...")
            page += 1
        except Exception as e:
            print("✅ No next page found, ending pagination.")
            break

    driver.quit()
    return jobs

def send_email(new_jobs):
    if not new_jobs:
        return

    msg = MIMEMultipart()
    msg['Subject'] = f"New NHS Jobs: {len(new_jobs)} Found!"
    msg['From'] = EMAIL
    msg['To'] = EMAIL

    body = "🚨 New Medical/Dental Jobs:\n\n"
    for job in new_jobs:
        body += f"- {job['Title']}\n   {job['Link']}\n\n"
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✉️ Sent email with {len(new_jobs)} jobs")
    except Exception as e:
        print(f"🚨 Email failed: {str(e)}")

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

# --- Main ---
if __name__ == "__main__":
    monitor()
    print("🏁 Script completed")
