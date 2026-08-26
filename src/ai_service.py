import json
import time
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from google import genai
from google.genai import types

from src.config import (
    GEMINI_API_KEY,
    EXTRACTED_TEXT_DIR,
    ASSIGNMENTS_FILE,
    COURSES_FILE,
    SCHEDULE_FILE
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ai_service")

# Stopwords to filter out when matching content
STOPWORDS = {
    "kira", "untuk", "mata", "kuliah", "ini", "bakal", "ngapain", "aja", "sepanjang", 
    "semester", "tentang", "apa", "bagaimana", "gimana", "ada", "yang", "dan", "di", 
    "ke", "dari", "bisa", "tolong", "jelaskan", "buat", "kasih", "tahu", "pada", 
    "adalah", "itu", "saya", "aku", "gua", "gw", "kamu", "lu", "dong", "saja", "ya"
}

# Aliases to map user queries directly to specific course folder
COURSE_ALIASES = {
    "IF590": ["rti", "riset", "research", "metopen", "metlit", "metodologi penelitian", "it research", "winarno", "arya", "skripsi", "proposal", "poster"],
    "IF570": ["mobdev", "mobile", "map", "kotlin", "android", "pemrograman aplikasi bergerak", "aplikasi mobile"],
    "IF542": ["dl", "deep learning", "neural network", "machine learning", "ml vs dl"],
    "IF571": ["cyber", "cybersecurity", "security", "keamanan", "keamanan siber", "cia triad"],
    "EM105": ["techno", "technopreneur", "technopreneurship", "kewirausahaan", "wadhwani", "nen", "pitching", "business"]
}

class AIService:
    def __init__(self, api_key: str = GEMINI_API_KEY):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        # Ultra-fast low-latency models (~1.5s response)
        self.models_to_try = [
            "models/gemini-flash-lite-latest",
            "models/gemini-3.1-flash-lite",
            "models/gemini-3.6-flash"
        ]

    def is_configured(self) -> bool:
        return bool(self.client and self.api_key)

    def _detect_target_course(self, query: str) -> Optional[str]:
        """Detect if the user query refers to a specific course code or alias."""
        q_lower = query.lower()
        for code, aliases in COURSE_ALIASES.items():
            if code.lower() in q_lower:
                return code
            for alias in aliases:
                if re.search(rf"\b{re.escape(alias)}\b", q_lower):
                    return code
        return None

    def _generate_with_fallback(self, prompt: str) -> str:
        """Attempt generation with ultra-fast models and fallback."""
        if not self.is_configured():
            return "⚠️ Gemini API Key belum diatur di file `.env`."

        last_error = None
        for model in self.models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                last_error = e
                logger.warning(f"Model {model} failed ({e}), trying next model...")

        return f"❌ Gagal memproses permintaan AI: {str(last_error)}"

    def _get_relevant_context(self, query: str = "", max_chars: int = 35000) -> str:
        """Collect relevant course text with smart course isolation and TF-IDF weighting."""
        context_blocks = []
        total_len = 0

        target_code = self._detect_target_course(query) if query else None

        course_dirs = [d for d in EXTRACTED_TEXT_DIR.iterdir() if d.is_dir()]
        if not course_dirs:
            return "Belum ada dokumen materi yang diekstrak."

        candidate_files = []
        for cdir in course_dirs:
            is_target_dir = target_code and target_code.lower() in cdir.name.lower()
            for f in cdir.glob("*.txt"):
                candidate_files.append((f, is_target_dir))

        raw_tokens = [q.lower() for q in re.findall(r"\w+", query)] if query else []
        significant_tokens = [t for t in raw_tokens if t not in STOPWORDS and len(t) > 1]

        scored_files = []
        for file_path, is_target_dir in candidate_files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                content_lower = content.lower()
                stem_lower = file_path.stem.lower()

                score = 0
                if target_code:
                    if is_target_dir:
                        score += 1000
                    else:
                        score -= 500

                if significant_tokens:
                    for token in significant_tokens:
                        count = content_lower.count(token)
                        score += count
                        if token in stem_lower:
                            score += 50
                else:
                    if any(kw in stem_lower for kw in ["rpkps", "guideline", "syllabus", "intro", "materi", "01"]):
                        score += 50
                    score += 1

                if any(w in query.lower() for w in ["ngapain", "semester", "silabus", "rpkps", "jadwal", "materi"]):
                    if "rpkps" in stem_lower or "guideline" in stem_lower:
                        score += 200

                scored_files.append((score, file_path, content))
            except Exception:
                continue

        scored_files.sort(key=lambda x: x[0], reverse=True)

        for score, file_path, content in scored_files:
            if target_code and score < 0:
                continue

            course_name = file_path.parent.name
            doc_name = file_path.name

            if total_len + len(content) > max_chars:
                remaining = max_chars - total_len
                if remaining > 1000:
                    snippet = content[:remaining]
                    context_blocks.append(f"=== MATA KULIAH: {course_name} ===\n=== DOKUMEN: {doc_name} ===\n{snippet}\n[TRUNCATED...]")
                break
            else:
                context_blocks.append(f"=== MATA KULIAH: {course_name} ===\n=== DOKUMEN: {doc_name} ===\n{content}")
                total_len += len(content)

        return "\n\n".join(context_blocks)

    def generate_morning_briefing(self, today_day: Optional[str] = None) -> str:
        """Generate a personalized daily morning briefing for class preparation."""
        if not today_day:
            days = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
            today_day = days[datetime.now().weekday()]

        schedule_info = ""
        if SCHEDULE_FILE.exists():
            try:
                schedules = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
                today_classes = schedules.get(today_day, [])
                if today_classes:
                    schedule_info = f"Jadwal Kuliah Hari {today_day}:\n" + json.dumps(today_classes, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Error loading schedule: {e}")

        assignments_summary = ""
        if ASSIGNMENTS_FILE.exists():
            try:
                assignments = json.loads(ASSIGNMENTS_FILE.read_text(encoding="utf-8"))
                pending = [a for a in assignments if not a.get("is_submitted")]
                if pending:
                    assignments_summary = "Daftar Tugas Pending / Belum Selesai:\n"
                    for p in pending[:5]:
                        assignments_summary += f"- [{p.get('course_name')}] {p.get('title')} | Deadline: {p.get('due_date')} ({p.get('time_remaining')})\n"
            except Exception as e:
                logger.warning(f"Error loading assignments: {e}")

        context = self._get_relevant_context(query=schedule_info or "RPKPS Guidelines", max_chars=35000)

        prompt = f"""
Kamu adalah AI Asisten Belajar Pintar untuk Mahasiswa Universitas Multimedia Nusantara (UMN).
Tugasmu adalah membuatkan **Daily Morning Class Preparation Briefing** yang ringkas, praktis, dan menyemangati mahasiswa sebelum memulai hari kuliah.

Informasi Hari Ini:
- Hari: {today_day}
- {schedule_info if schedule_info else 'Jadwal spesifik belum diatur, berikan overview mata kuliah semester ini.'}
- {assignments_summary if assignments_summary else 'Tidak ada tugas yang terdeteksi menumpuk.'}

Materi & Guidelines Perkuliahan:
{context}

Format Response Telegram (Gunakan gaya bahasa santai, mahasiswa-friendly, jelas, dan berikan poin-poin actionable):
1. ☀️ **Morning Briefing ({today_day})**
2. 📚 **Mata Kuliah & Topik Pembahasan Hari Ini** (Ringkasan singkat topik apa yang bakal dibahas sesuai silabus/slide)
3. 💡 **Persiapan Sebelum Masuk Kelas** (Apa yang harus dibaca, dipahami, atau disiapkan seperti laptop/software/alat)
4. ⚠️ **Reminder Tugas & Deadline** (Jika ada tugas yang mendekati deadline)
5. 🚀 **Motivational / Quick Study Tip**

Gunakan formatting Markdown yang rapi untuk pesan Telegram (bold, bullet points).
"""
        return self._generate_with_fallback(prompt)

    def generate_assignment_reminder(self) -> str:
        """Generate a focused reminder message for pending assignments."""
        if not ASSIGNMENTS_FILE.exists():
            return "ℹ️ Belum ada data tugas. Silakan jalankan `/sync` terlebih dahulu."

        try:
            assignments = json.loads(ASSIGNMENTS_FILE.read_text(encoding="utf-8"))
            pending = [a for a in assignments if not a.get("is_submitted")]

            if not pending:
                return "🎉 **Hore! Semua tugas e-learning sudah beres / tidak ada tugas pending saat ini.** Tetap santai dan pertahankan! 🚀"

            msg_lines = [
                "📋 **REMINDER TUGAS E-LEARNING UMN**",
                f"Terdapat **{len(pending)}** tugas yang masih perlu dikerjakan:\n"
            ]

            for i, p in enumerate(pending, 1):
                msg_lines.append(
                    f"{i}. **{p.get('course_name')}**\n"
                    f"   📌 Tugas: _{p.get('title')}_\n"
                    f"   ⏰ Deadline: *{p.get('due_date')}*\n"
                    f"   ⏳ Sisa Waktu: {p.get('time_remaining')}\n"
                    f"   🔗 [Buka Tugas di E-Learning]({p.get('url')})\n"
                )

            msg_lines.append("💡 _Segera selesaikan sebelum deadline agar tidak menumpuk ya!_")
            return "\n".join(msg_lines)

        except Exception as e:
            return f"❌ Terjadi kesalahan saat membaca daftar tugas: {e}"

    def answer_query(self, user_question: str) -> str:
        """Answer user's question about lecture materials, guidelines, and courses."""
        context = self._get_relevant_context(query=user_question, max_chars=35000)

        prompt = f"""
Kamu adalah Asisten AI Perkuliahan UMN (Universitas Multimedia Nusantara).
Tugasmu adalah menjawab pertanyaan mahasiswa berdasarkan materi kuliah, RPKPS, guideline, dan slide presentasi yang telah disinkronkan dari E-Learning UMN.

=== ATURAN PENTING ===
1. Perhatikan baik-baik nama mata kuliah yang ditanyakan mahasiswa (contoh: RTI = Riset Teknologi Informasi / IF590, bukan Technopreneurship).
2. Jawab HANYA berdasarkan dokumen mata kuliah yang relevan dengan pertanyaan. JANGAN mencampuradukkan materi antar mata kuliah yang berbeda.
3. Sebutkan nama mata kuliah dan kode mata kuliah secara jelas di awal jawaban.

=== KONTEKS MATERI KULIAH DARI E-LEARNING ===
{context}

=== PERTANYAAN MAHASISWA ===
{user_question}

Panduan Jawaban:
- Jawab dengan ramah, akurat, to the point, dan terstruktur.
- Jika ada tabel mingguan / roadmap / poin-poin penting, sajikan dengan rapi (Week 1 s.d. Week 14, UTS, UAS, Komponen Penilaian).
- Jika informasi tidak ditemukan di dokumen, sampaikan terus terang bahwa materi tersebut belum ada di file yang diunduh.
"""
        return self._generate_with_fallback(prompt)
