import sys
import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import UMN_USERNAME, UMN_PASSWORD, COURSES_FILE, ASSIGNMENTS_FILE
from src.moodle_client import MoodleClient
from src.document_parser import DocumentParser

console = Console()

def run_sync():
    console.print(Panel.fit("[bold cyan]🎓 UMN E-Learning Auto-Sync & Document Extractor[/bold cyan]"))

    if not UMN_USERNAME or not UMN_PASSWORD:
        console.print("[bold red]❌ Error:[/bold red] UMN_USERNAME dan UMN_PASSWORD belum diisi di file `.env`.")
        console.print("Silakan edit file `.env` terlebih dahulu.")
        sys.exit(1)

    client = MoodleClient()
    with console.status("[bold green]Sedang login ke E-Learning UMN...[/bold green]"):
        if not client.login():
            console.print("[bold red]❌ Gagal login ke E-Learning UMN![/bold red] Cek kembali username/password.")
            sys.exit(1)

    console.print("[bold green]✅ Berhasil login ke E-Learning UMN![/bold green]\n")

    with console.status("[bold yellow]Mencari daftar mata kuliah aktif...[/bold yellow]"):
        courses = client.get_enrolled_courses()

    if not courses:
        console.print("[yellow]⚠️ Tidak ada mata kuliah yang terdeteksi atau halaman sedang berubah.[/yellow]")
        return

    table = Table(title="📚 Mata Kuliah Terdeteksi", show_header=True, header_style="bold magenta")
    table.add_column("No", style="dim", width=4)
    table.add_column("ID", width=10)
    table.add_column("Nama Mata Kuliah")

    for i, c in enumerate(courses, 1):
        table.add_row(str(i), c["id"], c["title"])

    console.print(table)
    console.print()

    # Sync materials
    total_downloaded = 0
    with console.status("[bold blue]Mengunduh materi & slide terbaru...[/bold blue]"):
        for course in courses:
            new_files = client.sync_course_materials(course)
            total_downloaded += len([f for f in new_files if f.get("is_new")])

    console.print(f"[bold green]✅ Sinkronisasi dokumen selesai! ({total_downloaded} file baru terunduh)[/bold green]\n")

    # Extract text
    console.print("[bold yellow]⚙️ Mengekstrak teks dari PDF, PPTX, dan DOCX...[/bold yellow]")
    parser = DocumentParser()
    extracted = parser.process_all()
    console.print(f"[bold green]✅ Ekstraksi teks selesai! ({len(extracted)} file teks baru diproses)[/bold green]\n")

    # Fetch assignments
    with console.status("[bold purple]Memeriksa tugas & deadline...[/bold purple]"):
        assignments = client.get_assignments(courses)

    pending = [a for a in assignments if not a.get("is_submitted")]
    if pending:
        assign_table = Table(title="⚠️ Tugas Pending / Belum Selesai", show_header=True, header_style="bold red")
        assign_table.add_column("Mata Kuliah", style="cyan")
        assign_table.add_column("Judul Tugas", style="bold")
        assign_table.add_column("Deadline", style="yellow")
        assign_table.add_column("Sisa Waktu", style="red")

        for p in pending:
            assign_table.add_row(
                p.get("course_name", "")[:30],
                p.get("title", "")[:35],
                p.get("due_date", ""),
                p.get("time_remaining", "")
            )
        console.print(assign_table)
    else:
        console.print("[bold green]🎉 Tidak ada tugas pending yang terdeteksi![/bold green]")

    console.print("\n[bold cyan]🚀 Sistem E-Learning Assistant siap digunakan![/bold cyan]")

if __name__ == "__main__":
    run_sync()
