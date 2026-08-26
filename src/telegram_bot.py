import json
import logging
import asyncio
from pathlib import Path
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from src.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    COURSES_FILE,
    ASSIGNMENTS_FILE,
    EXTRACTED_TEXT_DIR
)
from src.ai_service import AIService
from src.moodle_client import MoodleClient
from src.document_parser import DocumentParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("telegram_bot")

ai_service = AIService()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name or "Teman"

    welcome_text = (
        f"👋 **Halo, {user_name}!**\n\n"
        f"Aku adalah **AI Asisten E-Learning UMN** kamu. Aku siap bantu kamu mempersiapkan materi kuliah, cek deadline tugas, dan merangkum slide presentasi!\n\n"
        f"📌 **Fitur & Perintah:**\n"
        f"• ☀️ `/briefing` - Buat Daily Morning Class Prep & Materi Hari Ini\n"
        f"• 📋 `/tugas` - Cek daftar tugas & sisa waktu deadline\n"
        f"• 🔄 `/sync` - Tarik materi & tugas terbaru dari E-Learning UMN\n"
        f"• 📚 `/courses` - Cek daftar mata kuliah terdaftar\n"
        f"• ⚙️ `/id` - Cek Chat ID kamu (untuk konfigurasi `.env`)\n\n"
        f"💡 **Tanya Langsung:**\n"
        f"Kamu bisa langsung ketik pertanyaan apa saja di chat ini (contoh: _'Jelaskan materi pertemuan 1 Enterprise Architecture'_, _'Apa topik week 3 English 3?'_)."
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 **Telegram Chat ID Kamu:** `{chat_id}`\n\n"
        f"Salin ID di atas dan masukkan ke file `.env` di baris `TELEGRAM_CHAT_ID={chat_id}` untuk menerima notifikasi otomatis harian.",
        parse_mode=ParseMode.MARKDOWN
    )

async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("☕ *Sedang meracik briefing persiapan kuliah hari ini...*", parse_mode=ParseMode.MARKDOWN)
    briefing = ai_service.generate_morning_briefing()
    await update.message.reply_text(briefing, parse_mode=ParseMode.MARKDOWN)

async def tugas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminder = ai_service.generate_assignment_reminder()
    await update.message.reply_text(reminder, parse_mode=ParseMode.MARKDOWN)

async def courses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not COURSES_FILE.exists():
        await update.message.reply_text("ℹ️ Data mata kuliah belum ada. Jalankan `/sync` terlebih dahulu.")
        return

    try:
        courses = json.loads(COURSES_FILE.read_text(encoding="utf-8"))
        if not courses:
            await update.message.reply_text("⚠️ Belum ada mata kuliah yang tersimpan.")
            return

        lines = ["📚 **Daftar Mata Kuliah Terdeteksi:**\n"]
        for i, c in enumerate(courses, 1):
            cname = c.get("clean_name", c.get("title"))
            txt_dir = EXTRACTED_TEXT_DIR / cname
            num_docs = len(list(txt_dir.glob("*.txt"))) if txt_dir.exists() else 0
            lines.append(f"{i}. **{c.get('title')}**\n   📄 Dokumen Terekstrak: {num_docs} file\n")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Terjadi kesalahan: {e}")

async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔄 *Memulai sinkronisasi dengan E-Learning UMN...*", parse_mode=ParseMode.MARKDOWN)

    loop = asyncio.get_running_loop()

    def do_sync():
        client = MoodleClient()
        if not client.login():
            return False, "Gagal login ke E-Learning UMN. Cek kredensial di `.env`."

        courses = client.get_enrolled_courses()
        for course in courses:
            client.sync_course_materials(course)

        parser = DocumentParser()
        parser.process_all()

        client.get_assignments(courses)
        return True, f"Berhasil sinkronisasi {len(courses)} mata kuliah & materi terbaru!"

    try:
        success, msg = await loop.run_in_executor(None, do_sync)
        if success:
            await status_msg.edit_text(f"✅ **Sinkronisasi Selesai!**\n\n{msg}", parse_mode=ParseMode.MARKDOWN)
        else:
            await status_msg.edit_text(f"❌ **Sinkronisasi Gagal:** {msg}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await status_msg.edit_text(f"❌ Error saat sync: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_query = update.message.text
    if not user_query or user_query.startswith("/"):
        return

    # Send typing action
    await update.message.chat.send_action("typing")

    loop = asyncio.get_running_loop()
    answer = await loop.run_in_executor(None, ai_service.answer_query, user_query)

    # Chunk response if message is too long for Telegram (limit 4096 chars)
    if len(answer) > 4000:
        chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
    else:
        try:
            await update.message.reply_text(answer, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # Fallback to plain text if markdown parsing fails
            await update.message.reply_text(answer)

def create_bot_app():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN belum diatur!")
        return None

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("briefing", briefing_command))
    app.add_handler(CommandHandler("tugas", tugas_command))
    app.add_handler(CommandHandler("courses", courses_command))
    app.add_handler(CommandHandler("sync", sync_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app

if __name__ == "__main__":
    app = create_bot_app()
    if app:
        logger.info("Starting Telegram Bot...")
        app.run_polling()
