def scrape_all_pages():
    session = requests.Session()
    jobs = []
    page = 1

    # Step 1: Press "Search" with parameters, handle pagination via POST
    while True:
        form_data = {
            "JobSearch_Submit": "Search",
            "_pg": str(page),  # Dynamic page number 
            "_sort": "newest",
            "JobSearch.re": "MedicalAndDental"  # Hidden field (verify via debug)
        }

        # Always POST for every page
        response = session.post(
            BASE_URL,
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()

        print(f"\n🕵️ Scraping Page {page} [POST] {BASE_URL}")
        
        # Save debug HTML with POST response
        with open(f"debug_page_{page}.html", "w") as f:
            f.write(response.text)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        job_listings = soup.select('li.hj-job-result')  # Update selector
        
        print(f"📄 Found {len(job_listings)} jobs on page {page}")
        
        if not job_listings:
            break

        # Extract jobs here...
        for job in job_listings:
            # ...your existing extraction code...

        page += 1

    return jobs


def send_email(new_jobs):
    msg = MIMEMultipart()
    msg['Subject'] = f"New NHS Jobs: {len(new_jobs)} Found!"
    msg['From'] = EMAIL
    msg['To'] = EMAIL
    
    body = "🚨 New Medical/Dental Jobs:\n\n"
    for idx, job in enumerate(new_jobs, 1):
        body += f"{idx}. {job['Title']}\n{job['Link']}\n\n"
    body += "\nBot by YourName 🤖"
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✉️ Email sent with {len(new_jobs)} jobs")
    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")

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

# --- Main Entry Point ---
if __name__ == "__main__":
    # Validate environment vars
    if not EMAIL or not APP_PASSWORD:
        raise ValueError("Missing email credentials in environment variables")
    
    # Force fresh start if needed
    if "--reset" in os.sys.argv:
        try:
            os.remove("jobs.txt")
            print("🗑️ Reset job tracking")
        except FileNotFoundError:
            pass
    
    monitor()
    print("🏁 Script completed")
