"""Conversation Manager — Mengelola memori percakapan multi-turn & riwayat aktivitas bot.

Menyimpan riwayat chat per chat_id ke data/metadata/chat_histories/{chat_id}.json agar:
1. Bot tidak pikun saat user bertanya follow-up ("iya", "bukan yang itu", "jelaskan lebih lanjut").
2. Bot mengenali topik/mata kuliah aktif dari percakapan sebelumnya jika query user pendek.
3. Bot mengetahui tugas/tindakan yang baru saja dikerjakan (dari assignment_outputs.json).
4. Riwayat tersimpan persisten bahkan jika container di-restart.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.config import ASSIGNMENT_OUTPUTS_FILE, METADATA_DIR

logger = logging.getLogger("conversation_manager")

CHAT_HISTORIES_DIR = METADATA_DIR / "chat_histories"
MAX_HISTORY_TURNS = 14  # 7 user + 7 assistant


class ConversationManager:
    def __init__(self, storage_dir: Path = CHAT_HISTORIES_DIR):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _file_for_chat(self, chat_id: int) -> Path:
        return self.storage_dir / f"history_{chat_id}.json"

    def get_history(self, chat_id: int) -> List[Dict[str, str]]:
        f = self._file_for_chat(chat_id)
        if not f.exists():
            return []
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Gagal membaca chat history {chat_id}: {e}")
            return []

    def save_history(self, chat_id: int, history: List[Dict[str, str]]) -> None:
        f = self._file_for_chat(chat_id)
        try:
            trimmed = history[-MAX_HISTORY_TURNS:]
            f.write_text(json.dumps(trimmed, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Gagal menyimpan chat history {chat_id}: {e}")

    def add_user_message(self, chat_id: int, text: str) -> None:
        history = self.get_history(chat_id)
        history.append({
            "role": "user",
            "text": text,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        })
        self.save_history(chat_id, history)

    def add_assistant_message(self, chat_id: int, text: str) -> None:
        history = self.get_history(chat_id)
        history.append({
            "role": "assistant",
            "text": text,
            "timestamp": datetime.now().isoformat(timespec="seconds")
        })
        self.save_history(chat_id, history)

    def clear_history(self, chat_id: int) -> bool:
        f = self._file_for_chat(chat_id)
        if f.exists():
            try:
                f.unlink()
                return True
            except Exception as e:
                logger.warning(f"Gagal menghapus history {chat_id}: {e}")
        return False

    def format_history_for_prompt(self, chat_id: int, max_turns: int = 8) -> str:
        """Format percakapan terakhir untuk diinjeksi ke prompt LLM."""
        history = self.get_history(chat_id)
        if not history:
            return ""

        recent = history[-max_turns:]
        lines = []
        for msg in recent:
            role = "Mahasiswa" if msg.get("role") == "user" else "AI Asisten"
            text = msg.get("text", "").strip()
            lines.append(f"{role}: {text}")

        return "\n".join(lines)

    def detect_active_course_from_history(self, chat_id: int, detect_fn: Callable[[str], Optional[str]]) -> Optional[str]:
        """Cari mata kuliah yang sedang dibicarakan di pesan user terakhir."""
        history = self.get_history(chat_id)
        for msg in reversed(history):
            if msg.get("role") == "user":
                text = msg.get("text", "")
                code = detect_fn(text)
                if code:
                    return code
        return None

    @staticmethod
    def get_recent_assignments_summary(max_items: int = 3) -> str:
        """Konteks tugas yang baru saja dikerjakan bot agar bot tidak bingung saat ditanya
        'tugas yang lu kerjain tadi darimana' atau 'tugas tadi salah'."""
        if not ASSIGNMENT_OUTPUTS_FILE.exists():
            return ""
        try:
            data = json.loads(ASSIGNMENT_OUTPUTS_FILE.read_text(encoding="utf-8"))
            if not data:
                return ""

            items = []
            for url, val in data.items():
                items.append((val.get("generated_at", ""), url, val))

            items.sort(key=lambda x: x[0], reverse=True)
            recent = items[:max_items]

            blocks = ["=== RIWAYAT TUGAS YANG BARU SAJA DIKERJAKAN BOT ==="]
            for gen_time, url, val in recent:
                title = val.get("title", "-")
                cname = val.get("course_name", "-")
                files = [Path(f).name for f in val.get("files", [])]
                files_str = ", ".join(files) if files else "-"
                summary = val.get("summary", "")[:250]
                blocks.append(
                    f"• Judul Tugas: {title}\n"
                    f"  Mata Kuliah: {cname}\n"
                    f"  Waktu Pengerjaan: {gen_time}\n"
                    f"  File Dihasilkan: {files_str}\n"
                    f"  Ringkasan: {summary}..."
                )
            blocks.append("===================================================\n")
            return "\n".join(blocks)
        except Exception as e:
            logger.warning(f"Gagal membaca assignment outputs summary: {e}")
            return ""
