import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MATERIALS_DIR = DATA_DIR / "materials"
EXTRACTED_TEXT_DIR = DATA_DIR / "extracted_text"
METADATA_DIR = DATA_DIR / "metadata"

# Ensure directories exist
MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_TEXT_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR.mkdir(parents=True, exist_ok=True)

# Load .env file
load_dotenv(PROJECT_ROOT / ".env")

UMN_USERNAME = os.getenv("UMN_USERNAME", "")
UMN_PASSWORD = os.getenv("UMN_PASSWORD", "")
UMN_BASE_URL = os.getenv("UMN_BASE_URL", "https://elearning.umn.ac.id").rstrip("/")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MORNING_BRIEFING_TIME = os.getenv("MORNING_BRIEFING_TIME", "07:00")
EVENING_REMINDER_TIME = os.getenv("EVENING_REMINDER_TIME", "18:00")
AUTO_SYNC_HOURS = os.getenv("AUTO_SYNC_HOURS", "06:00,18:00")

SCHEDULE_FILE = METADATA_DIR / "class_schedule.json"
COURSES_FILE = METADATA_DIR / "courses.json"
ASSIGNMENTS_FILE = METADATA_DIR / "assignments.json"
SYNC_STATE_FILE = METADATA_DIR / "sync_state.json"
