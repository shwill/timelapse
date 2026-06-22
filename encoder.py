from __future__ import annotations
import subprocess
from pathlib import Path

import numpy as np

import core
from models import GrowConfig
from overlay import bake_overlay
from scheduler import build_frame_schedule, FrameEntry


def build_note_frame_map(
    config: GrowConfig, schedule: list[FrameEntry]
) -> dict[str, tuple[int, int]]:
    """Map note text → (start_output_frame, end_output_frame)."""
    note_map: dict[str, tuple[int, int]] = {}
    cum_frames = []
    f = 0
    for entry in schedule:
        cum_frames.append(f)
        f += entry.hold_frames

    for note in config.notes:
        start_frame = f  # default: after end
        for i, entry in enumerate(schedule):
            if entry.frame_dt.date() >= note.start:
                start_frame = cum_frames[i]
                break
        end_frame = start_frame + int(note.duration_s * config.normal_fps)
        note_map[note.text] = (start_frame, end_frame)
    return note_map


def encode(
    paths: list[Path],
    config: GrowConfig,
    output: str,
    deflicker_window: int = 61,
    use_wb: bool = True,
    denoise: bool = True,
    preset: str = "medium",
    progress_cb=None,
) -> None:
    if not paths:
        raise ValueError("No frames to encode")

    input_dir = paths[0].parent
    cache = core.load_cache(input_dir)
    n = len(paths)
    lums = np.zeros(n)
    sats = np.zeros(n)
    ch_means = np.zeros((n, 3))
    new_count = 0
    for i, p in enumerate(paths):
        if p.name in cache:
            lums[i], sats[i], ch_means[i] = cache[p.name]
        else:
            lums[i], sats[i], ch_means[i] = core.frame_stats(core.load_rgb(str(p)))
            cache[p.name] = (lums[i], sats[i], ch_means[i])
            new_count += 1
    if new_count:
        core.save_cache(input_dir, cache)

    modes = ["ir" if s < core.SATURATION_IR_THRESHOLD else "color" for s in sats]
    segs = core.find_segments(modes)
    lum_corr, wb_corr = core.compute_corrections(lums, ch_means, modes, segs, deflicker_window, use_wb)
    desat = core.desaturation_ramp(modes, segs, blend=10)

    schedule = build_frame_schedule(paths, config)
    note_map = build_note_frame_map(config, schedule)

    first_rgb = core.load_rgb(str(paths[0]))
    h, w = first_rgb.shape[:2]
    vf = "hqdn3d=4:3:12:9" if denoise else None
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "rgb24", "-r", str(config.normal_fps),
        "-i", "pipe:0",
        *([ "-vf", vf ] if vf else []),
        "-c:v", "libx264", "-crf", "18", "-preset", preset,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        output,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    path_to_idx = {str(p): i for i, p in enumerate(paths)}
    output_frame_idx = 0
    total_output = sum(e.hold_frames for e in schedule)

    try:
        for entry in schedule:
            i = path_to_idx[str(entry.path)]
            rgb = core.load_rgb(str(entry.path))
            rgb = np.clip(rgb * lum_corr[i], 0, 255)
            for ch in range(3):
                rgb[:, :, ch] = np.clip(rgb[:, :, ch] * wb_corr[i, ch], 0, 255)
            if desat[i] > 0:
                gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
                for ch in range(3):
                    rgb[:, :, ch] = rgb[:, :, ch] * (1 - desat[i]) + gray * desat[i]

            frame_out = bake_overlay(rgb, entry.frame_dt, config, output_frame_idx, note_map)

            for _ in range(entry.hold_frames):
                proc.stdin.write(frame_out.tobytes())
                output_frame_idx += 1
                if progress_cb and output_frame_idx % 24 == 0:
                    progress_cb(output_frame_idx, total_output)

    finally:
        proc.stdin.close()

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg exited {proc.returncode}")
