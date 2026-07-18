buildozer命令找不到
ctrl+shift+p  rebuild 大概5分钟

下面第一次至少半个小时

buildozer -v android debug 2>&1 | awk 'BEGIN {start=systime()} {now=systime(); printf "[%s][已用时: %ds] %s\n", strftime("%H:%M:%S", now), now-start, $0; fflush()}'



path.write_bytes(get_bmp_bytes(rgb=(255, 0, 128), size=(512, 512)))



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