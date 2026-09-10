import logging
import threading
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    MORNING_BRIEFING_TIME,
    EVENING_REMINDER_TIME,
    AUTO_SYNC_HOURS,
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


_sync_lock = threading.Lock()

def job_sync_elearning():
    """Job: Sync materials and assignments from E-Learning."""
    if not _sync_lock.acquire(blocking=False):
        logger.info("[CRON] Sync sedang berjalan di proses lain. Menunggu selesai...")
        acquired = _sync_lock.acquire(timeout=120)
        if not acquired:
            logger.warning("[CRON] Timeout menunggu sync sebelumnya. Melewati sync ini.")
            return

    try:
        logger.info("[CRON] Starting automated E-Learning sync...")
        client = MoodleClient()
        if client.login():
            courses = client.get_enrolled_courses()
            for c in courses:
                client.sync_course_materials(c)
            parser = DocumentParser()
            parser.process_all()
            client.get_assignments(courses)
            logger.info("[CRON] E-Learning sync completed.")
        else:
            logger.warning("[CRON] Gagal login ke E-Learning UMN saat auto-sync.")
    except Exception as e:
        logger.error(f"[CRON] Error during auto-sync: {e}")
    finally:
        _sync_lock.release()

def job_morning_briefing():
    """Job: Generate and broadcast morning class prep briefing."""
    logger.info("[CRON] Triggering Morning Briefing...")
    # Pastikan data materi & tugas selalu fresh sebelum membuat briefing
    job_sync_elearning()

    ai_service = AIService()
    briefing = ai_service.generate_morning_briefing()
    send_telegram_alert(briefing)

def job_evening_assignment_reminder():
    """Job: Generate and broadcast assignment deadlines reminder."""
    logger.info("[CRON] Triggering Evening Assignment Reminder...")
    # Pastikan data tugas & deadline selalu fresh sebelum mengirim reminder
    job_sync_elearning()

    ai_service = AIService()
    reminder = ai_service.generate_assignment_reminder()
    send_telegram_alert(reminder)

def job_auto_do_assignments():
    """Job: AI mengerjakan tugas pending yang belum pernah dikerjakan, kirim .docx ke Telegram untuk direview."""
    if not AUTO_DO_ASSIGNMENTS:
        return
    logger.info("[CRON] Auto-do assignments: memeriksa tugas baru...")
    # Pastikan data tugas di-sync terlebih dahulu agar tugas baru terdeteksi
    job_sync_elearning()

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

    # Auto-sync schedule from AUTO_SYNC_HOURS (mis. "06:00,18:00")
    sync_hours = AUTO_SYNC_HOURS or "06:00,18:00"
    for idx, sync_time in enumerate(sync_hours.split(",")):
        sync_time = sync_time.strip()
        if not sync_time:
            continue
        try:
            s_hour, s_min = sync_time.split(":")
            scheduler.add_job(
                job_sync_elearning,
                CronTrigger(hour=int(s_hour), minute=int(s_min)),
                id=f"elearning_sync_{idx}",
                name=f"Auto Sync E-Learning Materials ({sync_time})"
            )
            logger.info(f"Scheduled Auto-Sync at {sync_time} WIB")
        except Exception as e:
            logger.error(f"Invalid sync time '{sync_time}': {e}")

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
