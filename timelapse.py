#!/usr/bin/env python3
"""
Legacy CLI shim. Use `python app.py --encode` for new grow.json-based workflow.
This shim runs the full pipeline without grow.json (no phases/slow zones/overlay).
"""
import argparse
import sys
from pathlib import Path

import core
from models import GrowConfig
from encoder import encode


def main():
    ap = argparse.ArgumentParser(description="Timelapse builder (legacy shim)")
    ap.add_argument("input_dir")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--blend-frames", type=int, default=10)
    ap.add_argument("--sat-threshold", type=float, default=core.SATURATION_IR_THRESHOLD)
    ap.add_argument("--deflicker-window", type=int, default=61)
    ap.add_argument("--date", metavar="YYYY-MM-DD")
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--no-wb", action="store_true")
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--dump-csv", metavar="FILE")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output = args.output or f"timelapse_{input_dir.name}.mp4"
    paths = sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".webp")
        and (not args.date or p.name.startswith(args.date))
    )
    if not paths:
        sys.exit(f"No frames found in {input_dir}")

    cfg = GrowConfig(normal_fps=args.fps)
    print(f"Found {len(paths)} frames → {args.fps}fps → {output}")
    encode(paths, cfg, output,
           deflicker_window=args.deflicker_window,
           use_wb=not args.no_wb,
           denoise=not args.no_denoise,
           preset=args.preset)
    print(f"\nDone: {output}")


if __name__ == "__main__":
    main()
