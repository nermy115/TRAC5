import os
import sys
import requests

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    response = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })
    print(f"Telegram: {response.status_code}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python trac_apply.py <job_url>")
        sys.exit(1)

    job_url = sys.argv[1]
    send_telegram(
        f"🏥 *New NHS Job Found*\n\n"
        f"*URL:* {job_url}"
    )
