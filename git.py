import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse


def kill_process_tree(pid: int):
    """Windows 下递归杀死进程树"""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def looks_like_url(s: str) -> bool:
    """判断是否为 Git 远程地址"""
    return s.startswith("https://") or s.startswith("git@") or "://" in s


def parse_url_info(url: str):
    """从 URL 中提取 remote_url、auth、repo 路径"""
    parsed = urlparse(url)
    auth = None
    if "@" in parsed.netloc:
        auth, host = parsed.netloc.split("@", 1)
        remote_url = urlunparse(parsed._replace(netloc=f"{auth}@{host}"))
    else:
        remote_url = url
    repo_path = parsed.path.lstrip("/")
    return remote_url, auth, repo_path


def parse_size_str(val: str) -> int:
    """解析如 100mb, 50m, 1g, 104857600 等字符串为字节数，默认 100MB"""
    if not val:
        return 104857600
    s = str(val).strip().lower()

    multiplier = 1
    if s.endswith("gb") or s.endswith("g"):
        multiplier = 1024 * 1024 * 1024
        s = s.rstrip("gb").rstrip("g")
    elif s.endswith("mb") or s.endswith("m"):
        multiplier = 1024 * 1024
        s = s.rstrip("mb").rstrip("m")
    elif s.endswith("kb") or s.endswith("k"):
        multiplier = 1024
        s = s.rstrip("kb").rstrip("k")
    elif s.endswith("b"):
        s = s.rstrip("b")

    try:
        return int(float(s) * multiplier)
    except ValueError:
        return 104857600


def preprocess_args():
    """
    预处理参数，支持格式：
    1. git.py <URL> [push|pull|init|list-big|remove-big] ...
    2. git.py [list-big|remove-big|pull|push] ...
    """
    new_argv = [sys.argv[0]]
    remaining = sys.argv[1:]

    if not remaining:
        return new_argv

    first = remaining[0]
    if looks_like_url(first):
        remote_url, auth, repo_path = parse_url_info(first)
        new_argv.extend(["--remote", remote_url])
        if auth:
            new_argv.extend(["--auth", auth])
        remaining = remaining[1:]

        mode = None
        commit_msg = None
        if remaining:
            maybe_mode = remaining[0]
            if maybe_mode in ("push", "pull", "init", "list-big", "listbig", "remove-big", "filter-repo"):
                mode = maybe_mode
                remaining = remaining[1:]
                if mode == "push" and remaining and not remaining[0].startswith("-"):
                    commit_msg = remaining[0]
                    remaining = remaining[1:]
            else:
                mode = "push"
                commit_msg = maybe_mode
                remaining = remaining[1:]
        else:
            mode = "push"

        new_argv.append(mode)
        if commit_msg:
            new_argv.extend(["--commit-msg", commit_msg])
        new_argv.extend(remaining)
        return new_argv

    return sys.argv


def find_git(user_git: str) -> str:
    """查找 git 可执行文件（用户指定 > GIT_PATH > 系统 PATH）"""
    if user_git and Path(user_git).is_file():
        return user_git
    env_git = os.environ.get("GIT_PATH", "")
    if env_git and Path(env_git).is_file():
        return env_git
    sys_git = shutil.which("git")
    if sys_git:
        return sys_git
    print("[FATAL] 无法找到 git 可执行文件。请设置 GIT_PATH 或确保 git 在 PATH 中。")
    sys.exit(1)


