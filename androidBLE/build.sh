#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if command -v gradle >/dev/null 2>&1; then
    GRADLE_CMD="gradle"
elif [ -x "$PWD/gradlew" ]; then
    GRADLE_CMD="$PWD/gradlew"
else
    echo "未找到 Gradle。请先安装 Gradle 或者在当前环境中配置 PATH。"
    echo "可尝试：sudo apt update && sudo apt install -y gradle"
    exit 1
fi

if [ "$GRADLE_CMD" = "$PWD/gradlew" ]; then
    "$GRADLE_CMD" :app:assembleDebug
else
    "$GRADLE_CMD" :app:assembleDebug
fi

OUT_DIR="$PWD/app/build/outputs/apk/debug"
APK_PATH="$(find "$OUT_DIR" -maxdepth 1 -type f -name '*.apk' | head -n 1)"

if [ -n "$APK_PATH" ]; then
    echo "APK 输出: $APK_PATH"
else
    echo "未生成 APK" >&2
    exit 1
fi
