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
from src.ai_service import AIService, get_llm_state, set_llm_state, MODEL_PRESETS, VALID_PROVIDERS
from src.config import OPENROUTER_API_KEY
from src.assignment_worker import AssignmentWorker
from src.moodle_client import MoodleClient
from src.document_parser import DocumentParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("telegram_bot")

ai_service = AIService()
assignment_worker = AssignmentWorker()

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
        f"• 📝 `/kerjakan` - AI kerjakan tugas & kirim file .docx siap review\n"
        f"• 🤖 `/model` - Ganti provider/model LLM (Gemini / OpenRouter)\n"
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

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lihat / ganti provider & model LLM yang aktif.
    Pemakaian:
      /model                     -> info provider & model aktif
      /model gemini              -> pakai Gemini (default)
      /model openrouter          -> pakai OpenRouter (default minimax/minimax-m3:free)
      /model openrouter <model>  -> pakai model OpenRouter spesifik
    """
    args = context.args or []

    if not args:
        state = get_llm_state()
        gemini_ready = "✅" if ai_service.is_configured() else "❌ (API key belum di-set)"
        openrouter_ready = "✅" if OPENROUTER_API_KEY else "❌ (API key belum di-set)"
        text = (
            f"🤖 **LLM Aktif Saat Ini**\n"
            f"• Provider: `{state['provider']}`\n"
            f"• Model: `{state['model']}`\n\n"
            f"**Provider tersedia:**\n"
            f"1. `gemini` {gemini_ready}\n"
            f"   Model: `{MODEL_PRESETS['gemini']['default']}`\n"
            f"2. `openrouter` {openrouter_ready}\n"
            f"   Model: `{MODEL_PRESETS['openrouter']['default']}`\n\n"
            f"**Cara ganti:**\n"
            f"• `/model gemini` — balik ke Gemini\n"
            f"• `/model openrouter` — pakai MiniMax M3 (free) via OpenRouter\n"
            f"• `/model openrouter <model_id>` — pakai model OpenRouter lain\n"
            f"  contoh: `/model openrouter deepseek/deepseek-chat-v3.1:free`"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    provider = args[0].strip().lower()
    custom_model = args[1].strip() if len(args) > 1 else None

    if provider not in VALID_PROVIDERS:
        await update.message.reply_text(
            f"❌ Provider `{provider}` tidak dikenal. Pilihan: `{', '.join(VALID_PROVIDERS)}`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if provider == "openrouter" and not OPENROUTER_API_KEY:
        await update.message.reply_text(
            "⚠️ `OPENROUTER_API_KEY` belum diatur di file `.env`.\n\n"
            "Ambil API key gratis di https://openrouter.ai/keys, lalu tambahkan ke `.env` dan restart service.\n"
            "Sementara ini tetap pakai `/model gemini` ya.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        state = set_llm_state(provider, custom_model)
        await update.message.reply_text(
            f"✅ **LLM berhasil diganti!**\n"
            f"• Provider: `{state['provider']}`\n"
            f"• Model: `{state['model']}`\n\n"
            f"Semua fitur (briefing, reminder, AI tutor) sekarang pakai model ini — termasuk job cron otomatis. "
            f"Pengaturan ini bertahan meski service di-restart.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal ganti model: {e}")

def _format_pending_list(pending) -> str:
    lines = ["📝 **Tugas Pending (belum disubmit):**\n"]
    for i, a in enumerate(pending, 1):
        lines.append(
            f"{i}. **{a.get('title', '-')}**\n"
            f"   📚 {a.get('course_name', '-')} | ⏰ {a.get('due_date', '-')}"
            f" (_{a.get('time_remaining', '-')}_)\n"
        )
    lines.append("\nKetik `/kerjakan <nomor>` biar AI kerjakan tugasnya,")
    lines.append("atau `/kerjakan semua` (maks 3 tugas terdekat deadline).")
    lines.append("\n⚠️ _Hasil dikirim sebagai file .docx untuk **direview dulu** — pengumpulan tetap kamu lakukan sendiri di e-learning._")
    return "\n".join(lines)


async def _send_assignment_result(update: Update, result: dict):
    """Kirim file hasil + ringkasan ke chat Telegram."""
    for fpath in result.get("files", []):
        path = Path(fpath)
        if not path.exists():
            continue
        caption = f"📄 {path.name}"
        with open(path, "rb") as fh:
            await update.message.reply_document(document=fh, filename=path.name, caption=caption)

    summary = result.get("summary") or "(Tidak ada ringkasan dari AI.)"
    attachments = result.get("attachments") or []
    text = (
        f"✅ **Tugas selesai dikerjakan AI!**\n\n"
        f"📝 {result.get('assignment')}\n\n"
        f"🧠 **Ringkasan pengerjaan:**\n{summary}\n\n"
        f"📎 Sumber soal: {len(attachments)} lampiran" + (f" ({', '.join(attachments[:3])})" if attachments else "") + "\n\n"
        f"👀 **Jangan lupa review sebelum dikumpulin ya!** File di atas tinggal kamu unduh, cek, lalu upload manual ke e-learning."
    )
    for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text(chunk)


async def kerjakan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI mengerjakan tugas e-learning & kirim file hasil ke Telegram untuk direview."""
    args = context.args or []
    pending = assignment_worker.list_pending()

    if not pending:
        await update.message.reply_text(
            "🎉 **Tidak ada tugas pending yang terdeteksi!**\n\n"
            "Coba `/sync` dulu kalau baru ada tugas yang di-upload dosen.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # /kerjakan (tanpa argumen) -> daftar tugas pending
    if not args:
        await update.message.reply_text(_format_pending_list(pending), parse_mode=ParseMode.MARKDOWN)
        return

    # /kerjakan semua -> kerjakan maks 3 tugas terdekat deadline
    if args[0].lower() in ("semua", "all"):
        targets = pending[:3]
        await update.message.reply_text(
            f"🤖 Oke, AI akan mengerjakan **{len(targets)} tugas** satu per satu.\n"
            f"_Ini butuh waktu (±2 menit per tugas) — hasil dikirim bertahap._",
            parse_mode=ParseMode.MARKDOWN
        )
        for i, a in enumerate(targets, 1):
            await update.message.reply_text(
                f"⏳ *[{i}/{len(targets)}]* Mengambil soal & mengerjakan: _{a.get('title')}_...",
                parse_mode=ParseMode.MARKDOWN
            )
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, assignment_worker.work_on_assignment, a)
            if result.get("ok"):
                await _send_assignment_result(update, result)
            else:
                await update.message.reply_text(f"❌ Gagal mengerjakan _{a.get('title')}_: {result.get('error')}")
        return

    # /kerjakan <nomor>
    try:
        idx = int(args[0]) - 1
    except ValueError:
        await update.message.reply_text("Format: `/kerjakan <nomor>` (lihat daftar di `/kerjakan`)", parse_mode=ParseMode.MARKDOWN)
        return

    if idx < 0 or idx >= len(pending):
        await update.message.reply_text(f"❌ Nomor {args[0]} tidak ada. Cek daftar dengan `/kerjakan`.", parse_mode=ParseMode.MARKDOWN)
        return

    assignment = pending[idx]
    status_msg = await update.message.reply_text(
        f"📥 *Mengambil soal & lampiran dari e-learning...*\n📝 _{assignment.get('title')}_",
        parse_mode=ParseMode.MARKDOWN
    )

    loop = asyncio.get_running_loop()

    def do_work():
        return assignment_worker.work_on_assignment(assignment)

    try:
        await status_msg.edit_text(
            f"🧠 *AI sedang mengerjakan tugas...*\n📝 _{assignment.get('title')}_\n\n_Esteksi 1-3 menit, jangan kemana-mana :)_",
            parse_mode=ParseMode.MARKDOWN
        )
        result = await loop.run_in_executor(None, do_work)
    except Exception as e:
        await status_msg.edit_text(f"❌ Error saat mengerjakan tugas: {e}")
        return

    if result.get("ok"):
        await _send_assignment_result(update, result)
    else:
        await status_msg.edit_text(f"❌ Gagal mengerjakan tugas: {result.get('error')}")

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
    user_query = update.message.text if update.message else ""
    if not user_query or user_query.startswith("/"):
        return

    logger.info(f"Received user query: {user_query[:60]}")

    try:
        # Send typing action
        await update.message.chat.send_action("typing")

        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, ai_service.answer_query, user_query)

        if not answer:
            answer = "ℹ️ Maaf, tidak ada respons yang dihasilkan."

        # Chunk response if message is too long for Telegram (limit 4096 chars)
        if len(answer) > 4000:
            chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
            for chunk in chunks:
                try:
                    await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
                except Exception:
                    await update.message.reply_text(chunk)
        else:
            try:
                await update.message.reply_text(answer, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                # Fallback to plain text if markdown parsing fails
                await update.message.reply_text(answer)
    except Exception as e:
        logger.exception(f"Error handling user message: {e}")
        try:
            await update.message.reply_text(f"❌ Terjadi kesalahan saat memproses pertanyaan: {e}")
        except Exception:
            pass

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
    app.add_handler(CommandHandler("kerjakan", kerjakan_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("sync", sync_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app

if __name__ == "__main__":
    app = create_bot_app()
    if app:
        logger.info("Starting Telegram Bot...")
        app.run_polling()
