import json
import time
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import requests
from google import genai
from google.genai import types

from src.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    LLM_STATE_FILE,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    SEMESTER_START_DATE,
    SEMESTER_BREAKS,
    EXTRACTED_TEXT_DIR,
    ASSIGNMENTS_FILE,
    COURSES_FILE,
    SCHEDULE_FILE
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ai_service")

VALID_PROVIDERS = ("gemini", "openrouter")

# Preset model yang bisa dipilih via perintah /model di Telegram
MODEL_PRESETS = {
    "gemini": {
        "default": "gemini-3.7-flash (auto-fallback)",
        "options": [
            "gemini-3.7-flash",
            "gemini-flash-lite-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.6-flash",
            "gemini-2.5-flash",
            "gemini-2.5-pro"
        ]
    },
    "openrouter": {
        "default": OPENROUTER_MODEL,
        "options": [
            OPENROUTER_MODEL,
            "deepseek/deepseek-chat-v3.1:free",
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.3-70b-instruct:free"
        ]
    }
}


def _load_llm_state() -> Dict[str, Any]:
    """Muat provider & model aktif. State file (hasil /model) menang atas default .env."""
    default_provider = LLM_PROVIDER if LLM_PROVIDER in VALID_PROVIDERS else "gemini"

    if LLM_STATE_FILE.exists():
        try:
            state = json.loads(LLM_STATE_FILE.read_text(encoding="utf-8"))
            provider = state.get("provider", "")
            if provider in VALID_PROVIDERS:
                return {
                    "provider": provider,
                    "model": state.get("model") or MODEL_PRESETS[provider]["default"]
                }
        except Exception as e:
            logger.warning(f"Gagal membaca state LLM ({e}), pakai default dari .env.")

    return {"provider": default_provider, "model": MODEL_PRESETS[default_provider]["default"]}


def get_llm_state() -> Dict[str, str]:
    """Return state provider/model LLM aktif saat ini."""
    return _load_llm_state()


def set_llm_state(provider: str, model: Optional[str] = None) -> Dict[str, str]:
    """Simpan provider & model aktif ke state file (bertahan meski service restart)."""
    provider = (provider or "").strip().lower()
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Provider tidak dikenal: {provider}. Pilihan: {', '.join(VALID_PROVIDERS)}")

    model = (model or "").strip() or MODEL_PRESETS[provider]["default"]
    state = {"provider": provider, "model": model}

    try:
        LLM_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        LLM_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Gagal menyimpan state LLM: {e}")

    logger.info(f"LLM aktif diganti ke: {provider} / {model}")
    return state

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
    "EM105": ["techno", "technopreneur", "technopreneurship", "kewirausahaan", "wadhwani", "nen", "pitching", "business"],
    "IF581": ["game dev", "game development", "gamedev", "game"],
    "UM321": ["english 3", "english3", "bahasa inggris"],
    "MSC5233": ["ai for strategic communication", "strategic communication", "ai stratcom"]
}

