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

# ---------- 检查 cmake ----------
if ! command -v cmake &>/dev/null; then
    echo "正在配置上海时区..."
    sudo ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
    echo "Asia/Shanghai" | sudo tee /etc/timezone > /dev/null

    # 2. 配置 24 小时制时间 (LC_TIME=C)
    sed -i '/export LC_TIME=/d' ~/.profile
    echo 'export LC_TIME=C' >> ~/.profile
    export LC_TIME=C

    # 3. 安装 cmake
    echo "cmake 未安装，正在安装..."
    sudo apt-get update && sudo apt-get install -y cmake
fi

# ---------- 修复 python-for-android 的 pip 升级冲突 ----------
P4A_BUILD_FILE=".buildozer/android/platform/python-for-android/pythonforandroid/build.py"
if [ -f "$P4A_BUILD_FILE" ]; then
    python3 - <<'PY' "$P4A_BUILD_FILE"
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
old = '''        # Prepare base environment and upgrade pip:
        base_env = dict(copy.copy(os.environ))
        base_env["PYTHONPATH"] = ctx.get_site_packages_dir(arch)
        info('Upgrade pip to latest version')
        shprint(sh.bash, '-c', (
            "source venv/bin/activate && pip install -U pip"
        ), _env=copy.copy(base_env))
'''
new = '''        # Prepare base environment without forcing an in-venv pip upgrade.
        # This avoids breaking python-for-android's own pip/resolvelib stack
        # in the temporary build virtualenv.
        base_env = dict(copy.copy(os.environ))
        base_env["PYTHONPATH"] = ctx.get_site_packages_dir(arch)
        info('Skipping pip upgrade in build venv')
'''
if old in text:
    path.write_text(text.replace(old, new))
    print(f"Patched {path}")
else:
    print(f"No matching patch block found in {path}")
PY
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
ANDROID_PROJECT_DIR=".buildozer/android/platform/build-arm64-v8a/dists/hualing"
JNI_BUILD_DIR="$ANDROID_PROJECT_DIR/build/yolo_jni"
JNI_LIB_DIR="$ANDROID_PROJECT_DIR/libs/arm64-v8a"
SRC_LIB_DIR="android_src/libs/arm64-v8a"
NDK_ROOT="${ANDROID_NDK_ROOT:-${ANDROID_NDK_HOME:-/home/vscode/.buildozer/android/platform/android-ndk-r25b}}"

if [ ! -d "$NDK_ROOT" ]; then
    echo "Error: Android NDK not found at $NDK_ROOT" >&2
    exit 1
fi

mkdir -p "$JNI_BUILD_DIR" "$JNI_LIB_DIR" "$SRC_LIB_DIR" "$ANDROID_PROJECT_DIR/src/main/assets"
cp -f android_src/assets/yolov8n.param "$ANDROID_PROJECT_DIR/src/main/assets/yolov8n.param"
cp -f android_src/assets/yolov8n.bin "$ANDROID_PROJECT_DIR/src/main/assets/yolov8n.bin"
echo "Packed YOLO assets to $ANDROID_PROJECT_DIR/src/main/assets"
cmake -S android_src/jni -B "$JNI_BUILD_DIR" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$NDK_ROOT/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-24 \
    -DANDROID_STL=c++_shared \
    -DANDROID_CPP_FEATURES=exceptions \
    -DANDROID_ALLOW_UNDEFINED_SYMBOLS=TRUE
cmake --build "$JNI_BUILD_DIR" -j4

cp "$JNI_BUILD_DIR/libyolo_jni.so" "$JNI_LIB_DIR/libyolo_jni.so"
cp "$JNI_BUILD_DIR/libyolo_jni.so" "$SRC_LIB_DIR/libyolo_jni.so"
cp /home/vscode/.buildozer/android/platform/android-ndk-r25b/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so "$JNI_LIB_DIR/libc++_shared.so"
cp /home/vscode/.buildozer/android/platform/android-ndk-r25b/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so "$SRC_LIB_DIR/libc++_shared.so"
echo "Packed native library to $JNI_LIB_DIR/libyolo_jni.so"
echo "Packed libc++ runtime to $JNI_LIB_DIR/libc++_shared.so"

buildozer -v android debug 2>&1 |awk -W interactive 'BEGIN {start=systime()} {now=systime(); printf "[%s][已用时: %ds] %s\n", strftime("%H:%M:%S", now), now-start, $0; fflush()}'

SRC="$OUT_DIR/hualing-0.1-arm64-v8a-debug.apk"
DST="$OUT_DIR/hualing-0.1-arm64-v8a-debug-${TS}.apk"

if [ -f "$SRC" ]; then
    cp "$SRC" "$DST"
    echo "Created $DST"
else
    echo "Error: expected APK not found at $SRC" >&2
    exit 1
fi