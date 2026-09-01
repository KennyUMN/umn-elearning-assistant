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

# --- LLM Provider Configuration ---
# Provider default saat pertama kali jalan: "gemini" | "openrouter"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

# Gemini (default)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Opsional: override model Gemini utama (mis. "models/gemini-flash-lite-latest").
# Kalau kosong, pakai daftar fallback bawaan di ai_service.py.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip()

# OpenRouter (https://openrouter.ai/keys)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "minimax/minimax-m3:free").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")

# State provider/model aktif (hasil perintah /model di Telegram) — bertahan restart
LLM_STATE_FILE = METADATA_DIR / "llm_state.json"

# --- Assignment Auto-Worker (AI kerjakan tugas, kirim file ke Telegram) ---
# Identitas untuk header dokumen tugas. Kosongkan STUDENT_NAME untuk auto-isi dari email UMN.
STUDENT_NAME = os.getenv("STUDENT_NAME", "").strip()
STUDENT_NIM = os.getenv("STUDENT_NIM", "").strip()
# Cron otomatis: kerjakan tugas pending yang belum pernah dikerjakan
AUTO_DO_ASSIGNMENTS = os.getenv("AUTO_DO_ASSIGNMENTS", "true").strip().lower() in ("1", "true", "yes", "ya")
AUTO_DO_ASSIGNMENTS_TIME = os.getenv("AUTO_DO_ASSIGNMENTS_TIME", "19:00").strip()
AUTO_DO_MAX_PER_RUN = int(os.getenv("AUTO_DO_MAX_PER_RUN", "2"))

# Direktori & file state tugas
ASSIGNMENTS_ATTACH_DIR = DATA_DIR / "assignment_attachments"
ASSIGNMENTS_OUTPUT_DIR = DATA_DIR / "assignments_output"
ASSIGNMENT_OUTPUTS_FILE = METADATA_DIR / "assignment_outputs.json"
ASSIGNMENTS_ATTACH_DIR.mkdir(parents=True, exist_ok=True)
ASSIGNMENTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MORNING_BRIEFING_TIME = os.getenv("MORNING_BRIEFING_TIME", "07:00")
EVENING_REMINDER_TIME = os.getenv("EVENING_REMINDER_TIME", "18:00")
AUTO_SYNC_HOURS = os.getenv("AUTO_SYNC_HOURS", "06:00,18:00")

# Tanggal kuliah pertama minggu-1 semester berjalan (format YYYY-MM-DD).
# Dipakai buat menghitung "minggu semester ke-N" agar briefing sesuai roadmap RPKPS.
# Sumber: Kalender Akademik UMN 2026/2027 (rev. 15-07-2026) — Ganjil mulai 24 Agustus 2026.
SEMESTER_START_DATE = os.getenv("SEMESTER_START_DATE", "").strip()
# Rentang libur akademik dalam semester (UTS, dll): "YYYY-MM-DD:YYYY-MM-DD" dipisah koma.
# Minggu yang jatuh di rentang ini tidak dihitung sebagai minggu perkuliahan.
# UTS Ganjil 2026/2027: 12-24 Oktober 2026.
SEMESTER_BREAKS = os.getenv("SEMESTER_BREAKS", "").strip()

SCHEDULE_FILE = METADATA_DIR / "class_schedule.json"
COURSES_FILE = METADATA_DIR / "courses.json"
ASSIGNMENTS_FILE = METADATA_DIR / "assignments.json"
SYNC_STATE_FILE = METADATA_DIR / "sync_state.json"
