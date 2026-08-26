# 🎓 UMN E-Learning Assistant (Telegram Bot + Cron Auto-Sync + AI RAG)

Asisten pintar berbasis AI yang terhubung langsung ke **E-Learning Universitas Multimedia Nusantara (UMN)**, otomatis mengunduh materi kuliah (PDF, PPTX, Word), mengekstrak teks & slide, memantau deadline tugas, serta mengirimkan **Daily Morning Class Prep Briefing** dan **Assignment Reminder** langsung ke Telegram kamu.

---

## ✨ Fitur Utama

1. **Auto-Downloader & Parser (`sync.py`)**:
   - Login otomatis ke E-Learning UMN (`https://elearning.umn.ac.id/`).
   - Mengunduh materi, slide, dan lampiran tugas semester aktif ke `data/materials/`.
   - Mengekstrak teks dari PDF, PPTX, dan DOCX ke `data/extracted_text/`.
2. **Daily Morning Class Prep Briefing (Cron Job - 07:00 WIB)**:
   - Setiap pagi sebelum kelas dimulai, AI merangkum materi apa yang perlu dipersiapkan, slide mana yang harus dibaca, dan apa inti bahasan hari ini berdasarkan jadwal kuliah & silabus/RPKPS.
3. **Daily Assignment & Deadline Reminder (Cron Job - 18:00 WIB)**:
   - Memeriksa tugas di e-learning, mendeteksi mana yang belum disubmit, menghitung sisa waktu deadline, dan mengirim reminder prioritas.
4. **Interactive AI Tutor (Telegram Bot)**:
   - Tanya langsung di chat Telegram kapan saja: *"Jelaskan konsep TOGAF di materi Enterprise Architecture week 1"*, *"Apa saja kriteria tugas English 3?"*, dll.
5. **Perintah Telegram Lengkap**:
   - `/briefing` - Buat briefing kelas hari ini secara instan.
   - `/tugas` - Cek daftar tugas pending & deadline.
   - `/sync` - Memicu sinkronisasi materi & tugas terbaru dari e-learning.
   - `/courses` - Melihat daftar mata kuliah yang terdeteksi.
   - `/id` - Melihat Telegram Chat ID kamu.

---

## 🚀 Panduan Setup Cepat (3 Langkah)

### 1. Salin Konfigurasi `.env`
Salin file `.env.example` menjadi `.env`:
```bash
cp .env.example .env
```

Buka dan isi file `.env`:
- `UMN_USERNAME` : NIM atau username SSO UMN kamu.
- `UMN_PASSWORD` : Password akun SSO UMN kamu.
- `GEMINI_API_KEY`: Dapatkan gratis di [Google AI Studio](https://aistudio.google.com/).
- `TELEGRAM_BOT_TOKEN`: Dapatkan dari [@BotFather](https://t.me/BotFather) di Telegram (ketik `/newbot`).
- `TELEGRAM_CHAT_ID`: ID akun Telegram kamu (dapat dilihat via bot [@userinfobot](https://t.me/userinfobot) atau ketik `/id` di bot kamu).

### 2. Atur Jadwal Mata Kuliah Mingguan
Buka file `data/metadata/class_schedule.json` dan sesuaikan jadwal kuliah kamu per hari (Senin - Jumat) agar AI tahu jadwal kelas apa saja yang kamu hadapi setiap harinya.

### 3. Jalankan Aplikasi
Aktifkan virtual environment dan jalankan:

**Opsi A: Tes Sinkronisasi E-Learning Pertama Kali (CLI)**
```bash
source venv/bin/activate
python sync.py
```

**Opsi B: Jalankan Bot Telegram + Cron Scheduler Otomatis**
```bash
source venv/bin/activate
python main.py
```

---

## 📁 Struktur Direktori
```text
umn-elearning-assistant/
├── data/
│   ├── materials/          # File asli yang diunduh (PDF, PPTX, DOCX)
│   ├── extracted_text/     # Teks hasil ekstraksi siap baca AI
│   └── metadata/           # Data mata kuliah, tugas, dan jadwal
├── src/
│   ├── moodle_client.py    # Engine scraper login & fetcher E-Learning UMN
│   ├── document_parser.py  # Parser PDF, PPTX, DOCX
│   ├── ai_service.py       # Integrasi Gemini API & Prompting
│   ├── telegram_bot.py     # Bot Telegram & handler chat
│   ├── scheduler.py        # Cron scheduler harian (07:00 & 18:00 WIB)
│   └── config.py           # Konfigurasi path & env
├── sync.py                 # Standalone sync runner
├── main.py                 # Runner bot + background cron
└── requirements.txt        # Dependensi Python
```
