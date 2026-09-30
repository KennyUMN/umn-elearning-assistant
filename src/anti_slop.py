"""Anti-Slop Academic Writing Engine.

Bentuknya sengaja BUKAN daftar frasa. Sangkar frasa hanya menangkap kalimat
persis; model jarang menghasilkan string yang sama persis, dan menghapus
substring membuat kalimat rusak. Yang bekerja adalah pola yang bisa dicek
("tik"), lalu diperiksa model sebelum isi dikembalikan.

Diadaptasi dari pola "Signs of AI writing" (Wikipedia / WikiProject AI
Cleanup), disaring ke idiom bahasa Indonesia yang muncul di dokumen tugas.
"""

import re
from typing import Any, Dict, List

# ── Tik: pola yang sering muncul di teks AI tapi jarang di tulisan manusia ──
# Dipakai (1) disuntikkan ke prompt supaya model tahu apa yang dihindari,
# (2) dipakai filter sebagai jaring pengaman kalau model tetap lolos.
AI_TICS: List[str] = [
    # 1. Pembuka basa-basi (throat-clearing)
    r"\b(?:dalam era|dalam dunia|di era|seiring (?:dengan )?pesatnya|seiring perkembangan|"
    r"seperti yang kita tahu|penting untuk dipahami|perlu dipahami bahwa|"
    r"tidak dapat dipungkiri|pada masa kini|di masa sekarang)\b",
    # 2. Peningkatan arti (significance inflation)
    r"\b(?:pivotal|game[\s-]changer|menjadi sorotan|berperan penting|"
    r"memegang peranan|menjadi tolok ukur|menjadi salah satu)\b",
    # 3. Kata hampa / kosmetik
    r"\b(?:holistik|komprehensif|sinergi|terbina|pada tataran)\b",
    # 4. Partisial -ing sebagai kedalaman palsu
    r"\b(?:menunjukkan|menekankan|mencerminkan|merepresentasikan|mempertegas|"
    r"menunjukkan|menekankan|mencerminkan|merepresentasikan|mempertegas|menegaskan|mengusulkan)\s+(?:bahwa\s+)?(?:hal|penerapan|proses|hasil|sebuah|"
    r"pentingnya|keterkaitan|hasilnya|ketiga\s+\w+|hal-hal|masalah-masalah|ketika|semua hal)\b",
    # 5. "tidak hanya X, tetapi juga Y" (negative parallelism)
    r"\btidak hanya\b[^.]{0,60}\b(?:tetapi juga|melainkan)\b",
    # 6. Kopula dihindari (copula avoidance)
    r"\b(?:berfungsi sebagai|berperan sebagai)\b",
    # 7. Kesimpulan generik
    r"\b(?:kesimpulannya|pada akhirnya|dengan demikian|secara keseluruhan|"
    r"secara singkat|implikasinya adalah|maraknya)\b",
    # 8. Penanda bahasa Inggris yang tidak perlu
    r"\b(?:essentially|overall|in conclusion|it is worth noting|moreover|"
    r"furthermore|underscores|showcases|delve into)\b",
]

# Ekor kesimpulan klise: kalimat penutup yang mengulang isi bab sebelumnya.
_CLICHED_TAIL = re.compile(
    r"(?:^|(?<=\. ))(?:Dengan demikian|Maka dari uraian di atas|"
    r"Berdasarkan uraian tersebut)[^.]{0,200}\.",
    re.IGNORECASE,
)

# Kalimat yang benar-benar tidak bernapas — dibuang, bukan dipoles.
_EMPTY_FILLER = re.compile(
    r"^(?:secara keseluruhan|dengan kata lain|intinya)[.:]?$",
    re.IGNORECASE,
)

