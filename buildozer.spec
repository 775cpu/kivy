[app]
title = hualing
package.name = hualing
package.domain = qgb
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

# 图标配置（引入绝对路径宏，防止打包切换目录时找不到文件）
icon.filename = %(source.dir)s/android_src/splash.png
icon.adaptive_icon_background = #FF0000
icon.adaptive_icon_foreground = %(source.dir)s/android_src/splash.png

# 官方正确的自定义开屏图片参数（必须加路径宏）
presplash.filename = %(source.dir)s/android_src/splash.png

# 官方正确的开屏背景色
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