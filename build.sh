#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# ---------- 解析命令行参数 ----------
usage() {
    echo "Usage: $0 [--color|-c|--icon] <COLOR>"
    echo "  COLOR:  (R,G,B) 或 RRGGBB (例如 (67,20,80) 或 F1F2F3)"
    echo "  If no color is provided, the icon color step is skipped."
    exit 1
}

COLOR_ARG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --color|-c|--icon)
            if [[ -z "${2:-}" ]]; then
                echo "Error: $1 requires a color value."
                usage
            fi
            COLOR_ARG="$2"
            shift 2
            ;;
        -*)
            echo "Unknown option: $1"
            usage
            ;;
        *)
            echo "Unexpected argument: $1"
            usage
            ;;
    esac
done

# ---------- 颜色处理（仅在提供颜色参数时执行） ----------
if [[ -n "$COLOR_ARG" ]]; then
    echo "Color argument provided: $COLOR_ARG"

    # 颜色转换函数
    parse_color() {
        local input="$1"
        local r g b
        input="$(echo "$input" | tr -d ' ')"
        if [[ "$input" =~ ^\(([0-9]+),([0-9]+),([0-9]+)\)$ ]]; then
            r="${BASH_REMATCH[1]}"
            g="${BASH_REMATCH[2]}"
            b="${BASH_REMATCH[3]}"
        elif [[ "$input" =~ ^([0-9A-Fa-f]{6})$ ]]; then
            r=$((16#${input:0:2}))
            g=$((16#${input:2:2}))
            b=$((16#${input:4:2}))
        else
            echo "Error: Invalid color format '$1'. Expected (R,G,B) or RRGGBB." >&2
            exit 1
        fi
        if (( r < 0 || r > 255 || g < 0 || g > 255 || b < 0 || b > 255 )); then
            echo "Error: RGB values must be between 0 and 255." >&2
            exit 1
        fi
        echo "$r $g $b"
        printf "#%02X%02X%02X\n" "$r" "$g" "$b"
    }

    read -r R G B < <(parse_color "$COLOR_ARG" | head -n1)
    HEX_COLOR="$(parse_color "$COLOR_ARG" | tail -n1)"
    echo "Parsed color: R=$R G=$G B=$B  ->  $HEX_COLOR"

    # ---------- 生成 splash.png ----------
    echo "Generating splash.png with color ($R,$G,$B)..."
    python3 -c "
import rpc, io, PIL.Image
bmp_bin = rpc.get_bmp_bytes(rgb=($R, $G, $B), size=(64,64))
img = PIL.Image.open(io.BytesIO(bmp_bin))
img.save('android_src/splash.png')
"

    # ---------- 更新 buildozer.spec ----------
    SPEC_FILE="buildozer.spec"
    if [[ ! -f "$SPEC_FILE" ]]; then
        echo "Error: $SPEC_FILE not found in current directory." >&2
        exit 1
    fi
    echo "Updating $SPEC_FILE with presplash_color = $HEX_COLOR ..."
    sed -i "s/^\([[:space:]]*android\.presplash_color[[:space:]]*=[[:space:]]*\).*/\1$HEX_COLOR/" "$SPEC_FILE"
else
    echo "No color provided, skipping icon color update (splash.png and spec)."
fi

# ---------- 可重复构建配置 ----------
FIXED_TIME=1609459200   # 2021-01-01 00:00:00 UTC
export SOURCE_DATE_EPOCH=$FIXED_TIME
export PYTHONHASHSEED=0

# 固定项目源文件的时间戳
echo "固定项目源文件的时间戳..."
find . \
    -path ./.buildozer -prune -o \
    -path ./__pycache__ -prune -o \
    -path ./bin -prune -o \
    -name '*.py' -exec touch -d "@$FIXED_TIME" {} \;

# ---------- 打包 APK ----------
TS=$(date +%Y%m%d_%H%M%S)
OUT_DIR="bin"
mkdir -p "$OUT_DIR"

# 清理旧 APK
find "$OUT_DIR" -maxdepth 1 -type f \( -name 'hualing-0.1-arm64-v8a-debug.apk' -o -name 'hualing-0.1-arm64-v8a-debug-*.apk' \) -delete

echo "Building Android APK..."
buildozer -v android debug 2>&1 | awk 'BEGIN {start=systime()} {now=systime(); printf "[%s][已用时: %ds] %s\n", strftime("%H:%M:%S", now), now-start, $0; fflush()}'

SRC="$OUT_DIR/hualing-0.1-arm64-v8a-debug.apk"
DST="$OUT_DIR/hualing-0.1-arm64-v8a-debug-${TS}.apk"

if [ -f "$SRC" ]; then
    cp "$SRC" "$DST"
    echo "Created $DST"
else
    echo "Error: expected APK not found at $SRC" >&2
    exit 1
fi