def get_origin_url(git_bin: str) -> str:
    """尝试获取当前仓库配置的 origin 地址"""
    try:
        res = subprocess.run([git_bin, "remote", "get-url", "origin"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def run_shell(git_bin: str, args: list[str], realtime: bool = False) -> subprocess.CompletedProcess:
    """执行命令（自动补全 PortableGit 环境）"""
    cmd = [git_bin] + args
    git_exe_path = Path(git_bin).resolve()
    git_bin_dir = git_exe_path.parent
    git_root = git_bin_dir.parent

    # PortableGit 环境补全（仅影响 Windows）
    portable_paths = [
        str(git_root / "cmd"),
        str(git_bin_dir),
        str(git_root / "mingw64" / "bin"),
        str(git_root / "usr" / "bin"),
    ]
    env = os.environ.copy()
    env["NoDefaultCurrentDirectoryInExePath"] = "1"
    valid_paths = [p for p in portable_paths if os.path.exists(p)]
    env["PATH"] = os.pathsep.join(valid_paths) + os.pathsep + env.get("PATH", "")

    print(f"\n[RUN] {' '.join(cmd)}")

    proc = None
    try:
        if realtime:
            proc = subprocess.Popen(cmd, env=env)
            retcode = proc.wait()
            return subprocess.CompletedProcess(cmd, retcode)
        else:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            stdout, stderr = proc.communicate()
            if stdout and stdout.strip():
                print(f"[STDOUT]\n{stdout}")
            if stderr and stderr.strip():
                print(f"[STDERR]\n{stderr}")
            print(f"[RETURN CODE] {proc.returncode}")
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)

    except KeyboardInterrupt:
        print("\n\n[CANCEL] 收到中断信号，正在清理 Git 进程树...")
        if proc and proc.poll() is None:
            kill_process_tree(proc.pid)
        print("[CANCEL] 所有相关进程已终止。")
        sys.exit(130)
    except Exception as e:
        print(f"[FATAL] 执行异常: {repr(e)}")
        raise


def check_lfs_available(git_bin: str) -> bool:
    """检查 git-lfs 是否已安装并可执行"""
    res = run_shell(git_bin, ["lfs", "version"], realtime=False)
    return res.returncode == 0


def install_lfs() -> bool:
    """尝试自动安装 Git LFS（跨平台）"""
    system = platform.system()
    print("\n[INFO] 检测到大文件，但未找到 Git LFS，尝试自动安装...")

    if system == "Linux":
        for cmd in [
            ["sudo", "apt-get", "install", "-y", "git-lfs"],
            ["sudo", "yum", "install", "-y", "git-lfs"],
            ["sudo", "dnf", "install", "-y", "git-lfs"],
            ["sudo", "zypper", "install", "-y", "git-lfs"],
        ]:
            if shutil.which(cmd[0]):
                print(f"[INSTALL] 尝试: {' '.join(cmd)}")
                try:
                    subprocess.run(cmd, check=True)
                    return True
                except subprocess.CalledProcessError:
                    print(f"[WARN] 安装命令失败: {cmd}")
        print("[FATAL] 无法自动安装 git-lfs，请手动安装后重试。")
        return False

    elif system == "Darwin":
        if shutil.which("brew"):
            print("[INSTALL] 尝试: brew install git-lfs")
            try:
                subprocess.run(["brew", "install", "git-lfs"], check=True)
                return True
            except subprocess.CalledProcessError:
                print("[FATAL] Homebrew 安装 git-lfs 失败。")
                return False
        else:
            print("[FATAL] 未找到 Homebrew，请手动安装 git-lfs。")
            return False

    elif system == "Windows":
        print("[FATAL] Windows 请手动下载安装 Git LFS: https://git-lfs.com/")
        return False

    else:
        print(f"[FATAL] 不支持的操作系统: {system}，请手动安装 git-lfs。")
        return False


def init_lfs(git_bin: str) -> bool:
    """初始化 Git LFS（必须已安装）"""
    print("\n[INFO] 执行 git lfs install")
    res = run_shell(git_bin, ["lfs", "install"])
    if res.returncode != 0:
        print("[FATAL] Git LFS 初始化失败！")
        return False
    print("[INFO] Git LFS 就绪")
    return True


def set_remote(git_bin: str, remote_url: str):
    """设置 origin 远程地址"""
    if remote_url:
        run_shell(git_bin, ["remote", "set-url", "origin", remote_url])


def scan_large_files(repo_root: Path, threshold: int) -> set[str]:
    """扫描超过阈值的文件，返回相对路径集合"""
    large_files = set()
    skip_dirs = {".git", "build", "dist", "__pycache__"}
    for path in repo_root.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            fsize = path.stat().st_size
        except OSError:
            continue
        if fsize >= threshold:
            rel = str(path.relative_to(repo_root)).replace("\\", "/")
            large_files.add(rel)
    return large_files


def clean_and_apply_lfs(git_bin: str, repo_root: Path, large_patterns: set[str]):
    """更新 .gitattributes 以包含 LFS 规则"""
    attr_path = repo_root / ".gitattributes"
    other_lines = []
    lfs_lines = set()

    if attr_path.exists():
        with open(attr_path, "r", encoding="utf-8") as f:
            for line in f.readlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if "filter=lfs" in stripped:
                    lfs_lines.add(stripped)
                else:
                    other_lines.append(stripped)

    for pat in large_patterns:
        rule = f"{pat} filter=lfs diff=lfs merge=lfs -text"
        lfs_lines.add(rule)

    all_rules = other_lines + sorted(lfs_lines)
    if all_rules:
        with open(attr_path, "w", encoding="utf-8") as f:
            f.write("\n".join(all_rules) + "\n")
    print(f"\n[INFO] .gitattributes 更新完成，LFS追踪总数: {len(lfs_lines)}")


def git_pull(git_bin: str, branch: str, extra_args: list[str]):
    """执行 pull + lfs pull"""
    print("\n===== 执行 git pull origin " + branch + " =====")
    cmd_args = ["pull", "--progress"] + extra_args + ["origin", branch]
    res = run_shell(git_bin, cmd_args, realtime=True)
    if res.returncode != 0:
        print("[ERROR] git pull 失败！")
        sys.exit(1)
    print("\n===== 执行 git lfs pull =====")
    run_shell(git_bin, ["lfs", "pull"], realtime=True)


def git_push(git_bin: str, branch: str, repo_root: Path, extra_args: list[str], commit_msg: str = "auto update"):
    """暂存、提交、推送"""
    run_shell(git_bin, ["add", "-A"])
    diff_check = run_shell(git_bin, ["diff", "--cached", "--quiet"])
    if diff_check.returncode == 0:
        print("\n[INFO] 无变更，跳过 commit，直接推送")
    else:
        run_shell(git_bin, ["commit", "-m", commit_msg])

    print(f"\n===== 推送 origin {branch} =====")
    cmd_args = ["push", "-v", "--progress"] + extra_args + ["origin", branch]
    push_res = run_shell(git_bin, cmd_args, realtime=True)
    if push_res.returncode != 0:
        print("[ERROR] git push 失败！")
        sys.exit(1)


def git_list_big(git_bin: str, threshold_bytes: int) -> list[tuple[int, str, str]]:
    """扫描 Git 历史记录中的大文件，返回 [(size_bytes, path, blob_hash), ...]"""
    print(f"\n===== 扫描历史记录中 >= {threshold_bytes/1024/1024:.2f} MB ({threshold_bytes} 字节) 的大文件 =====")
    try:
        p1 = subprocess.Popen([git_bin, "rev-list", "--objects", "--all"], stdout=subprocess.PIPE, text=True)
        p2 = subprocess.Popen([git_bin, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize) %(rest)"],
                              stdin=p1.stdout, stdout=subprocess.PIPE, text=True)
        p1.stdout.close()
        output, _ = p2.communicate()

        large_files = []
        for line in output.splitlines():
            parts = line.split(" ", 3)
            if len(parts) >= 4 and parts[1] == "blob":
                size = int(parts[2])
                if size >= threshold_bytes:
                    large_files.append((size, parts[3], parts[0]))

        large_files.sort(key=lambda x: x[0], reverse=True)

        if not large_files:
            print("🎉 历史记录中未发现超过设定的文件。")
        else:
            print(f"{'大小 (MB)':<12} | {'Blob Hash':<40} | {'文件路径'}")
            print("-" * 85)
            for size, path, blob_hash in large_files:
                print(f"{size/1024/1024:<12.2f} | {blob_hash:<40} | {path}")

        return large_files

    except Exception as e:
        print(f"[ERROR] 获取历史记录大文件失败: {e}")
        return []


def git_remove_big(git_bin: str, threshold_bytes: int, target_hashes: list[str] = None):
    """使用 git filter-repo 按 blob-hash 精度清理历史大文件"""
    print(f"\n===== 准备清理历史大文件 =====")

    check_cmd = run_shell(git_bin, ["filter-repo", "--version"], realtime=False)
    if check_cmd.returncode != 0:
        print("\n[ERROR] 未检测到 git-filter-repo 工具。")
        print("💡 请先在终端运行安装：pip install git-filter-repo")
        sys.exit(1)

    hashes_to_remove = set()

    if target_hashes:
        for h in target_hashes:
            cleaned = h.strip()
            if cleaned:
                hashes_to_remove.add(cleaned)
        print(f"[INFO] 使用指定的 {len(hashes_to_remove)} 个 Blob Hash 进行精准删除。")
    else:
        large_files = git_list_big(git_bin, threshold_bytes)
        if not large_files:
            print("[INFO] 没有找到符合条件的大文件，无需清理。")
            return

        for _, _, blob_hash in large_files:
            hashes_to_remove.add(blob_hash)

    if not hashes_to_remove:
        print("[INFO] 没有待清理的 Blob Hash，操作已取消。")
        return

    print(f"\n[ACTION] 即将按 Blob Hash 精准擦除以下 {len(hashes_to_remove)} 个数据节点:")
    for h in sorted(hashes_to_remove):
        print(f"  - Blob Hash: {h}")

    hash_list_code = ", ".join([f'b"{h}"' for h in hashes_to_remove])
    callback_code = (
        f"target_hashes = {{{hash_list_code}}}\n"
        f"if blob.original_id in target_hashes:\n"
        f"    blob.skip()"
    )

    cmd_args = ["filter-repo", "--blob-callback", callback_code, "--force"]
    res = run_shell(git_bin, cmd_args, realtime=True)

    if res.returncode == 0:
        print("\n[INFO] 历史大文件 Blob 已成功擦除！")
        print("⚠️  注意：历史记录已被重写，推送时需使用强制推送 (git push origin master --force)。")
    else:
        print("[ERROR] 清理失败！")
        sys.exit(1)


def main():
    sys.argv = preprocess_args()

    default_git = os.environ.get("GIT_PATH", "git")
    default_branch = os.environ.get("BRANCH", "master")

    parser = argparse.ArgumentParser(description="CQ-editor Git Auto LFS Tool")
    parser.add_argument("--git", default=default_git, help="git 可执行文件路径")
    parser.add_argument("--branch", default=default_branch, help="分支名称")
    parser.add_argument("--size",'-s', default="100mb", help="大文件大小限制（支持 100mb, 50m, 1g 等，默认 100mb）")
    parser.add_argument("--threshold", type=int, default=0, help="（兼容项）字节数阈值")
    parser.add_argument("--hashes", "--hash", default="", help="手动要清理的 Blob Hash（多个用逗号隔开）")
    parser.add_argument("--remote", default="", help="完整远程 URL")
    parser.add_argument("--auth", help="认证信息 user:token")
    parser.add_argument("--commit-msg", default="auto update", help="自定义 commit 消息")
    parser.add_argument("mode", choices=["push", "pull", "init", "list-big", "listbig", "remove-big", "filter-repo"], help="操作模式")

    args, extra = parser.parse_known_args()

    git_exe = find_git(args.git)
    repo_root = Path.cwd()

    # 如果未指定 --remote，则尝试自动获取本地 origin 的 URL
    remote_url = args.remote or get_origin_url(git_exe)

    # 仅在需要推送/拉取/初始化且没有配置远程时才报 FATAL
    if not remote_url and args.mode not in ("list-big", "listbig", "remove-big", "filter-repo"):
        print("[FATAL] 必须提供远程仓库地址（直接传 URL 或通过 --remote）")
        sys.exit(1)

    if args.threshold > 0:
        threshold_bytes = args.threshold
    else:
        threshold_bytes = parse_size_str(args.size)

    print(f"仓库路径: {repo_root.absolute()}")
    print(f"Git程序: {git_exe}")
    if args.mode != "init":
        print(f"文件限制: {threshold_bytes / 1024 / 1024:.2f} MB ({threshold_bytes} 字节)")
    if remote_url:
        print(f"远程地址: {remote_url}")
    print(f"分支: {args.branch}")

    try:
        if args.mode == "init":
            print("\n===== 执行 git init =====")
            run_shell(git_exe, ["init"])
            run_shell(git_exe, ["remote", "remove", "origin"])
            run_shell(git_exe, ["remote", "add", "origin", remote_url])
            print("\n✅ 初始化完成！")
            return

        if args.mode in ("list-big", "listbig"):
            git_list_big(git_exe, threshold_bytes)
            return

        if args.mode in ("remove-big", "filter-repo"):
            target_hashes = [h.strip() for h in args.hashes.split(",") if h.strip()] if args.hashes else None
            git_remove_big(git_exe, threshold_bytes, target_hashes=target_hashes)
            if remote_url:
                set_remote(git_exe, remote_url)
                print("\n✅ 远程地址已重新绑定。")
            return

        large_files = scan_large_files(repo_root, threshold_bytes)
        has_large = len(large_files) > 0
        print(f"\n[INFO] 扫描到 {len(large_files)} 个本地超过阈值的文件")

        lfs_needed = has_large
        lfs_available = check_lfs_available(git_exe)

        if lfs_needed and not lfs_available:
            if not install_lfs():
                sys.exit(1)
            if not check_lfs_available(git_exe):
                print("[FATAL] Git LFS 安装后仍然不可用，请检查环境。")
                sys.exit(1)
            lfs_available = True

        if lfs_needed or lfs_available:
            if not init_lfs(git_exe):
                sys.exit(1)

        if lfs_needed:
            clean_and_apply_lfs(git_exe, repo_root, large_files)

        if remote_url:
            set_remote(git_exe, remote_url)

        if args.mode == "pull":
            git_pull(git_exe, args.branch, extra)
        elif args.mode == "push":
            git_push(git_exe, args.branch, repo_root, extra, args.commit_msg)

        print("\n✅ 操作完成！")
    except KeyboardInterrupt:
        print("\n[CANCEL] 用户手动终止程序。")
        sys.exit(130)


if __name__ == "__main__":
    main()