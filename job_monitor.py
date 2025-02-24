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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Use webdriver_manager only when not running on GitHub Actions.
if not os.getenv("GITHUB_ACTIONS"):
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
    
    if os.getenv("GITHUB_ACTIONS"):
        driver = webdriver.Chrome(options=options)
    else:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # Open the base URL
    driver.get(BASE_URL)
    time.sleep(2)  # Allow page to load
    
    # --- Accept Cookie Consent ---
    try:
        consent_button = driver.find_element(By.ID, "onetrust-accept-btn-handler")
        consent_button.click()
        print("✅ Cookie consent accepted.")
        time.sleep(1)  # Give a moment for the consent overlay to disappear
    except Exception as e:
        print("ℹ️ Cookie consent button not found or already handled:", e)
    
    # --- Simulate Clicking the Search Button ---
    try:
        search_button = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Search']")
        search_button.click()
        print("✅ Clicked the Search button.")
        # Wait explicitly for a job result element to appear (adjust the selector as needed)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.hj-job-result"))
        )
    except Exception as e:
        print("🚨 Error finding or clicking the search button or waiting for results:", e)
        driver.quit()
        return jobs

    # --- Pagination and Scraping ---
    page = 1
    while True:
        # Optionally, wait for the job listings container to update
        time.sleep(2)
        html = driver.page_source

        # Save debug HTML for manual inspection
        debug_filename = f"debug_page_{page}.html"
        with open(debug_filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"📄 Saved debug HTML for page {page} as '{debug_filename}'.")

        soup = BeautifulSoup(html, 'html.parser')
        # Update this selector based on your inspection of debug_page_1.html
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
            # Wait again for job listings to load on the new page
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.hj-job-result"))
            )
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
