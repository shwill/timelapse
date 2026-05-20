#!/bin/bash
set -euo pipefail

PRESET="${PRESET:-medium}"
FPS="${FPS:-24}"
INPUT_BASE="${INPUT_BASE:-/data}"
OUTPUT_DIR="${OUTPUT_DIR:-/data/timelapses}"
DATE="${DATE:-$(date -d yesterday +%Y-%m-%d)}"

mkdir -p "$OUTPUT_DIR"

stitch() {
    local cam="$1"
    local latest="$OUTPUT_DIR/${cam}_latest.mp4"
    local tmpfile
    tmpfile=$(mktemp /tmp/concat_XXXXXX.txt)

    find "$OUTPUT_DIR" -name "${cam}_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].mp4" \
        | sort \
        | while read -r f; do printf "file '%s'\n" "$f"; done \
        > "$tmpfile"

    local count
    count=$(wc -l < "$tmpfile" | tr -d ' ')

    if [[ "$count" -eq 0 ]]; then
        echo "[$cam] No daily files to stitch yet"
        rm -f "$tmpfile"
        return
    fi

    echo "[$cam] Stitching $count daily files → $latest"
    ffmpeg -y -f concat -safe 0 -i "$tmpfile" -c copy "$latest"
    rm -f "$tmpfile"
}

for INPUT in "$INPUT_BASE"/*/; do
    CAM=$(basename "$INPUT")
    [[ "$CAM" == "timelapses" ]] && continue
    DAILY="$OUTPUT_DIR/${CAM}_${DATE}.mp4"

    img_count=$(find "$INPUT" -maxdepth 1 -name "${DATE}_*.jpg" | wc -l | tr -d ' ')
    if [[ "$img_count" -eq 0 ]]; then
        echo "[$CAM] No images for $DATE, skipping encode"
    else
        echo "[$CAM] Encoding $DATE ($img_count images) → $DAILY"
        python /app/timelapse.py "$INPUT" "$DAILY" \
            --date "$DATE" \
            --fps "$FPS" \
            --preset "$PRESET"
    fi

    stitch "$CAM"
done
