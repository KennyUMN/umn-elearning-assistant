import sys
import logging
from rich.console import Console
from rich.panel import Panel

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UMN_USERNAME, GEMINI_API_KEY
from src.scheduler import start_scheduler
from src.telegram_bot import create_bot_app

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")

def main():
    console.print(Panel.fit(
        "[bold cyan]🎓 UMN E-Learning Assistant — Telegram & Cron Automation[/bold cyan]\n"
        "[dim]Auto-Sync • Daily Class Prep Briefing • Assignment Deadlines • AI Tutor[/dim]"
    ))

    # Verification checks
    if not UMN_USERNAME:
        console.print("[yellow]⚠️ Warning: `UMN_USERNAME` belum diatur di `.env`.[/yellow]")
    if not GEMINI_API_KEY:
        console.print("[yellow]⚠️ Warning: `GEMINI_API_KEY` belum diatur di `.env`.[/yellow]")
    if not TELEGRAM_BOT_TOKEN:
        console.print("[bold red]❌ Error: `TELEGRAM_BOT_TOKEN` belum diatur di `.env`.[/bold red]")
        console.print("Silakan buat bot di @BotFather dan masukkan token ke `.env`.")
        sys.exit(1)

    # 1. Start Background Scheduler (Cron Jobs)
    console.print("[bold green]⏰ Menjalankan Background Scheduler (Cron Jobs)...[/bold green]")
    scheduler = start_scheduler()

    # 2. Start Telegram Bot Polling
    console.print("[bold green]🤖 Menjalankan Telegram Bot...[/bold green]")
    bot_app = create_bot_app()
    if bot_app:
        console.print("[bold cyan]✨ Bot aktif! Buka Telegram dan kirim `/start` ke bot kamu.[/bold cyan]\n")
        try:
            bot_app.run_polling()
        except (KeyboardInterrupt, SystemExit):
            console.print("\n[bold yellow]Mematikan bot dan scheduler...[/bold yellow]")
            scheduler.shutdown()

if __name__ == "__main__":
    main()
