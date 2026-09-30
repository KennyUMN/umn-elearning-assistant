"""Verifikasi daftar model di src/ai_service.py masih hidup.

Model LLM ditarik secara berkala oleh provider (Gemini 2.5 dihapus Google,
slug :free OpenRouter rot mingguan). Daftar hardcoded di source akan basi —
skrip ini yang menangkapnya.

Run: venv/bin/python scripts/check_models.py
Exit 0 = semua hidup, 1 = ada yang mati ( cetak yang harus diganti).

Butuh GEMINI_API_KEY / OPENROUTER_API_KEY di .env. Memakai kuota sedikit:
satu panggilan "say ok" per model (max_tokens kecil).
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.ai_service import GEMINI_FALLBACK_CHAIN, MODEL_PRESETS  # noqa: E402

TIMEOUT = 60
PROMPT = "say ok"
RETRIES = 3  # SSL EOF / connection reset = jaringan, BUKAN model mati


def _is_transient(e: Exception) -> bool:
    """Error jaringan yang bukan sinyal model mati."""
    s = str(e).lower()
    return any(k in s for k in ("ssl", "eof", "timeout", "timed out",
                                "connection", "temporarily", "reset", "429", "503", "502"))


def check_gemini() -> list[str]:
    """Kirim satu generate_content per model. Kembalikan list model mati."""
    key = __import__("os").getenv("GEMINI_API_KEY", "")
    if not key:
        print("  SKIP  GEMINI_API_KEY belum di-set")
        return []

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    dead = []
    names = list(dict.fromkeys(GEMINI_FALLBACK_CHAIN
                               + [f"models/{m}" for m in MODEL_PRESETS["gemini"]["options"]]))
    for name in names:
        for attempt in range(RETRIES):
            try:
                r = client.models.generate_content(
                    model=name, contents=PROMPT,
                    config=types.GenerateContentConfig(max_output_tokens=2048))
                if (r.text or "").strip():
                    print(f"  LIVE  {name}")
                else:
                    print(f"  EMPTY {name}  (balasan kosong — cek manual)")
                    dead.append(name)
                break
            except Exception as e:
                if attempt == RETRIES - 1 or not _is_transient(e):
                    print(f"  DEAD  {name}  -> {str(e)[:120]}")
                    dead.append(name)
                    break
                time.sleep(2 * (attempt + 1))   # SSL EOF sesaat, coba lagi
    return dead


def check_openrouter() -> list[str]:
    """Cek slug ada di katalog, lalu satu chat/completions (free tier = 429 ≠ mati)."""
    import os

    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        print("  SKIP  OPENROUTER_API_KEY belum di-set")
        return []

    base = "https://openrouter.ai/api/v1"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    catalog = requests.get(f"{base}/models", headers=headers, timeout=TIMEOUT).json()
    known = {m["id"] for m in catalog.get("data", [])}

    dead = []
    for slug in MODEL_PRESETS["openrouter"]["options"]:
        if slug not in known:
            print(f"  DEAD  {slug}  -> tidak ada di katalog OpenRouter")
            dead.append(slug)
            continue
        # 429 = free tier rate limit, bukan model mati. 403 = tidak tersedia.
        # Reasoning model butuh max_tokens besar atau content-nya kosong
        # (token habis untuk reasoning) despite HTTP 200.
        try:
            r = requests.post(f"{base}/chat/completions", headers=headers, timeout=120,
                              json={"model": slug, "max_tokens": 8000,
                                    "messages": [{"role": "user", "content": PROMPT}]})
        except Exception as e:
            if _is_transient(e):
                print(f"  LIVE* {slug}  (error jaringan sesaat: {type(e).__name__} — slug ada di katalog)")
            else:
                print(f"  DEAD  {slug}  -> {type(e).__name__}: {str(e)[:100]}")
                dead.append(slug)
            continue

        if r.status_code == 200:
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if content and content.strip():
                print(f"  LIVE  {slug}")
            else:
                print(f"  EMPTY {slug}  (HTTP 200 tapi content kosong — cek manual)")
                dead.append(slug)
        elif r.status_code == 429:
            print(f"  LIVE* {slug}  (429 rate limit free tier — slug ada, tidak diuji)")
        else:
            print(f"  DEAD  {slug}  -> HTTP {r.status_code} {r.text[:100]}")
            dead.append(slug)
    return dead


def main() -> int:
    print("=== Gemini (fallback chain + /model presets) ===")
    dead_gemini = check_gemini()
    print("\n=== OpenRouter (/model presets) ===")
    dead_or = check_openrouter()

    dead = dead_gemini + dead_or
    print()
    if dead:
        print(f"MATI {len(dead)} model — ganti di src/ai_service.py:")
        for d in dead:
            print(f"  - {d}")
        return 1
    print("Semua model hidup.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
