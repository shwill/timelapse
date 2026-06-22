import csv
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import savgol_filter

SATURATION_IR_THRESHOLD = 0.12
CACHE_FILE = ".timelapse_cache.csv"


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
            if i + 1 < len(segs):
                ramp_start = max(start, end - blend)
                length = max(end - ramp_start - 1, 1)
                for j in range(ramp_start, end):
                    desat[j] = (j - ramp_start) / length
            if i > 0 and segs[i - 1][2] == "ir":
                ramp_end = min(end, start + blend)
                length = max(ramp_end - start - 1, 1)
                for j in range(start, ramp_end):
                    desat[j] = max(desat[j], 1.0 - (j - start) / length)
    return desat


def load_cache(input_dir: Path) -> dict:
    p = input_dir / CACHE_FILE
    if not p.exists():
        return {}
    cache = {}
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            cache[row["filename"]] = (
                float(row["luminance"]),
                float(row["saturation"]),
                np.array([float(row["r_mean"]), float(row["g_mean"]), float(row["b_mean"])]),
            )
    return cache


def save_cache(input_dir: Path, cache: dict) -> None:
    p = input_dir / CACHE_FILE
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filename", "luminance", "saturation", "r_mean", "g_mean", "b_mean"])
        for name, (lum, sat, ch) in sorted(cache.items()):
            w.writerow([name, f"{lum:.2f}", f"{sat:.4f}", *[f"{c:.4f}" for c in ch]])
