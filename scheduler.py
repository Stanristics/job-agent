"""
Scheduler — searches for jobs immediately on startup,
then again every 24 hours as long as the app is running.

Since you shut down your Mac at night, just start the system
each morning and it will search automatically right away.
"""

import schedule
import time
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8000"

def trigger_search():
    logger.info(f"🔍 Searching for jobs — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    try:
        r = requests.post(f"{API_URL}/search", timeout=10)
        logger.info(f"✅ Search started: {r.json()}")
    except Exception as e:
        logger.error(f"❌ Failed to trigger search: {e}")

# ── Run immediately on startup ────────────────
logger.info("⏰ Job Agent Scheduler started — searching now...")
time.sleep(3)  # Give the API a moment to fully start
trigger_search()

# ── Then repeat every 24 hours ───────────────
schedule.every(24).hours.do(trigger_search)

logger.info("✅ Will search again every 24 hours while running.")
while True:
    schedule.run_pending()
    time.sleep(60)
