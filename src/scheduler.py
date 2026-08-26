import logging
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    MORNING_BRIEFING_TIME,
    EVENING_REMINDER_TIME
)
from src.ai_service import AIService
from src.moodle_client import MoodleClient
from src.document_parser import DocumentParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scheduler")

def send_telegram_alert(text: str):
    """Send alert message directly to configured Telegram Chat ID."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram token or Chat ID not configured. Skipping alert.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code != 200:
            logger.error(f"Failed to send Telegram alert: {res.text}")
        else:
            logger.info("Telegram scheduled alert delivered successfully.")
    except Exception as e:
        logger.error(f"Error sending Telegram alert: {e}")

def job_sync_elearning():
    """Job: Sync materials and assignments from E-Learning."""
    logger.info("[CRON] Starting automated E-Learning sync...")
    try:
        client = MoodleClient()
        if client.login():
            courses = client.get_enrolled_courses()
            for c in courses:
                client.sync_course_materials(c)
            parser = DocumentParser()
            parser.process_all()
            client.get_assignments(courses)
            logger.info("[CRON] E-Learning sync completed.")
    except Exception as e:
        logger.error(f"[CRON] Error during auto-sync: {e}")

def job_morning_briefing():
    """Job: Generate and broadcast morning class prep briefing."""
    logger.info("[CRON] Triggering Morning Briefing...")
    # First ensure we have fresh data
    job_sync_elearning()

    ai_service = AIService()
    briefing = ai_service.generate_morning_briefing()
    send_telegram_alert(briefing)

def job_evening_assignment_reminder():
    """Job: Generate and broadcast assignment deadlines reminder."""
    logger.info("[CRON] Triggering Evening Assignment Reminder...")
    ai_service = AIService()
    reminder = ai_service.generate_assignment_reminder()
    send_telegram_alert(reminder)

def start_scheduler():
    """Start APScheduler in the background."""
    scheduler = BackgroundScheduler()

    # Parse morning briefing hour & minute
    try:
        m_hour, m_min = MORNING_BRIEFING_TIME.split(":")
        scheduler.add_job(
            job_morning_briefing,
            CronTrigger(hour=int(m_hour), minute=int(m_min)),
            id="morning_briefing",
            name="Daily Morning Class Prep Briefing"
        )
        logger.info(f"Scheduled Morning Briefing at {MORNING_BRIEFING_TIME} WIB")
    except Exception as e:
        logger.error(f"Invalid MORNING_BRIEFING_TIME format: {e}")

    # Parse evening reminder hour & minute
    try:
        e_hour, e_min = EVENING_REMINDER_TIME.split(":")
        scheduler.add_job(
            job_evening_assignment_reminder,
            CronTrigger(hour=int(e_hour), minute=int(e_min)),
            id="evening_reminder",
            name="Daily Evening Assignment Reminder"
        )
        logger.info(f"Scheduled Evening Reminder at {EVENING_REMINDER_TIME} WIB")
    except Exception as e:
        logger.error(f"Invalid EVENING_REMINDER_TIME format: {e}")

    # Auto-sync twice daily (e.g. 06:00 and 17:30)
    scheduler.add_job(
        job_sync_elearning,
        CronTrigger(hour="6,17", minute="30"),
        id="elearning_sync",
        name="Auto Sync E-Learning Materials"
    )

    scheduler.start()
    return scheduler

if __name__ == "__main__":
    scheduler = start_scheduler()
    logger.info("Scheduler running in standalone mode. Press Ctrl+C to exit.")
    import time
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
