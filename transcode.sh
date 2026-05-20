#!/usr/bin/env bash
# Convert H.264 MP4 to H.265/HEVC — ~40% smaller at same quality
# -tag:v hvc1 ensures compatibility with Apple QuickTime / iOS
set -euo pipefail

INPUT="${1:?Usage: $0 <input.mp4> [output.mp4]}"
OUTPUT="${2:-${INPUT%.mp4}_hevc.mp4}"

ffmpeg -i "$INPUT" \
    -c:v libx265 \
    -crf 22 \
    -preset slow \
    -pix_fmt yuv420p \
    -movflags +faststart \
    -tag:v hvc1 \
    "$OUTPUT"

echo "Done: $OUTPUT"
