# Hualing Kivy Android App

这是一个基于 Kivy 的 Android 应用，集成了摄像头预览、YOLO 实时检测、JNI 原生推理以及 BLE 相关能力。

## 1. 项目定位

- 主要入口：main.py
- 使用 Buildozer 打包为 Android APK
- 运行时通过原生 JNI 调用 YOLO 模型进行推理
- BLE 相关代码位于单独的 Java 实现工程中

## 2. 目录说明

- main.py：应用主入口
- rpc.py：RPC 服务入口
- detection_core.py：检测相关逻辑
- android_src/：Android 资源、JNI、assets、打包配置
- androidBLE/：独立的 Java 实现工程，不作为当前 APK 的主代码来源
- YOLOv8-Mobile/：另一个独立 Android 项目，不应打进当前应用包

> 说明：androidBLE 和 YOLOv8-Mobile 这两个目录都是独立工程，当前 APK 打包时应避免被包含进去。

## 3. 功能特点

- 摄像头预览与画面处理
- YOLO 模型的原生推理链路
- BLE / 蓝牙桥接能力
- 支持 Buildozer 直接构建 Android APK

## 4. 环境准备

建议在 VS Code Codespaces 或 Dev Container 中构建。

### 必要依赖

- Python 3.11
- Java / Android SDK / NDK
- CMake
- Pillow
- Buildozer

### 常见依赖安装

```bash
sudo apt-get update
sudo apt-get install -y cmake
```

如果后续构建提示缺少 Rust 或 Python 依赖，可根据报错补齐对应工具链。

## 5. 构建方式

### 首次构建

```bash
./build.sh
```

首次构建通常需要较长时间，视网络和依赖下载情况而定，可能需要 30~40 分钟。

### 重新构建

```bash
./build.sh
```

如果需要清理旧构建产物：

```bash
buildozer android clean
```

## 6. 生成的 APK

构建完成后，APK 会输出到：

```bash
bin/
```

例如：

```bash
bin/hualing-0.1-arm64-v8a-debug.apk
```

## 7. 打包说明

当前项目已通过 Buildozer 配置尽量避免把无关目录和构建缓存打进 APK。

### 已经排除的内容

- androidBLE/
- YOLOv8-Mobile/
- .buildozer/
- bin/
- Gradle / 构建缓存目录

这样可以有效减少 assets/private.tar 的体积，避免把独立工程和构建中间产物一起打包。

## 8. 生成启动图 / 图标辅助脚本

如果需要重新生成启动图：

```bash
python3 -c "import rpc, io, PIL.Image; bmp_bin = rpc.get_bmp_bytes(rgb=(67,20,80), size=(90,210)); img = PIL.Image.open(io.BytesIO(bmp_bin)); img.save('android_src/splash.png')"
```

## 9. 常见问题

### 1) Buildozer 命令在 Codespaces 中找不到

可以在 VS Code 中执行：

- Ctrl+Shift+P
- 选择 Rebuild

### 2) 重新打包时卡在旧缓存

可尝试清理部分构建目录：

```bash
rm -rf .buildozer/android/platform/build-arm64-v8a/build/venv
rm -rf .buildozer/android/platform/build-arm64-v8a/build/python-installs/hualing
rm -rf .buildozer/android/platform/build-arm64-v8a/dists/hualing
```

然后重新执行构建。

### 3) APK 体积过大

优先检查：

- 是否把独立项目目录打进了源码树
- 是否把构建中间产物打进了私有资源包
- 是否保留了不必要的模型、图片和缓存文件

## 10. 备注

- 本项目的 Android 侧原生加载链路会输出详细日志，便于排查 JNI / SO 加载问题。
- 如果要进一步收缩包体积，可以继续精简资源、模型和 Python 字节码包内容。
