[app]
title = hualing
package.name = hualing
package.domain = qgb
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
icon.filename = .icon/icon.bmp
icon.adaptive_icon_background = #FF0000
icon.adaptive_icon_foreground = .icon/icon.bmp

# 自定义开屏图片
android.splash_image = .icon/icon.bmp
# 启动图背景色（不填默认黑色，和图片底色匹配更美观）
android.splash_color = #FF0000
# 是否隐藏默认Kivy文字水印（必须加，否则底部显示Powered by Kivy）
android.splash_remove_label = True
# 全屏启动图，和你fullscreen=1匹配
android.splash_fullscreen = True

version = 0.1
requirements = hostpython3==3.11.9, python3==3.11.9, kivy, android, able_recipe,pyjnius,pyaes,dill
# 增加了 INTERNET 权限以允许网络套接字(Socket)运行
android.permissions = INTERNET, BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_SCAN, BLUETOOTH_CONNECT, ACCESS_FINE_LOCATION
orientation = portrait
fullscreen = 1
android.archs = arm64-v8a
#, armeabi-v7a
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