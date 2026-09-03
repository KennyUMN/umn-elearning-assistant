"""Anti-Slop Academic Writing Engine.

Menghilangkan pola penulisan klise AI (AI Slop) dari dokumen tugas, esai, dan laporan kuliah:
- Menghapus frasa pembuka basa-basi (throat-clearing openers).
- Membasmi buzzwords kosong tanpa substansi teknis.
- Memecah struktur formulaik simetris (1 intro + 3 bullet seragam + kesimpulan klise).
- Menegakkan gaya bahasa aktif, lugas, spesifik, dan menunjukkan pemikiran kritis mahasiswa.
"""

import re
from typing import List, Dict, Any

# Instruksi ketat yang diinjeksikan langsung ke prompt LLM pengerjaan tugas
ANTI_SLOP_SYSTEM_INSTRUCTIONS = """
=== ATURAN WAJIB: ANTI-AI-SLOP ACADEMIC WRITING ===
Tugas ini HARUS ditulis seperti dikerjakan oleh mahasiswa teknik/informatika manusia yang cerdas, kritis, dan berpikiran tajam — BUKAN robot AI korporat dengan bahasa template klise.

1. DILARANG KERAS MENGGUNAKAN PEMBUKA BASA-BASI (THROAT-CLEARING OPENERS):
   - HARAM menulis: "Dalam era digital saat ini...", "Seiring pesatnya perkembangan teknologi...", "Seperti yang kita ketahui...", "Penting untuk dipahami bahwa...", "Tentunya hal ini bukan tanpa alasan...", "Di era globalisasi yang serba modern ini...".
   - HARAM (English): "In today's fast-paced world...", "It is worth noting that...", "At its core...", "Delve into...", "A testament to...", "Crucial step in...".
   - SOLUSI: Langsung mulai dari pokok argumen, fakta teknis, atau masalah spesifik pada kalimat pertama!

2. BASMI BUZZWORD KOSONG & KLAIM KABUR (SPECIFICITY OVER ABSTRACTION):
   - HARAM menggunakan kata hampa: "holistik", "sinergi", "optimalisasi menyeluruh", "game-changer", "fondasi yang sangat krusial", "membawa dampak signifikan" tanpa didukung bukti konkret.
   - WAJIB gunakan terminologi teknis presisi: sebutkan nama algoritma, library, parameter, arsitektur, trade-off komputasi, rumus, atau mekanisme sistem yang nyata.

3. HINDARI POLA STRUKTUR SIMETRIS FORMULAIC (BREAK ROBOTIC TEMPLATES):
   - JANGAN membuat format kaku: 1 paragraf pengantar normatif -> 3 bullet point ber-bold -> 1 paragraf kesimpulan template.
   - Variasikan ritme tulisan: campur kalimat pendek yang tegas dengan penjelasan analitis yang lebih panjang.
   - Buang kesimpulan yang hanya mengulang kalimat sebelumnya dengan awalan "Kesimpulannya, X memegang peranan penting...". Ganti dengan evaluasi kritis, limitasi, atau implikasi praktis.

4. TUNJUKKAN CRITICAL THINKING & REAL-WORLD TRADE-OFFS:
   - Mahasiswa sejati tahu bahwa setiap solusi teknik punya kelemahan. Sebutkan trade-off (misal: "Kecepatan inferensi meningkat, namun memori footprint lebih boros 20%").
   - Arahkan pembahasan pada konteks implementasi nyata, batas toleransi sistem, atau penanganan edge cases.

5. ACTIVE VOICE & NATURAL STUDENT TONE:
   - Gunakan kalimat aktif ("Pengembang memilih arsitektur MVVM karena...", bukan "Pengimplementasian MVVM dirasa sangat dibutuhkan...").
   - Bahasa akademis harus lugas, padat informasi (dense), dan tidak bertele-tele.
"""

# Daftar frasa AI Slop yang otomatis disaring/dibersihkan jika lolos
BANNED_PHRASES = [
    # Indonesian cliches
    r"\bDalam era digital saat ini\b,?",
    r"\bDi era digital yang serba cepat ini\b,?",
    r"\bSeiring dengan pesatnya perkembangan teknologi\b,?",
    r"\bSeperti yang kita ketahui bersama\b,?",
    r"\bTentunya hal ini bukan tanpa alasan\b,?",
    r"\bPerlu dipahami bahwa\b,?",
    r"\bHal ini memegang peranan yang sangat krusial\b,?",
    r"\bSecara holistik dan komprehensif\b,?",
    r"\bKesimpulannya, .* memegang peranan penting\b,?",
    
    # English cliches
    r"\bIn today's fast-paced world\b,?",
    r"\bAt its core\b,?",
    r"\bIt is worth noting that\b,?",
    r"\bDelve into\b,?",
    r"\bA testament to\b,?",
    r"\bGame-changer\b,?",
    r"\bWhen it comes to\b,?"
]

def clean_text_slop(text: str) -> str:
    """Membersihkan frasa klise AI yang terselip secara mekanis."""
    cleaned = text
    for pattern in BANNED_PHRASES:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    
    # Rapikan tanda baca & spasi beruntun
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([.,;:!?])\s*\1+", r"\1", cleaned)
    cleaned = re.sub(r"^\s*[,;:!?.]+\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned

def sanitize_sections_slop(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Membersihkan slop dari struktur sections yang dihasilkan LLM."""
    cleaned_sections = []
    for sec in sections:
        new_sec = dict(sec)
        if "paragraphs" in new_sec and isinstance(new_sec["paragraphs"], list):
            new_sec["paragraphs"] = [
                clean_text_slop(str(p)) for p in new_sec["paragraphs"] if clean_text_slop(str(p))
            ]
        if "bullets" in new_sec and isinstance(new_sec["bullets"], list):
            new_sec["bullets"] = [
                clean_text_slop(str(b)) for b in new_sec["bullets"] if clean_text_slop(str(b))
            ]
        cleaned_sections.append(new_sec)
    return cleaned_sections
