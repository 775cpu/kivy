[app]
title = hualing
package.name = hualing
package.domain = qgb
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

# 图标配置（保持你的路径，修正为标准的6位纯红实色）
icon.filename = android_src/splash.png
icon.adaptive_icon_background = #FF0000
icon.adaptive_icon_foreground = android_src/splash.png

# 官方正确的自定义开屏图片参数
presplash.filename = android_src/splash.png

# 官方正确的开屏背景色（必须是6位不透明色，与图片底色融为一体）
android.presplash_color = #FF0000

version = 0.1
requirements = hostpython3==3.11.9, python3==3.11.9, kivy, android, able_recipe,pyjnius,pyaes,dill
# 增加了 INTERNET 权限以允许网络套接字(Socket)运行
android.permissions = INTERNET, BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_SCAN, BLUETOOTH_CONNECT, ACCESS_FINE_LOCATION
orientation = portrait
fullscreen = 1
android.archs = arm64-v8a
android.add_src = android_src
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