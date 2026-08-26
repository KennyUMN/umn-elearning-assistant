#!/usr/bin/env python3
"""Render docs/demo.gif — simulated Telegram conversation for the README."""
from PIL import Image, ImageDraw, ImageFont
import os

# ---------- config ----------
W, H = 640, 1290
HEADER_H = 104
MAX_BUBBLE_W = 460
LINE_H = 30
PAD_V = 36
GAP = 12
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "demo.gif")

BG         = (23, 33, 43)     # telegram dark bg
HEADER_BG  = (23, 33, 43)
IN_BUBBLE  = (30, 42, 56)
OUT_BUBBLE = (43, 82, 120)
TEXT       = (240, 240, 240)
SUBTLE     = (150, 158, 166)
TIME_COL   = (124, 132, 140)
DOT        = (180, 186, 192)


def load_font(size):
    candidates = [
        ("/System/Library/Fonts/Helvetica.ttc", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ]
    for path, idx in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default()


FONT_MSG = load_font(24)
FONT_NAME = load_font(26)
FONT_TIME = load_font(18)
FONT_SUB = load_font(20)


def wrap(text, font, maxw, draw):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = (cur + " " + word).strip()
            if draw.textlength(trial, font=font) <= maxw:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def measure_block(msg, draw):
    lines = wrap(msg["text"], FONT_MSG, MAX_BUBBLE_W - 44, draw)
    return lines, len(lines) * LINE_H + PAD_V


def draw_header(d):
    d.rectangle([0, 0, W, HEADER_H], fill=HEADER_BG)
    d.line([(0, HEADER_H), (W, HEADER_H)], fill=(15, 22, 29), width=2)
    cx, cy, r = 66, HEADER_H // 2, 32
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(48, 106, 160))
    t = "UMN"
    tw = d.textlength(t, font=FONT_SUB)
    d.text((cx - tw / 2, cy - 13), t, font=FONT_SUB, fill=TEXT)
    d.text((112, 26), "UMN E-Learning Assistant", font=FONT_NAME, fill=TEXT)
    d.text((112, 60), "online", font=FONT_SUB, fill=SUBTLE)


def draw_message(d, y_bottom, msg):
    lines, bh = measure_block(msg, d)
    bw = max(d.textlength(l, font=FONT_MSG) for l in lines) + 44
    x0 = 20 if not msg["me"] else W - 20 - bw
    y0 = y_bottom - bh
    d.rounded_rectangle([x0, y0, x0 + bw, y_bottom], radius=16,
                        fill=OUT_BUBBLE if msg["me"] else IN_BUBBLE)
    ty = y0 + 12
    for l in lines:
        d.text((x0 + 22, ty), l, font=FONT_MSG, fill=TEXT)
        ty += LINE_H
    tl = msg["time"]
    tw = d.textlength(tl, font=FONT_TIME)
    d.text((x0 + bw - tw - 14, y_bottom - 26), tl, font=FONT_TIME, fill=TIME_COL)
    return y0 - GAP  # y for next bubble above


def draw_typing(d, y_bottom, phase):
    bw = 92
    x0, y0 = 20, y_bottom - 58
    d.rounded_rectangle([x0, y0, x0 + bw, y_bottom], radius=16, fill=IN_BUBBLE)
    for i in range(3):
        dx = x0 + 24 + i * 22
        dy = (y0 + y_bottom) // 2
        bounce = 3 if (i + phase) % 3 == 0 else 0
        r = 6
        d.ellipse([dx - r, dy - r - bounce, dx + r, dy + r - bounce], fill=DOT)


MSGS = [
    {"me": True, "time": "06:59", "text": "/briefing"},
    {"me": False, "time": "06:59",
     "text": "BRIEFING KELAS — Senin\n\n"
             "08:00 Enterprise Architecture\n"
             "- Baca slides week 5: TOGAF ADM\n"
             "- Fokus: Migration Planning\n\n"
             "13:00 English 3\n- Review rubric Presentation Task"},
    {"me": True, "time": "12:41", "text": "Jelaskan TOGAF ADM week 5 dong"},
    {"me": False, "time": "12:41",
     "text": "TOGAF ADM = siklus 8 fase untuk\nmerancang enterprise architecture.\n\n"
             "Slides week 5 fokus ke fase H:\nmenyusun roadmap transisi &\nprioritas work package."},
    {"me": True, "time": "17:59", "text": "/tugas"},
    {"me": False, "time": "17:59",
     "text": "TUGAS PENDING:\n\n"
             "1. EA — Assignment 3\n   Deadline Jumat 23:59 (2 hari)\n   BELUM SUBMIT\n\n"
             "2. English 3 — Presentation Outline\n   Deadline Senin 23:59\n\n"
             "Saran: kerjakan EA dulu ya."},
]


def render(n_visible, typing=False, phase=0):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    draw_header(d)
    y = float(H - 24)
    for msg in reversed(MSGS[:n_visible]):
        _, bh = measure_block(msg, d)
        if y - bh < HEADER_H + 40:
            break  # would overlap header — stop cleanly
        y = draw_message(d, y, msg)
    if typing:
        draw_typing(d, min(y, H - 24), phase)
    return img


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    frames, durations = [], []

    def add(n, typ=False, dur=700, phases=1):
        for p in range(phases):
            frames.append(render(n, typ, p))
            durations.append(dur if not typ else 420)

    add(1, dur=900)                       # user /briefing
    add(1, typ=True, phases=3)            # bot typing
    add(2, dur=2600)                      # briefing reply
    add(3, dur=900)                       # user question
    add(3, typ=True, phases=3)
    add(4, dur=2600)                      # explanation
    add(5, dur=900)                       # user /tugas
    add(5, typ=True, phases=3)
    add(6, dur=3600)                      # tugas reply (final hold)

    pal_img = frames[-1].quantize(colors=256, method=Image.MEDIANCUT)
    q_frames = [f.quantize(palette=pal_img, dither=Image.NONE) for f in frames]
    q_frames[-1].save(
        OUT, save_all=True, append_images=q_frames[:-1],
        duration=durations, loop=0, optimize=True, disposal=1,
    )
    print(f"saved {OUT} ({os.path.getsize(OUT)/1024:.0f} KB, {len(q_frames)} frames)")


if __name__ == "__main__":
    main()