class AIService:
    def __init__(self, api_key: str = GEMINI_API_KEY):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        # Default model is Gemini 3.7 Flash, with automatic fast fallback chain
        self.models_to_try = [
            "models/gemini-3.7-flash",
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
        """Dispatch generation ke provider aktif (gemini / openrouter) berdasarkan state LLM."""
        state = get_llm_state()
        provider, model = state["provider"], state["model"]
        logger.info(f"Generating via provider={provider} model={model}")

        if provider == "openrouter":
            if not OPENROUTER_API_KEY:
                return (
                    "⚠️ Provider aktif **openrouter** tapi `OPENROUTER_API_KEY` belum diatur di file `.env`.\n\n"
                    "Solusi:\n"
                    "1. Ambil API key gratis di https://openrouter.ai/keys\n"
                    "2. Tambahkan baris `OPENROUTER_API_KEY=keykamu` ke `.env`\n"
                    "3. Restart service, atau ketik `/model gemini` untuk balik ke Gemini dulu."
                )
            return self._generate_openrouter(prompt, model)

        # Provider: gemini (default: gemini-3.7-flash with auto-fallback)
        return self._generate_gemini(prompt, requested_model=model)

    def _generate_gemini(self, prompt: str, requested_model: Optional[str] = None) -> str:
        """Attempt generation with Gemini 3.7 Flash as default and fallback to other models."""
        if not self.is_configured():
            return "⚠️ Gemini API Key belum diatur di file `.env`."

        primary = requested_model or GEMINI_MODEL
        if primary and "auto-fallback" in primary:
            primary = primary.split()[0]

        chain = []
        if primary:
            formatted_primary = primary if primary.startswith("models/") else f"models/{primary}"
            chain.append(formatted_primary)

        for m in self.models_to_try:
            if m not in chain:
                chain.append(m)

        last_error = None
        for model in chain:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                last_error = e
                logger.warning(f"Model {model} failed ({e}), trying next fallback model...")

        return f"❌ Gagal memproses permintaan AI (gemini): {str(last_error)}"

    def _generate_openrouter(self, prompt: str, model: str) -> str:
        """Generate via OpenRouter (API kompatibel OpenAI chat completions)."""
        url = f"{OPENROUTER_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            # Atribusi opsional yang disarankan OpenRouter
            "HTTP-Referer": "https://github.com/KennyUMN/umn-elearning-assistant",
            "X-Title": "UMN E-Learning Assistant"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }

        last_error = None
        for attempt in range(2):  # 1 retry untuk error sementara (free tier kadang rate-limit)
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=180)
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content and content.strip():
                        return content.strip()
                    last_error = f"Response kosong/tidak terbaca: {str(data)[:300]}"
                else:
                    body = res.text[:300]
                    last_error = f"HTTP {res.status_code}: {body}"
                    # 429 = rate limit free tier → coba lagi setelah jeda
                    if res.status_code == 429:
                        time.sleep(3 * (attempt + 1))
                        continue
                    break
            except Exception as e:
                last_error = str(e)
                time.sleep(2)

        return (
            f"❌ Gagal memproses permintaan AI (openrouter / {model}):\n{last_error}\n\n"
            f"_Coba `/model gemini` untuk balik ke provider Gemini._"
        )

    def _get_relevant_context(self, query: str = "", max_chars: int = 35000) -> str:
        """Collect relevant course text with smart course isolation and TF-IDF weighting."""
        context_blocks = []
        total_len = 0

        # Step 0: Always include the enrolled courses summary
        enrolled_summary = ""
        if COURSES_FILE.exists():
            try:
                courses_data = json.loads(COURSES_FILE.read_text(encoding="utf-8"))
                course_titles = [c.get("title") for c in courses_data if c.get("title")]
                if course_titles:
                    enrolled_summary = (
                        "=== DAFTAR SEMUA MATA KULIAH TERDAFTAR SEMESTER INI ===\n"
                        + "\n".join(f"- {t}" for t in course_titles)
                        + "\n=======================================================\n\n"
                    )
                    context_blocks.append(enrolled_summary)
                    total_len += len(enrolled_summary)
            except Exception as e:
                logger.warning(f"Error loading courses in context: {e}")

        target_code = self._detect_target_course(query) if query else None

        course_dirs = [d for d in EXTRACTED_TEXT_DIR.iterdir() if d.is_dir()]
        if not course_dirs:
            return enrolled_summary + "Belum ada dokumen materi yang diekstrak." if enrolled_summary else "Belum ada dokumen materi yang diekstrak."

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

                if any(w in query.lower() for w in ["ngapain", "semester", "silabus", "rpkps", "jadwal", "materi", "semua", "daftar"]):
                    if "rpkps" in stem_lower or "guideline" in stem_lower:
                        score += 200

                scored_files.append((score, file_path, content))
            except Exception:
                continue

        scored_files.sort(key=lambda x: x[0], reverse=True)

        # If no specific target course, ensure balanced representation across all courses
        if not target_code:
            per_course_limit = max_chars // max(1, len(course_dirs))
            course_used = {}
            for score, file_path, content in scored_files:
                course_name = file_path.parent.name
                doc_name = file_path.name
                cur_used = course_used.get(course_name, 0)
                if cur_used >= per_course_limit:
                    continue

                piece = content[:per_course_limit - cur_used]
                context_blocks.append(f"=== MATA KULIAH: {course_name} ===\n=== DOKUMEN: {doc_name} ===\n{piece}")
                course_used[course_name] = cur_used + len(piece)
                total_len += len(piece)
                if total_len >= max_chars:
                    break
        else:
            for score, file_path, content in scored_files:
                if score < 0:
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

    def _get_semester_week(self) -> Optional[int]:
        """Hitung minggu semester ke-N dari SEMESTER_START_DATE (minggu-1 = pekan kuliah pertama).
        Minggu yang jatuh pada rentang SEMESTER_BREAKS (mis. UTS) tidak dihitung,
        sehingga nomor minggu tetap sinkron dengan roadmap RPKPS setelah libur.
        """
        if not SEMESTER_START_DATE:
            return None
        try:
            start = datetime.strptime(SEMESTER_START_DATE, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(f"Format SEMESTER_START_DATE tidak valid: '{SEMESTER_START_DATE}' (harus YYYY-MM-DD)")
            return None

        today = datetime.now().date()
        if today < start:
            return None  # semester belum mulai

        # Parse rentang libur: "2026-10-12:2026-10-24,2027-01-05:2027-01-10"
        breaks = []
        for part in SEMESTER_BREAKS.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            try:
                b_start, b_end = (datetime.strptime(x.strip(), "%Y-%m-%d").date() for x in part.split(":", 1))
                breaks.append((b_start, b_end))
            except ValueError:
                logger.warning(f"Format SEMESTER_BREAKS tidak valid: '{part}' (harus YYYY-MM-DD:YYYY-MM-DD)")

        week = 0
        d = start
        while d <= today:
            week_end = d + timedelta(days=6)
            # Minggu dianggap libur kalau mayoritas (>=4 hari) harinya jatuh dalam rentang break
            is_break_week = any(
                (min(week_end, b1) - max(d, b0)).days + 1 >= 4
                for b0, b1 in breaks if max(d, b0) <= min(week_end, b1)
            )
            if not is_break_week:
                week += 1
            d = week_end + timedelta(days=1)
        return min(week, 19)  # ~14 minggu perkuliahan + UAS

    @staticmethod
    def _module_week_number(file_stem: str) -> Optional[int]:
        """Deteksi nomor minggu dari nama file modul.
        Contoh: 'Materi-EM105-M01-Orientasi' -> 1, 'Week 3-Perceptron' -> 3, 'Pertemuan 12' -> 12.
        Token dipisah [-_] supaya 'EM105' tidak salah terbaca sebagai minggu.
        """
        for token in re.split(r"[-_]+", file_stem.lower()):
            m = re.fullmatch(r"m(\d{1,2})", token)
            if m:
                return int(m.group(1))
            m = re.fullmatch(r"(?:week|pertemuan|sesi|session|minggu)\s*(\d{1,2})", token)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _normalize_code(code: str) -> str:
        """'EM 105 - B' -> 'em105b', 'MSC5233-A-EN' -> 'msc5233aen'."""
        return re.sub(r"[^a-z0-9]", "", (code or "").lower())

    def _find_course_folder(self, code: str, course_name: str) -> Optional[Path]:
        """Cari folder mata kuliah di extracted_text.
        Strategi: (1) kode lengkap, (2) prefix kode sebelum tanda '-' (IF570-AL -> IF570,
        IF571-F -> IF571), (3) kata-kata nama mata kuliah.
        """
        norm = self._normalize_code(code)
        if norm:
            for d in EXTRACTED_TEXT_DIR.iterdir():
                if d.is_dir() and norm in self._normalize_code(d.name):
                    return d
            # Coba root kode: "IF570-AL" -> "IF570", "IF571-F" -> "IF571"
            root = self._normalize_code(code.split("-")[0])
            if root and root != norm:
                for d in EXTRACTED_TEXT_DIR.iterdir():
                    if d.is_dir() and root in self._normalize_code(d.name):
                        return d

        tokens = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", course_name)]
        if tokens:
            for d in EXTRACTED_TEXT_DIR.iterdir():
                name_lower = d.name.lower()
                if d.is_dir() and all(t in name_lower for t in tokens[:3]):
                    return d
        return None

    def _get_briefing_context(self, today_classes: List[Dict[str, Any]], week: Optional[int], max_chars: int = 28000) -> str:
        """Kumpulkan konteks briefing secara DETERMINISTIK per mata kuliah hari ini.
        Prioritas tiap matkul: (1) RPKPS/guideline = roadmap mingguan, (2) modul minggu berjalan
        (M0N/WeekN), (3) modul terakhir. Bukan TF-IDF campuran antar matkul.
        """
        blocks = []
        total_len = 0
        budget = max(5000, max_chars // max(1, len(today_classes)))

        for cls in today_classes:
            code = (cls.get("code") or "").strip()
            course_name = (cls.get("course") or "").strip()
            folder = self._find_course_folder(code, course_name)

            if folder is None:
                blocks.append(
                    f"=== {course_name} ({code}) ===\n[Belum ada dokumen materi yang diekstrak untuk mata kuliah ini. JANGAN mengarang topiknya.]"
                )
                continue

            files = list(folder.glob("*.txt"))
            rpkps_files = [p for p in files if any(k in p.stem.lower() for k in ("rpkps", "guideline", "syllabus"))]
            module_files = [p for p in files if p not in rpkps_files]

            def module_rank(p: Path) -> float:
                mod_week = self._module_week_number(p.stem)
                if week is not None and mod_week == week:
                    return 1000 + mod_week  # modul minggu ini
                if mod_week is not None:
                    return mod_week  # makin baru makin tinggi
                return -1  # tanpa nomor minggu: paling bawah

            course_block = f"=== {course_name} ({code}) | Minggu semester: {week if week else 'tidak diketahui'} ===\n"
            course_len = 0

            # 1) RPKPS (maks ~60% budget matkul ini)
            rpkps_budget = int(budget * 0.6)
            for p in rpkps_files[:1]:  # satu RPKPS cukup
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                piece = f"\n--- DOKUMEN (ROADMAP MINGGUAN): {p.name} ---\n{content}\n"
                if len(piece) > rpkps_budget:
                    piece = piece[:rpkps_budget] + "\n[TRUNCATED...]\n"
                course_block += piece
                course_len += len(piece)

            # 2) Modul (minggu ini dulu, lalu terbaru)
            for p in sorted(module_files, key=module_rank, reverse=True):
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                piece = f"\n--- DOKUMEN (MODUL): {p.name} ---\n{content}\n"
                if course_len + len(piece) > budget:
                    remaining = budget - course_len
                    if remaining > 800:
                        course_block += piece[:remaining] + "\n[TRUNCATED...]\n"
                    break
                course_block += piece
                course_len += len(piece)

            total_len += course_len
            blocks.append(course_block)

        return "\n\n".join(blocks) if blocks else "Belum ada dokumen materi yang diekstrak."

    def generate_morning_briefing(self, today_day: Optional[str] = None) -> str:
        """Generate a personalized daily morning briefing for class preparation (week-aware)."""
        if not today_day:
            days = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
            today_day = days[datetime.now().weekday()]

        week = self._get_semester_week()

        # --- Muat jadwal hari ini ---
        today_classes = []
        if SCHEDULE_FILE.exists():
            try:
                schedules = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
                today_classes = schedules.get(today_day, [])
            except Exception as e:
                logger.warning(f"Error loading schedule: {e}")
        else:
            logger.warning("class_schedule.json belum ada — isi sesuai jadwal kuliahmu agar briefing akurat.")

        # --- Muat tugas pending ---
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

        # --- Hari tanpa kelas: jangan halusinasi, langsung balas singkat ---
        if not today_classes:
            msg = f"☀️ **Morning Briefing ({today_day})**\n\n🎉 **Hari ini tidak ada jadwal kuliah!** Nikmati hari bebasnya.\n\n"
            msg += f"📋 **Tugas Pending:**\n{assignments_summary}\n" if assignments_summary else "📋 Tidak ada tugas pending yang terdeteksi. 🚀\n"
            msg += "\n💡 _Gunakan hari ini buat ngejar materi yang tertinggal, kerjain tugas, atau istirahat yang cukup!_"
            return msg

        # --- Konteks per matkul (deterministik: RPKPS + modul minggu ini) ---
        context = self._get_briefing_context(today_classes, week)
        schedule_info = json.dumps(today_classes, indent=2, ensure_ascii=False)

        if week:
            week_line = f"Minggu ke-{week}"
            topic_rule = (
                f"   a. Roadmap mingguan di RPKPS pada **minggu ke-{week}** — kutip topik / Course Sub-Learning Outcomes minggu itu, ATAU\n"
                f"   b. Modul minggu ke-{week} jika ada di E-Learning (penamaan biasanya M{week:02d} / Week{week}).\n"
                f"   Jika keduanya tidak ada: katakan terus terang \"Materi minggu ini belum tersedia di E-Learning\", lalu sarankan review modul terakhir yang tersedia — sebutkan nomor minggu asli modul itu (contoh: M01 = minggu 1). JANGAN mengarang topik dan JANGAN menyebut modul minggu lain sebagai modul minggu ini."
            )
        else:
            week_line = "tidak diketahui (isi SEMESTER_START_DATE di .env agar akurat)"
            topic_rule = (
                "   a. Roadmap mingguan di RPKPS — jika posisi minggu semester bisa disimpulkan dari materi yang sudah di-upload, gunakan itu dan sebutkan asumsimu, ATAU\n"
                "   b. Modul terakhir yang tersedia di E-Learning (sebutkan nama modulnya).\n"
                "   Jangan mengarang topik yang tidak ada di dokumen."
            )

        prompt = f"""
Kamu adalah AI Asisten Belajar Pintar untuk Mahasiswa Universitas Multimedia Nusantara (UMN).
Tugasmu membuat **Daily Morning Class Prep Briefing** yang AKURAT, berbasis FAKTA dari data di bawah.

=== DATA FAKTA (WAJIB DIPATUHI — JANGAN MENGARANG) ===
1. Hari ini: {today_day} | {week_line}
2. Jadwal kuliah HARI INI (satu-satunya kelas yang valid):
{schedule_info}
3. Tugas pending:
{assignments_summary if assignments_summary else '- Tidak ada tugas pending terdeteksi.'}
4. Materi & RPKPS per mata kuliah (satu-satunya sumber topik):
{context}

=== ATURAN KERAS ===
1. HANYA bahas mata kuliah yang ada di "Jadwal kuliah HARI INI". DILARANG membahas mata kuliah lain.
2. Topik pembahasan tiap mata kuliah WAJIB berasal dari:
{topic_rule}
3. Sebutkan sumber dokumennya (nama file RPKPS/modul) untuk tiap topik.
4. Jangan mencampur materi antar mata kuliah.

=== FORMAT RESPONSE TELEGRAM ===
1. ☀️ **Morning Briefing ({today_day})** — sebutkan minggu semester jika diketahui
2. 📚 **Per Mata Kuliah Hari Ini** (untuk setiap kelas: jam & ruangan, topik hari ini menurut RPKPS/modul + sumber dokumennya)
3. 💡 **Persiapan Sebelum Kelas** (bacaan/slide/software yang perlu disiapkan per kelas)
4. ⚠️ **Reminder Tugas & Deadline** (jika ada)
5. 🚀 **Motivational / Quick Study Tip**

Gunakan gaya bahasa santai mahasiswa-friendly dan formatting Markdown Telegram yang rapi.
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
        """Answer user's question with a proactive, insightful, and supportive AI tutor persona."""
        context = self._get_relevant_context(query=user_question, max_chars=35000)

        # Check for any pending assignments to provide proactive alerts if relevant
        assignments_alert = ""
        if ASSIGNMENTS_FILE.exists():
            try:
                assignments = json.loads(ASSIGNMENTS_FILE.read_text(encoding="utf-8"))
                pending = [a for a in assignments if not a.get("is_submitted")]
                target_code = self._detect_target_course(user_question)
                if target_code:
                    course_pending = [p for p in pending if target_code.lower() in p.get("course_name", "").lower()]
                    if course_pending:
                        assignments_alert = "\n[INFO TUGAS PENDING UNTUK MATA KULIAH INI]\n" + "\n".join(
                            f"- {p.get('title')} (Deadline: {p.get('due_date')} | Sisa waktu: {p.get('time_remaining')})"
                            for p in course_pending
                        )
            except Exception:
                pass

        prompt = f"""
Kamu adalah AI Asisten & Study Partner Pintar Mahasiswa Universitas Multimedia Nusantara (UMN).
Kamu memiliki kepribadian yang **proaktif, suportif, berinisiatif tinggi, dan solutif** (seperti kakak tingkat atau mentor pintar yang selalu satu langkah lebih maju).

=== KONTEKS MATERI KULIAH DARI E-LEARNING ===
{context}
{assignments_alert}

=== PERTANYAAN MAHASISWA ===
{user_question}

=== PANDUAN MENJAWAB PROAKTIF & ANTI-AI-SLOP ===
1. **Akurat & Berdasarkan Fakta**:
   - Sebutkan nama mata kuliah dan kode mata kuliah secara jelas di awal jawaban jika pertanyaan spesifik ke suatu matkul.
   - Jawab berdasarkan dokumen materi/RPKPS yang tersedia. Jika informasi detail tertentu belum ada di slide, katakan dengan jujur dan berikan insight umum yang relevan.

2. **Bebas dari AI Slop (Anti-Throat Clearing & Anti-Cliché)**:
   - DILARANG membuka dengan basa-basi klise: "Tentu!", "Tentu saja!", "Dalam era digital saat ini...", "Seiring pesatnya perkembangan...", "Seperti yang kita ketahui...".
   - Langsung ke inti topik pada kalimat pertama.
   - Hindari buzzword kosong ("holistik", "game-changer", "krusial"). Gunakan terminologi teknis konkret.

3. **Proactive Value-Add (Inisiatif & Persiapan)**:
   - Berikan **Tips Persiapan / Actionable Advice**: Apa yang sebaiknya dipersiapkan mahasiswa (contoh: tools/software yang perlu di-install, konsep dasar yang perlu dipahami dulu, slide/referensi yang perlu dibaca).
   - Hubungkan topik ini dengan relevansi praktiknya (kenapa materi ini penting di dunia industri / skripsi).

4. **Tawaran Bantuan Lanjutan (Actionable Next Steps)**:
   - Di akhir jawaban, **SELALU** tawarkan 2-3 opsi kelanjutan yang spesifik dan menarik agar mahasiswa bisa langsung memilih, contoh:
     - 📌 *1. Rangkuman intisari / cheat sheet poin-poin krusial materi ini*
     - 📌 *2. Latihan soal / kuis kilat 3 pertanyaan untuk uji pemahaman*
     - 📌 *3. Penjelasan roadmap / materi pertemuan berikutnya*
     - *(atau tawarkan bantuan kerjakan tugas jika ada tugas terkait)*

Format jawaban menggunakan Markdown Telegram yang rapi, terstruktur (bold, bullet points, emoji yang pas), dan komunikatif.
"""
        return self._generate_with_fallback(prompt)
