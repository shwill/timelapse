from __future__ import annotations
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from models import GrowConfig

FONT_DIR = Path(__file__).parent / "fonts"
FADE_FRAMES = 10  # frames for note fade-in and fade-out

# Phase bar colors (R, G, B, A) — completed portions
PHASE_COLORS = {
    "SEED":  (166, 227, 161, 209),
    "VEG":   (148, 226, 213, 209),
    "BLOOM": (250, 179, 135, 225),
}
FUTURE_COLOR = (255, 255, 255, 38)


def _load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    name = {"regular": "BarlowCondensed-Regular.ttf",
            "semibold": "BarlowCondensed-SemiBold.ttf",
            "bold": "BarlowCondensed-Bold.ttf"}[weight]
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _note_alpha(output_frame_idx: int, start_frame: int, end_frame: int) -> float:
    """Return alpha [0,1] for note at this output frame, with cosine fade in/out."""
    if output_frame_idx < start_frame or output_frame_idx >= end_frame:
        return 0.0
    pos = output_frame_idx - start_frame
    duration = end_frame - start_frame
    if pos < FADE_FRAMES:
        return (1 - math.cos(math.pi * pos / FADE_FRAMES)) / 2
    if pos >= duration - FADE_FRAMES:
        t = (pos - (duration - FADE_FRAMES)) / FADE_FRAMES
        return (1 + math.cos(math.pi * t)) / 2
    return 1.0


def bake_overlay(
    rgb: np.ndarray,
    frame_dt: datetime,
    config: GrowConfig,
    output_frame_idx: int,
    schedule_note_frames: dict[str, tuple[int, int]],  # text → (start_frame, end_frame)
) -> np.ndarray:
    """Bake bottom bar + active notes onto an RGB float32 array. Returns uint8."""
    h, w = rgb.shape[:2]
    base = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    frame_date = frame_dt.date()
    phase = config.phase_for_date(frame_date)

    # ── Bottom bar gradient ──────────────────────────────────────────────────
    bar_bottom = h - 12  # 12px gap from edge
    bar_top_fade = int(h * 0.70)
    for y in range(bar_top_fade, bar_bottom):
        t = (y - bar_top_fade) / max(bar_bottom - bar_top_fade, 1)
        alpha = int(min(204 + t * 10, 214))
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    # ── Row 1: Day counter (left) + Stage label (right) ─────────────────────
    font_bold = _load_font("bold", max(12, h // 22))
    font_semi = _load_font("semibold", max(10, h // 26))

    day_num = (frame_date - config.start_date).days + 1 if config.start_date else 1
    day_text = f"DAY {day_num}"

    stage_text = ""
    if phase:
        week = phase.week_number(frame_date)
        stage_text = f"{phase.abbr} · W{week}"

    text_y = bar_top_fade + int((bar_bottom - bar_top_fade) * 0.18)
    draw.text((16, text_y), day_text, font=font_bold, fill=(255, 255, 255, 255))
    if stage_text:
        bbox = draw.textbbox((0, 0), stage_text, font=font_semi)
        sw = bbox[2] - bbox[0]
        draw.text((w - sw - 16, text_y), stage_text, font=font_semi, fill=(160, 240, 160, 255))

    # ── Phase progress bar ───────────────────────────────────────────────────
    bar_y = text_y + int(h * 0.07)
    bar_h = max(3, h // 90)

    # compute total days across all phases
    if config.phases:
        first_start = config.phases[0].start
        last_phase = config.phases[-1]
        last_end = last_phase.end_date(config.phases) or frame_date
        total_days = max((last_end - first_start).days, 1)
    else:
        total_days = 1

    usable_w = w - 32
    x = 16
    for i, p in enumerate(config.phases):
        end_d = p.end_date(config.phases) or frame_date
        seg_days = max((end_d - p.start).days, 1)
        seg_w = max(4, int(usable_w * seg_days / max(total_days, 1)))
        # Clamp so we never overflow the drawable area
        seg_w = max(4, min(seg_w, w - x - 16))
        abbr = p.abbr
        color = PHASE_COLORS.get(abbr, (200, 200, 200, 180))
        phase_end = p.end_date(config.phases)
        x1 = x + seg_w
        if p.start <= frame_date and (phase_end is None or frame_date < phase_end):
            seg_elapsed = (frame_date - p.start).days
            dot_x = x + min(int(seg_w * seg_elapsed / seg_days), seg_w - 4)
            if dot_x > x:
                draw.rectangle([x, bar_y, dot_x, bar_y + bar_h], fill=color)
            if x1 > dot_x:
                draw.rectangle([dot_x, bar_y, x1, bar_y + bar_h], fill=FUTURE_COLOR)
            draw.ellipse([dot_x - 3, bar_y - 2, dot_x + 3, bar_y + bar_h + 2],
                         fill=(255, 255, 255, 230))
        elif p.start < frame_date:
            if x1 > x:
                draw.rectangle([x, bar_y, x1, bar_y + bar_h], fill=color)
        else:
            if x1 > x:
                draw.rectangle([x, bar_y, x1, bar_y + bar_h], fill=FUTURE_COLOR)
        x += seg_w + 2

    # ── Bar labels ───────────────────────────────────────────────────────────
    font_tiny = _load_font("regular", max(8, h // 36))
    x = 16
    for i, p in enumerate(config.phases):
        end_d = p.end_date(config.phases) or frame_date
        seg_days = max((end_d - p.start).days, 1)
        seg_w = max(1, int(usable_w * seg_days / max(total_days, 1)))
        draw.text((x, bar_y + bar_h + 3), p.name[:4].upper(),
                  font=font_tiny, fill=(255, 255, 255, 97))
        x += seg_w + 2

    # ── Floating note (top-center) ───────────────────────────────────────────
    font_note = _load_font("semibold", max(11, h // 24))
    for text, (start_f, end_f) in schedule_note_frames.items():
        alpha = _note_alpha(output_frame_idx, start_f, end_f)
        if alpha <= 0:
            continue
        a = int(alpha * 255)
        bbox = draw.textbbox((0, 0), text.upper(), font=font_note)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad_x, pad_y = 18, 5
        nx = (w - tw) // 2 - pad_x
        ny = int(h * 0.11)
        pill_alpha = int(alpha * 158)
        draw.rounded_rectangle(
            [nx, ny, nx + tw + pad_x * 2, ny + th + pad_y * 2],
            radius=5, fill=(0, 0, 0, pill_alpha),
            outline=(255, 208, 128, int(alpha * 64))
        )
        draw.text((nx + pad_x, ny + pad_y), text.upper(),
                  font=font_note, fill=(255, 208, 128, a))
        break  # only show first active note

    # ── Composite ────────────────────────────────────────────────────────────
    result = Image.alpha_composite(base, overlay).convert("RGB")
    return np.array(result, dtype=np.uint8)
