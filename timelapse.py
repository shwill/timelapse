#!/usr/bin/env python3
import argparse
import csv
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import savgol_filter

SATURATION_IR_THRESHOLD = 0.12


def load_rgb(path: str) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"), dtype=np.float32)


def frame_stats(rgb: np.ndarray) -> tuple:
    lum = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    r, g, b = rgb[:, :, 0] / 255, rgb[:, :, 1] / 255, rgb[:, :, 2] / 255
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    with np.errstate(divide="ignore", invalid="ignore"):
        sat = np.where(cmax > 0, (cmax - cmin) / cmax, 0.0)
    ch = rgb.mean(axis=(0, 1)) / 255.0
    return float(np.mean(lum)), float(np.mean(sat)), ch


def sg_smooth(values: np.ndarray, window: int, poly: int = 3) -> np.ndarray:
    n = len(values)
    w = min(window, n)
    if w % 2 == 0:
        w -= 1
    if w < poly + 2:
        return values.copy()
    return savgol_filter(values, w, poly)


def find_segments(modes: list) -> list:
    segs, start = [], 0
    for i in range(1, len(modes)):
        if modes[i] != modes[i - 1]:
            segs.append((start, i, modes[i - 1]))
            start = i
    segs.append((start, len(modes), modes[-1]))
    return segs


def correction_factors(values: np.ndarray, window: int) -> np.ndarray:
    s = sg_smooth(values, window)
    return np.where(values > 1.0, s / values, 1.0)


def compute_corrections(lums, ch_means, modes, segs, window, use_wb):
    n = len(lums)
    lum_corr = np.ones(n)
    wb_corr = np.ones((n, 3))

    for start, end, mode in segs:
        lum_corr[start:end] = correction_factors(lums[start:end], window)
        if use_wb and mode == "color":
            for ch in range(3):
                wb_corr[start:end, ch] = correction_factors(ch_means[start:end, ch], window)

    return lum_corr, wb_corr


def desaturation_ramp(modes: list, segs: list, blend: int) -> np.ndarray:
    n = len(modes)
    desat = np.zeros(n)
    for i, (start, end, mode) in enumerate(segs):
        if mode == "color":
            # fade out: desat 0→1 over last blend_frames (evening, color→IR)
            if i + 1 < len(segs):
                ramp_start = max(start, end - blend)
                length = max(end - ramp_start - 1, 1)
                for j in range(ramp_start, end):
                    desat[j] = (j - ramp_start) / length
            # fade in: desat 1→0 over first blend_frames (morning, IR→color)
            if i > 0 and segs[i - 1][2] == "ir":
                ramp_end = min(end, start + blend)
                length = max(ramp_end - start - 1, 1)
                for j in range(start, ramp_end):
                    desat[j] = max(desat[j], 1.0 - (j - start) / length)
    return desat


def encode(paths, lum_corr, wb_corr, desat, fps, output, denoise=True, preset="medium"):
    first = load_rgb(paths[0])
    h, w = first.shape[:2]
    n = len(paths)

    vf = "hqdn3d=4:3:12:9" if denoise else None
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "pipe:0",
        *([ "-vf", vf ] if vf else []),
        "-c:v", "libx264", "-crf", "18", "-preset", preset,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        output,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    try:
        for i, path in enumerate(paths):
            if i % 25 == 0:
                print(f"  {i}/{n} ({i * 100 // n}%)", end="\r", flush=True)

            rgb = load_rgb(path)
            rgb = np.clip(rgb * lum_corr[i], 0, 255)

            for ch in range(3):
                rgb[:, :, ch] = np.clip(rgb[:, :, ch] * wb_corr[i, ch], 0, 255)

            if desat[i] > 0:
                gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
                for ch in range(3):
                    rgb[:, :, ch] = rgb[:, :, ch] * (1 - desat[i]) + gray * desat[i]

            proc.stdin.write(rgb.astype(np.uint8).tobytes())

        print(f"  {n}/{n} (100%)", flush=True)
    finally:
        proc.stdin.close()

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg exited {proc.returncode}")


def main():
    ap = argparse.ArgumentParser(description="Timelapse builder with deflicker and day/night handling")
    ap.add_argument("input_dir", help="Folder with JPEGs named YYYY-MM-DD_HH-MM-SS.jpg")
    ap.add_argument("output", nargs="?", help="Output MP4 (default: timelapse_<dir>.mp4)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--blend-frames", type=int, default=10,
                    help="Output frames for color→IR cross-fade (default: 10)")
    ap.add_argument("--sat-threshold", type=float, default=SATURATION_IR_THRESHOLD,
                    help="Saturation below which a frame is classified as IR (default: 0.12)")
    ap.add_argument("--deflicker-window", type=int, default=61,
                    help="Savitzky-Golay window for deflicker — larger preserves more of the brightness ramp (default: 61)")
    ap.add_argument("--date", metavar="YYYY-MM-DD",
                    help="Only include images from this date (matches filename prefix)")
    ap.add_argument("--preset", default="medium",
                    choices=["ultrafast", "superfast", "veryfast", "faster", "fast",
                             "medium", "slow", "slower", "veryslow"],
                    help="x264 encoding preset (default: medium; use slow for best quality off-NAS)")
    ap.add_argument("--no-wb", action="store_true", help="Skip white balance correction")
    ap.add_argument("--no-denoise", action="store_true",
                    help="Skip temporal denoising (hqdn3d=4:3:12:9 applied by default)")
    ap.add_argument("--dump-csv", metavar="FILE",
                    help="Write per-frame analysis to CSV (useful for tuning --sat-threshold)")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output = args.output or f"timelapse_{input_dir.name}.mp4"

    paths = sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".webp")
        and (not args.date or p.name.startswith(args.date))
    )
    if not paths:
        sys.exit(f"No JPEG files found in {input_dir}")

    n = len(paths)
    print(f"Found {n} frames → {args.fps}fps → ~{n / args.fps:.1f}s → {output}")

    print("Pass 1/2: Analyzing frames...")
    lums = np.zeros(n)
    sats = np.zeros(n)
    ch_means = np.zeros((n, 3))

    for i, p in enumerate(paths):
        if i % 50 == 0:
            print(f"  {i}/{n}...", end="\r", flush=True)
        lums[i], sats[i], ch_means[i] = frame_stats(load_rgb(str(p)))
    print(f"  {n}/{n} done.   ")

    modes = ["ir" if s < args.sat_threshold else "color" for s in sats]
    segs = find_segments(modes)
    color_n = modes.count("color")
    print(f"  Color: {color_n}  IR: {n - color_n}  Mode switches: {len(segs) - 1}")

    if args.dump_csv:
        with open(args.dump_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame", "filename", "mode", "luminance", "saturation", "r_mean", "g_mean", "b_mean"])
            for i, p in enumerate(paths):
                w.writerow([i, p.name, modes[i], f"{lums[i]:.2f}", f"{sats[i]:.4f}", *[f"{c:.4f}" for c in ch_means[i]]])
        print(f"  Analysis → {args.dump_csv}")

    lum_corr, wb_corr = compute_corrections(
        lums, ch_means, modes, segs, args.deflicker_window, not args.no_wb
    )
    desat = desaturation_ramp(modes, segs, args.blend_frames)

    print("Pass 2/2: Encoding...")
    encode([str(p) for p in paths], lum_corr, wb_corr, desat, args.fps, output,
           denoise=not args.no_denoise, preset=args.preset)
    print(f"\nDone: {output}")


if __name__ == "__main__":
    main()
