#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

TS=$(date +%Y%m%d_%H%M%S)
OUT_DIR="bin"
mkdir -p "$OUT_DIR"

# Remove older APKs so only the latest build remains.
find "$OUT_DIR" -maxdepth 1 -type f \( -name 'mykivyapp-0.1-arm64-v8a-debug.apk' -o -name 'mykivyapp-0.1-arm64-v8a-debug-*.apk' \) -delete

echo "Building Android APK..."
buildozer -v android debug 2>&1 | awk 'BEGIN {start=systime()} {now=systime(); printf "[%s][已用时: %ds] %s\n", strftime("%H:%M:%S", now), now-start, $0; fflush()}'

SRC="$OUT_DIR/mykivyapp-0.1-arm64-v8a-debug.apk"
DST="$OUT_DIR/mykivyapp-0.1-arm64-v8a-debug-${TS}.apk"

if [ -f "$SRC" ]; then
    cp "$SRC" "$DST"
    echo "Created $DST"
else
    echo "Error: expected APK not found at $SRC" >&2
    exit 1
fi
