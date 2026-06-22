#!/bin/bash
set -euo pipefail

PRESET="${PRESET:-medium}"
FPS="${FPS:-24}"
INPUT_BASE="${INPUT_BASE:-/data}"
OUTPUT_DIR="${OUTPUT_DIR:-/data/timelapses}"
DATE="${DATE:-$(date -d yesterday +%Y-%m-%d)}"

export TIMELAPSE_DATA_DIR="$INPUT_BASE"
export TIMELAPSE_OUTPUT_DIR="$OUTPUT_DIR"

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

if [[ "${EDITOR_MODE:-0}" == "1" ]]; then
    exec python /app/app.py --editor --host 0.0.0.0 --port 8080
fi

python /app/app.py --encode --date "$DATE" --preset "$PRESET"

for INPUT in "$INPUT_BASE"/*/; do
    CAM=$(basename "$INPUT")
    [[ "$CAM" == "timelapses" ]] && continue
    stitch "$CAM"
done