# Instruksi ketat yang diinjeksikan ke prompt pengerjaan tugas.
ANTI_SLOP_SYSTEM_INSTRUCTIONS = """
=== ATURAN WAJIB: MENULIS SEPERTI MAHASISWA, BUKAN SEPERTI MESIN ===

Dokumen ini dinilai dosen sebagai kerja mahasiswa. Yang membedakan keduanya
bukan panjang, tapi spesifik: mahasiswa menyebut nama algoritma, angka dari
materi kuliah, dan trade-off yang mereka sendiri. Teks generik tidak ada nilainya.

1. LANGSUNG MASUK KE ISI. Kalimat pertama sebuah paragraf adalah inti poinnya.
   Dilarang membuka dengan throat-clearing ("dalam era digital saat ini...",
   "seiring pesatnya perkembangan...", "seperti yang kita ketahui...").
   Kalau kalimat pertamamu bisa dipindah ke esai lain tanpa diubah, hapus saja.

2. SEBUTKAN SPESIFIKNYA. Ganti generalisasi dengan yang bisa dipertanggungjawab:
   - "performa model meningkat" -> "akurasi mAlexNet naik dari X ke Y setelah augmentasi"
   - "metode ini efisien" -> "kompleksitas waktu O(n^2), memori O(n)"
   - "banyak penelitian menunjukkan" -> "Churchill (2020) mengukur X pada dataset Y"
   Kalau angkanya tidak ada di materi, tuliskan terus terang: "materi tidak
   menyebut angka spesifik; berdasarkan argumen saya sendiri, ...".

3. HINDARI KALIMAT YANG CUMA MENGULANG. Kalimat seperti "solusi yang baik hanya
   dapat lahir dari pemahaman yang benar terhadap masalah" tidak mengandung
   informasi baru apa pun. Ganti dengan: konsekuensi konkret, batas metode,
   atau trade-off yang membuat pembaca bisa membayangkan hasilnya.

4. VARIASIKAN RITME. Jangan satu paragraf berisi satu kalimat panjang. Campur
   kalimat pendek tegas dengan penjelasan yang lebih panjang. Hindari baris
   dramatis seperti "X. Dan Y. Dan Z." atau kalimat pamungkas yang bertepuk tangan.
   DILARANG juga pola "tidak hanya X, tetapi juga Y" — itu formula khas AI.

5. KESIMPULAN HARUS PUNYA ISI. Tulis minimal satu temuan yang TIDAK ada di bab
   sebelumnya: batas yang belum terpecahkan, konsekuensi lanjutan, atau
   pertanyaan yang masih terbuka. DILARANG menutup dengan kalimat normatif
   kosong ("akhirnya kita berharap...", "mari kita sporting").

6. JANGAN PAKAI: em-dash berlebihan, emoji, pen tebal, header Title Case,
   kata "krusial/holistik/fundamental/signifikan" sebagai penghias.

=== PEMERIKSAAN DIRI WAJIB SEBELUM MENGEMBALIKAN JSON ===
Baca ulang output-mu sendiri sekali dan perbaiki:
- Hapus setiap kalimat yang isinya nol.
- Ganti setiap generalisasi dengan angka, nama, atau kutipan dari materi.
- Cek kalimat pertama tiap BAB: kalau generik, tulis ulang.
Jangan kembalikan JSON sebelum pemeriksaan ini selesai.
"""


def find_slop(text: str) -> List[str]:
    """Kembalikan tik yang terdeteksi — untuk tes/logging, bukan untuk menghapus."""
    return [pat for pat in AI_TICS if re.search(pat, text or "", re.IGNORECASE)]


def clean_text_slop(text: str) -> str:
    """Buang kalimat pengisi dan kesimpulan klise.

    Sisanya dibiarkan utuh: menyunting kalimat secara mekanis lebih sering
    merusak makna daripadabaiki. Pembersihan utama terjadi lewat prompt.
    """
    if not text:
        return ""
    out = text.strip()
    for _ in range(3):  # bisa bertumpuk
        new = _CLICHED_TAIL.sub("", out).strip()
        if new == out:
            break
        out = new
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def sanitize_sections_slop(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bersihkan tiap section: buang kalimat kosong, jaga teks lain apa adanya."""
    cleaned_sections = []
    for sec in sections:
        new_sec = dict(sec)
        for field in ("paragraphs", "bullets"):
            if isinstance(new_sec.get(field), list):
                items = []
                for p in new_sec[field]:
                    t = clean_text_slop(str(p))
                    if t and not _EMPTY_FILLER.match(t):
                        items.append(t)
                new_sec[field] = items
        cleaned_sections.append(new_sec)
    return cleaned_sections
