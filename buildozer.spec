[app]
title = My Kivy App
package.name = mykivyapp
package.domain = qgb.hualing
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
icon.filename = icon.bmp
icon.adaptive_icon_background = #FF0000
icon.adaptive_icon_foreground = icon.bmp
version = 0.1
requirements = hostpython3==3.11.9, python3==3.11.9, kivy, android, able_recipe
# 增加了 INTERNET 权限以允许网络套接字(Socket)运行
android.permissions = INTERNET, BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_SCAN, BLUETOOTH_CONNECT, ACCESS_FINE_LOCATION
orientation = portrait
fullscreen = 1
android.archs = arm64-v8a
#, armeabi-v7a
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