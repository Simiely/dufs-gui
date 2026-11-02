"""下载 dufs 官方二进制到 bin/ 目录（内置打包前先跑这个）。

用法：
    python tools/fetch_dufs.py                 # 自动识别当前平台与最新版本
    python tools/fetch_dufs.py --version v0.47.0
    python tools/fetch_dufs.py --target win64  # 交叉下载：win64 / linux64 / mac-arm64 / mac-x64
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "sigoden/dufs"
UA = {"User-Agent": "dufs-gui-fetcher"}

# 直连 + 常见 GitHub 加速镜像，逐个尝试直到拿到真压缩包
MIRRORS = [
    "",
    "https://ghfast.top/",
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://mirror.ghproxy.com/",
]

DOWNLOAD_HELP = """
[!] 所有下载源都失败了。请手动下载：

    1. 打开 https://github.com/sigoden/dufs/releases
    2. 找到最新的 Windows 资产：dufs-vX.Y.Z-x86_64-pc-windows-msvc.zip
    3. 解压得到 dufs.exe，放到本项目的 bin\\ 目录

放好之后重新运行 build.bat 即可（它会跳过下载）。
也可以先启动软件，在「高级设置 → dufs 程序 → 更换…」里手动指定。
"""

TARGETS = {
    "win64": ("x86_64-pc-windows-msvc", "zip", "dufs.exe"),
    "win-arm64": ("aarch64-pc-windows-msvc", "zip", "dufs.exe"),
    "linux64": ("x86_64-unknown-linux-musl", "tar.gz", "dufs"),
    "linux-arm64": ("aarch64-unknown-linux-musl", "tar.gz", "dufs"),
    "mac-x64": ("x86_64-apple-darwin", "tar.gz", "dufs"),
    "mac-arm64": ("aarch64-apple-darwin", "tar.gz", "dufs"),
}


def detect_target() -> str:
    if os.name == "nt":
        return "win-arm64" if "ARM" in os.environ.get("PROCESSOR_ARCHITECTURE", "") else "win64"
    if sys.platform == "darwin":
        return "mac-arm64" if os.uname().machine in ("arm64", "aarch64") else "mac-x64"
    return "linux-arm64" if os.uname().machine in ("arm64", "aarch64") else "linux64"


def latest_version() -> str:
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    for prefix in MIRRORS:
        try:
            with urllib.request.urlopen(urllib.request.Request(prefix + url, headers=UA),
                                        timeout=20) as r:
                return json.load(r)["tag_name"]
        except Exception:
            continue
    # API 全不通时，抓 releases 页面找版本号
    for prefix in MIRRORS:
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(prefix + f"https://github.com/{REPO}/releases/latest",
                                           headers=UA), timeout=20) as r:
                html = r.read().decode("utf-8", "ignore")
            m = re.search(rf"/{re.escape(REPO)}/releases/tag/(v?[0-9][0-9.]*)", html)
            if m:
                return m.group(1)
        except Exception:
            continue
    raise SystemExit(DOWNLOAD_HELP)


def download(version: str, target: str, out_dir: Path) -> Path:
    triple, ext, exe = TARGETS[target]
    name = f"dufs-{version}-{triple}.{ext}"
    url = f"https://github.com/{REPO}/releases/download/{version}/{name}"

    data = None
    for prefix in MIRRORS:
        try:
            print(f"尝试 {prefix}{url}" if prefix else f"下载 {url}")
            with urllib.request.urlopen(urllib.request.Request(prefix + url, headers=UA),
                                        timeout=90) as r:
                raw = r.read()
            if raw[:2] == b"PK" or raw[:2] == b"\x1f\x8b":
                data = raw
                break
            print("  返回内容不像压缩包，换下一个源")
        except Exception as e:
            print(f"  失败：{type(e).__name__}")
    if data is None:
        raise SystemExit(DOWNLOAD_HELP)

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / ("dufs.exe" if exe.endswith(".exe") else "dufs")

    if ext == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(n for n in z.namelist() if n.endswith("dufs.exe"))
            with z.open(member) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
    else:
        with tempfile.TemporaryDirectory() as td:
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                member = next(m for m in t.getmembers() if m.name.endswith("/dufs")
                              or m.name == "dufs")
                t.extract(member, td)
                shutil.copy2(Path(td) / member.name, dest)

    if os.name != "nt":
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"已保存到 {dest}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="", help="版本号，如 v0.47.0")
    ap.add_argument("--target", default="", choices=list(TARGETS), help="目标平台")
    ap.add_argument("--out", default="", help="输出目录，默认项目 bin/")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out) if args.out else root / "bin"
    target = args.target or detect_target()
    version = args.version or latest_version()
    print(f"目标平台 {target}，版本 {version}")
    download(version, target, out_dir)


if __name__ == "__main__":
    main()
