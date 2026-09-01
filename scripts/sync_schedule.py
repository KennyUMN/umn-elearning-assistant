"""Auto-Detect & Audit Jadwal vs E-Learning UMN.

Apa yang dilakukan script ini:
1. LOGIN otomatis ke E-Learning UMN dan DETEKSI semua mata kuliah terdaftar
   (tidak perlu input manual — kursus langsung ditarik dari Moodle).
2. Membandingkan hasil deteksi dengan jadwal kuliah manual di
   `data/metadata/class_schedule.json` (hari/jam/ruang memang tidak tersedia
   di E-Learning, jadi bagian itu diisi manual sekali saja).
3. Menampilkan laporan silang:
   - Mata kuliah e-learning yang BELUM ada di jadwal
   - Entri jadwal yang TIDAK punya materi di e-learning (briefing tetap jalan
     tapi tanpa konteks RPKPS/modul untuk matkul itu)

Cara pakai:
    python scripts/sync_schedule.py          # deteksi + audit
    python scripts/sync_schedule.py --sync   # + unduh materi & ekstrak teks juga
"""
import sys
import re
import json
from pathlib import Path

# Bisa dijalankan langsung: python scripts/sync_schedule.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from src.config import SCHEDULE_FILE, EXTRACTED_TEXT_DIR
from src.moodle_client import MoodleClient
from src.document_parser import DocumentParser

console = Console()


def normalize(code: str) -> str:
    """'EM 105 - B' -> 'em105b' (hapus spasi & tanda baca, lowercase)."""
    return re.sub(r"[^a-z0-9]", "", (code or "").lower())


def extract_course_code(title: str) -> str:
    """Ambil kode dari judul kursus e-learning: '(IF571-B) Cybersecurity - LEC' -> 'IF571-B'."""
    m = re.search(r"\(([A-Z]{2,6}\s?\d{3,4}(?:\s?-\s?[A-Z0-9-]+)?)\)", title or "")
    return re.sub(r"\s+", "", m.group(1)) if m else ""


def code_root(code: str) -> str:
    """Root kode untuk pencocokan longgar: 'IF570-AL' -> 'if570'."""
    return normalize((code or "").split("-")[0])


def load_schedule() -> dict:
    if SCHEDULE_FILE.exists():
        try:
            return json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            console.print(f"[red]⚠️ Gagal baca {SCHEDULE_FILE}: {e}[/red]")
    return {}


def main():
    do_sync = "--sync" in sys.argv

    console.print("[bold cyan]🔎 Auto-Detect Mata Kuliah dari E-Learning UMN[/bold cyan]\n")

    # --- 1. Deteksi otomatis dari e-learning ---
    client = MoodleClient()
    with console.status("[bold green]Login & mendeteksi mata kuliah terdaftar...[/bold green]"):
        if not client.login():
            console.print("[bold red]❌ Gagal login ke E-Learning UMN![/bold red] Cek UMN_USERNAME/UMN_PASSWORD di .env")
            sys.exit(1)
        courses = client.get_enrolled_courses()  # otomatis menyimpan courses.json

    if not courses:
        console.print("[red]⚠️ Tidak ada mata kuliah terdeteksi dari e-learning.[/red]")
        sys.exit(1)

    el_table = Table(title=f"📚 {len(courses)} Mata Kuliah Terdeteksi dari E-Learning", header_style="bold magenta")
    el_table.add_column("Kode", style="cyan", width=14)
    el_table.add_column("Nama")
    for c in courses:
        el_table.add_row(extract_course_code(c.get("title", "")) or "-", c.get("title", ""))
    console.print(el_table)

    if do_sync:
        with console.status("[bold blue]Mengunduh & mengekstrak materi terbaru...[/bold blue]"):
            for c in courses:
                client.sync_course_materials(c)
            DocumentParser().process_all()
        console.print("[bold green]✅ Materi diperbarui & teks diekstrak.[/bold green]\n")

    # --- 2. Audit silang dengan jadwal manual ---
    schedule = load_schedule()
    if not schedule:
        console.print(f"[yellow]⚠️ {SCHEDULE_FILE} belum ada/isinya kosong — isi hari, jam, dan ruang kuliahmu.[/yellow]")
        return

    schedule_entries = []
    for day, entries in schedule.items():
        for e in entries or []:
            schedule_entries.append({**e, "day": day})

    sched_roots = {code_root(e.get("code", "")) for e in schedule_entries if e.get("code")}

    console.print()
    match_table = Table(title="🔁 Hasil Audit Silang: Jadwal ↔ E-Learning", header_style="bold cyan")
    match_table.add_column("Hari", style="bold", width=8)
    match_table.add_column("Matkul (jadwal)")
    match_table.add_column("Kode", style="cyan", width=14)
    match_table.add_column("Materi E-Learning", width=22)

    unmatched_el = []
    for e in sorted(schedule_entries, key=lambda x: list(schedule.keys()).index(x["day"])):
        root = code_root(e.get("code", ""))
        # Folder materi ada?
        folder = next((d for d in EXTRACTED_TEXT_DIR.iterdir()
                       if d.is_dir() and root and root in normalize(d.name)), None) if root else None
        status = f"✅ {len(list(folder.glob('*.txt')))} dokumen" if folder and list(folder.glob("*.txt")) else "➖ tidak ada di e-learning"
        match_table.add_row(e["day"], e.get("course", ""), e.get("code", ""), status)

    console.print(match_table)

    # Matkul e-learning yang belum masuk jadwal
    for c in courses:
        cc = extract_course_code(c.get("title", ""))
        if cc and code_root(cc) not in sched_roots:
            unmatched_el.append(c.get("title", ""))

    console.print()
    if unmatched_el:
        console.print("[bold yellow]⚠️ Mata kuliah e-learning ini belum ada di jadwal:[/bold yellow]")
        for t in unmatched_el:
            console.print(f"   • {t}")
        console.print("[dim]  → Tambahkan ke class_schedule.json kalau memang kuliahnya diambil.[/dim]\n")
    else:
        console.print("[bold green]✅ Semua mata kuliah e-learning sudah tercakup di jadwal.[/bold green]\n")

    no_material = [e for e in schedule_entries
                   if not any(code_root(e.get("code", "")) in normalize(d.name)
                              for d in EXTRACTED_TEXT_DIR.iterdir() if d.is_dir())]
    if no_material:
        console.print("[bold yellow]ℹ️ Matkul jadwal ini tidak punya materi di e-learning (briefing tetap jalan, tanpa RPKPS/modul):[/bold yellow]")
        for e in no_material:
            console.print(f"   • [{e['day']}] {e.get('course')} ({e.get('code')})")
        console.print()


if __name__ == "__main__":
    main()
