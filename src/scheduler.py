import logging
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    MORNING_BRIEFING_TIME,
    EVENING_REMINDER_TIME,
    AUTO_DO_ASSIGNMENTS,
    AUTO_DO_ASSIGNMENTS_TIME,
    AUTO_DO_MAX_PER_RUN
)
from src.ai_service import AIService
from src.assignment_worker import AssignmentWorker
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

def send_telegram_document(file_path, caption: str = ""):
    """Kirim file (mis. hasil tugas .docx) ke Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram token or Chat ID not configured. Skipping document send.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as fh:
            res = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]},
                files={"document": fh},
                timeout=120
            )
        if res.status_code != 200:
            logger.error(f"Failed to send Telegram document: {res.text[:300]}")
            return False
        logger.info(f"Telegram document sent: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error sending Telegram document: {e}")
        return False


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

def job_auto_do_assignments():
    """Job: AI mengerjakan tugas pending yang belum pernah dikerjakan, kirim .docx ke Telegram untuk direview."""
    if not AUTO_DO_ASSIGNMENTS:
        return
    logger.info("[CRON] Auto-do assignments: memeriksa tugas baru...")
    try:
        worker = AssignmentWorker()
        pending = worker.list_pending()
        done = set(worker.list_done_urls())
        todo = [a for a in pending if a.get("url") not in done][:AUTO_DO_MAX_PER_RUN]

        if not todo:
            logger.info("[CRON] Tidak ada tugas baru yang perlu dikerjakan.")
            return

        send_telegram_alert(f"🤖 *Auto-Worker:* Ada *{len(todo)}* tugas baru. AI mulai mengerjakan — hasilnya dikirim untuk direview.")
        for a in todo:
            result = worker.work_on_assignment(a)
            if result.get("ok"):
                caption = f"📝 {a.get('course_name', '')} — {a.get('title', '')}\n🧠 {result.get('summary', '')[:600]}"
                for f in result.get("files", []):
                    send_telegram_document(f, caption)
                send_telegram_alert("👀 File sudah dikirim. *Review dulu*, lalu kumpulkan manual ke e-learning ya!")
            else:
                send_telegram_alert(f"❌ Gagal mengerjakan _{a.get('title')}_: {result.get('error', '?')[:300]}")
    except Exception as e:
        logger.error(f"[CRON] Error auto-do assignments: {e}")

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

    # Auto-do assignments (AI kerjakan tugas baru, kirim .docx ke Telegram)
    try:
        a_hour, a_min = AUTO_DO_ASSIGNMENTS_TIME.split(":")
        scheduler.add_job(
            job_auto_do_assignments,
            CronTrigger(hour=int(a_hour), minute=int(a_min)),
            id="auto_do_assignments",
            name="AI Auto-Do Assignments"
        )
        logger.info(f"Scheduled Auto-Do Assignments at {AUTO_DO_ASSIGNMENTS_TIME} WIB (aktif: {AUTO_DO_ASSIGNMENTS})")
    except Exception as e:
        logger.error(f"Invalid AUTO_DO_ASSIGNMENTS_TIME format: {e}")

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
