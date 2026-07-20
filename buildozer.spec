[app]
title = hualing
package.name = hualing
package.domain = qgb
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

# 【清理门户】去掉空格，严格限制，防止污染
source.exclude_dirs = androidBLE,bin,.buildozer

# 1. 图标主参数：控制桌面图标 (生成 res/mipmap/icon.png)
icon.filename = %(source.dir)s/android_src/splash.png

# 2. 开屏图主参数：控制开屏 loading 核心图
presplash.filename = %(source.dir)s/android_src/splash.png

# 3. 补全自适应图标，防止新系统降级去调用灰蓝色遗留图标
icon.adaptive_foreground.filename = %(source.dir)s/android_src/splash.png
icon.adaptive_background.filename = %(source.dir)s/android_src/splash.png

# 4. 开屏背景底色
android.presplash_color = #670721

# ---------------------------------------------------------------------------
# 💥 彻底干掉 4 张灰蓝色残留的核心参数（利用 Buildozer 编译后期覆盖机制）：
# ---------------------------------------------------------------------------
# 放弃脆弱的 p4a.extra_args，改用官方首选的本地资源注入挂载点。
# 它会直接把你本地 android_src/res/drawable-* 下的蓝色 ic_launcher 强制替换进最终产物。
android.output_res_dir = %(source.dir)s/android_src/res
android.res_dir = %(source.dir)s/android_src/res

version = 0.1
requirements = hostpython3==3.11.9, python3==3.11.9, kivy, able_recipe, pyjnius, pyaes, dill
android.permissions = INTERNET,BLUETOOTH_ADMIN,BLUETOOTH,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,ACCESS_BACKGROUND_LOCATION,ACCESS_WIFI_STATE,CHANGE_WIFI_STATE,RECORD_AUDIO,POST_NOTIFICATIONS,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO,REQUEST_INSTALL_PACKAGES,FOREGROUND_SERVICE,FOREGROUND_SERVICE_LOCATION,WAKE_LOCK,RECEIVE_BOOT_COMPLETED,READ_PHONE_STATE
orientation = portrait
fullscreen = 1
android.archs = arm64-v8a

# 源码目录配置
android.add_src = android_src

# 【降级维稳】强制锁定 NDK 版本，避免 r28c 带来的编译工具链崩溃
android.ndk = 25b

android.allow_backup = True
android.accept_sdk_license = True
android.skip_update = False
android.api = 33
android.minapi = 21
android.ndk_api = 21
android.private_storage = True

[buildozer]
log_level = 2
warn_on_root = 1