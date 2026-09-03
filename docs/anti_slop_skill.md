# 🎓 Anti-Slop Academic Writing Skill & Framework

Skill ini dirancang untuk memastikan setiap tugas perkuliahan, makalah, laporan praktikum, dan ringkasan yang dikerjakan oleh AI memiliki standar akademis yang tinggi, berbobot teknis, bernada alami (human-like student voice), dan **bebas dari pola klise AI Slop**.

---

## 🚫 1. Pola Klise AI yang Dilarang (Blacklist)

### A. Pembuka Basa-Basi (*Throat-Clearing Openers*)
AI sering kali memulai tulisan dengan pengantar klise yang tidak bernilai informasi:
* ❌ *"Dalam era digital saat ini, perkembangan teknologi semakin pesat..."*
* ❌ *"Seiring dengan kemajuan zaman yang semakin modern..."*
* ❌ *"Seperti yang kita ketahui bersama, hal ini tentu bukan tanpa alasan..."*
* ❌ *"In today's fast-paced digital world..."*
* ❌ *"It is important to remember that..."*
* ❌ *"At its core, navigating this landscape..."*

**✅ Aturan Pengganti:**
Langsung mulai dari pokok masalah, argumen tesis, atau fakta teknis pada kalimat pertama. Contoh:
> *"Efisiensi arsitektur Transformer pada pemrosesan citra medis ditentukan oleh resolusi patch visual dan mekanisme self-attention."*

---

### B. Buzzwords Kosong & Klaim Mengambang
Hindari kata-kata muluk tanpa rincian:
* ❌ *"Solusi ini sangat holistik dan komprehensif..."*
* ❌ *"Menjadi game-changer yang memegang peranan krusial..."*
* ❌ *"Optimalisasi sinergis antar komponen..."*

**✅ Aturan Pengganti:**
Gunakan terminologi teknis konkret dengan parameter nyata (misal: *learning rate scheduler AdamW, latensi inferensi 18ms, normalisasi Batch vs LayerNorm, memori VRAM 4GB*).

---

### C. Struktur Formulaik Simetris
Pola AI yang paling mudah terdeteksi adalah:
1. Satu paragraf intro normatif
2. Selalu tepat 3 bullet points ber-bold (`**X**: penjelasan`, `**Y**: penjelasan`, `**Z**: penjelasan`)
3. Satu paragraf penutup klise (*"Kesimpulannya, X memegang peranan penting dalam masa depan..."*)

**✅ Aturan Pengganti:**
* Tulis dalam paragraf analitis yang mengalir dengan ritme bervariasi (campurkan kalimat pendek yang tegas dan kalimat penjelas yang mendalam).
* Jika menggunakan bullet points, variasikan jumlahnya (bisa 2 poin mendalam atau 4 poin teknis) dan jangan dibuat kaku seragam.
* Penutup harus berisi evaluasi kritis, perbandingan alternatif, atau batas limitasi sistem—bukan sekadar merangkum ulang apa yang sudah dibaca.

---

## 💡 2. Prinsip Tulisan Mahasiswa Teknik Nyata

1. **Active Voice (Kalimat Aktif):**
   * Subjek yang jelas melakukan tindakan.
   * *"Penulis menguji model menggunakan 5-fold cross validation"* lebih kuat daripada *"Pengujian model dilakukan secara berkala..."*.

2. **Menampilkan Critical Thinking & Trade-Offs:**
   * Mahasiswa informatika yang pandai selalu mempertimbangkan kelemahan teknis:
   * *"Kelebihan MobileNetV2 terletak pada komputasi ringan (3.4 juta parameter), namun memiliki penurunan akurasi sebesar 2.3% pada citra dengan variasi pencahayaan ekstrem."*

3. **Kepadatan Informasi (*Information Density*):**
   * Setiap kalimat harus membawa informasi baru atau memperdalam analisis, bukan memperpanjang jumlah kata dengan sinonim.

---

## ⚙️ 3. Integrasi Sistem

Skill ini diintegrasikan langsung ke dalam arsitektur bot:
1. **Engine**: [`src/anti_slop.py`](../src/anti_slop.py) menyuntikkan instruksi anti-slop ke prompt generator LLM.
2. **Post-Processing**: Fungsi sanitasi otomatis membersihkan frasa klise yang terselip sebelum dokumen di-render ke format `.docx`.
3. **Penerapan**: Berlaku otomatis pada perintah `/kerjakan`, cron auto-do assignment, dan penjawab materi perkuliahan.
