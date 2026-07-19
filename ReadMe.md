第一次打开codespaces buildozer命令找不到
ctrl+shift+p  rebuild 大概5分钟

./build.sh 第一次至少半个小时  [已用时: 1949s] 
buildozer android clean 后重新./build.sh [1500多秒]


androidBLE 目录 是纯java实现独立apk




python3 -c "import rpc, io, PIL.Image; bmp_bin = rpc.get_bmp_bytes(rgb=(255,0,100), size=(512,512)); img = PIL.Image.open(io.BytesIO(bmp_bin)); img.save('android_src/splash.png')"



git clone --depth=1 https://gh-proxy.com/https://github.com/775cpu/kivy.git
Cloning into 'kivy'...
remote: Enumerating objects: 13, done.
remote: Counting objects: 100% (13/13), done.
remote: Compressing objects: 100% (11/11), done.
fatal: fetch-pack: invalid index-pack output


cd /workspaces/kivy && latest_apk=$(basename "$(ls -1t bin/*.apk | head -1)") && git add -A && git commit -m "${latest_apk}" && git push 



buildozer android clean 会完全重新编译太慢了需要30分钟 。
rm -rf /workspaces/kivy/.buildozer/android/platform/build-arm64-v8a/build/venv


因为底层最耗时的 C/Rust 源码编译结果保存在 other_builds 目录下，我们只要避开它，只删掉跟 pip 报错相关的目标安装目录和未完成的独立包分布（Dist）即可。

检查并确认 buildozer.spec 中的 requirements 里已经去掉了 ,android。

rm -rf .buildozer/android/platform/build-arm64-v8a/build/python-installs/hualing
rm -rf .buildozer/android/platform/build-arm64-v8a/dists/hualing
直接重新打包




独立图片文件（SDL 默认灰蓝色图标，4 张）
ic_launcher...（mdpi 小尺寸 SDL 标）
ic_launcher...（hdpi 中尺寸 SDL 标）
ic_launcher...（xhdpi 大尺寸 SDL 标）
ic_launcher...（xxhdpi 超大尺寸 SDL 标）
这四张就是检测报告里❌ 顽固残留灰蓝图，对应 4 个分辨率 drawable 旧图标，编译自动生成，不受本地 android_src 覆盖。
独立深蓝色自定义图片（3 张，你目标色 (11,22,100)，全部正常替换）
icon.png：自适应图标主图
icon_backgr... → icon_background.png 自适应图标背景层
icon_foregr... → icon_foreground.png 自适应图标前景层
这三张存放在res/mipmap内，spec 自适应图标参数已完美生效，桌面图标显示正常。

apk\res\drawable-hdpi-v4\ic_launcher.png
apk\res\drawable-mdpi-v4\ic_launcher.png
apk\res\drawable-xhdpi-v4\ic_launcher.png
apk\res\drawable-xxhdpi-v4\ic_launcher.png  python-for-android (p4a) 在其 SDL2 bootstrap 模板中内置的默认图标资源。

这就是为什么它如此“顽固”的原因：
它不是你项目代码库中的文件，而是被封装在 p4a 预编译的二进制模板库里。当你执行 buildozer android debug 时，构建工具会自动将这套默认图标集注入到 res/drawable-xxhdpi/ 等目录下。由于它是作为“模板默认值”存在的，如果不强制替换掉构建环境中的那个 .png 源文件，它就会在每次构建时覆盖你的自定义资源



import os,zipfile
from PIL import Image

def get_img_status(img_path, target_rgb, is_file_obj=False):
    try:
        with Image.open(img_path) as img:
            img = img.convert('RGBA')
            w, h = img.size
            center_pixel = img.getpixel((w // 2, h // 2))
            center_rgb = center_pixel[:3]
            
            if center_rgb == target_rgb:
                status = "✅ 完美匹配"
            elif center_rgb == (79, 97, 119):
                status = "❌ 顽固残留(灰蓝)"
            else:
                status = f"⚠️ 未知颜色{center_rgb}"
            return f"{w}x{h}".ljust(9), f"RGBA{center_pixel}".ljust(22), status
    except Exception as e:
        return "未知".ljust(9), "读取失败".ljust(22), f"⚠️ 错误: {e}"

def run_density_check(apk_path, local_dir, target_rgb=(11, 22, 100)):
    print(f"\n{'='*35} 🛠️ 1. 本地源图片检测 (android_src) {'='*35}")
    if os.path.exists(local_dir):
        for root, _, files in os.walk(local_dir):
            for f in files:
                if f.endswith(('.png', '.jpg', '.jpeg')):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, local_dir)
                    res, rgba, status = get_img_status(full_path, target_rgb)
                    print(f"🏠 [本地] {rel_path.ljust(45)} | 尺寸: {res} | 中心: {rgba} | 状态: {status}")
    else:
        print(f"❌ 未找到本地目录: {local_dir}")

    print(f"\n{'='*35} 📦 2. 编译产物检测 (APK 内部资源) {'='*35}")
    if os.path.exists(apk_path):
        total, matched = 0, 0
        with zipfile.ZipFile(apk_path, 'r') as z:
            for name in z.namelist():
                # 过滤出所有可能包含开屏、背景、图标的 res 资源
                if name.endswith('.png') and ('res/drawable' in name or 'res/mipmap' in name):
                    with z.open(name) as f:
                        res, rgba, status = get_img_status(f, target_rgb)
                        total += 1
                        if "✅" in status: matched += 1
                        print(f"🤖 [APK ] {name.ljust(45)} | 尺寸: {res} | 中心: {rgba} | 状态: {status}")
        print(f"\n📊 报告结论：扫描到 APK 相关图片 {total} 张，成功替换目标色 {matched} 张 (达成率: {matched}/{total})")
    else:
        print(f"❌ 未找到待测 APK 文件: {apk_path}，请先执行 buildozer android debug 编译。")
    print('='*100)

# 执行双向高密度检测
run_density_check(
    apk_path="bin/hualing-0.1-arm64-v8a-debug.apk", 
    local_dir="/workspaces/kivy/android_src", 
    target_rgb=(11, 22, 100)
)