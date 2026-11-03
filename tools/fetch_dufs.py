"""下载 dufs 官方二进制到 bin/ 目录（内置打包前先跑这个）。

版本固定在校验和清单里（tools/dufs_checksums.json），**不再自动拉取 latest**：
自动追最新会让"构建输入"随上游发布时间漂移，无法复现，也无法提前校验哈希。

每个下载源都要通过 SHA256 比对；哈希不符立即失败且不会静默换源。
清单里的哈希优先来自 GitHub Releases API 的官方 digest。若某来源哈希为空，
首次下载会按 TOFU 记录并写回清单 —— 该策略只能发现"下载后被替换"，
不能证明首次下载未被投毒，不等于上游签名。

用法：
    python tools/fetch_dufs.py                 # 使用清单中固定的版本
    python tools/fetch_dufs.py --target win64  # 交叉下载：win64 / linux64 / mac-arm64 / mac-x64
"""

from __future__ import annotations

import argparse
import io
import os
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _integrity  # noqa: E402

REPO = "sigoden/dufs"
UA = {"User-Agent": "dufs-gui-fetcher"}
CHECKSUMS = Path(__file__).resolve().parent / "dufs_checksums.json"

# 直连 + 常见 GitHub 加速镜像，逐个尝试直到拿到内容。
# 源的名字必须与校验和清单里的 sources 键严格对应：新增镜像时必须同步补哈希，
# 否则会被拒绝（避免"新加的镜像天然免检"）。
MIRRORS = [
    ("github", ""),
    ("ghfast.top", "https://ghfast.top/"),
    ("gh-proxy.com", "https://gh-proxy.com/"),
    ("ghproxy.net", "https://ghproxy.net/"),
    ("mirror.ghproxy.com", "https://mirror.ghproxy.com/"),
]

DOWNLOAD_HELP = """
[!] 所有下载源都失败了。请手动下载：

    1. 打开 https://github.com/sigoden/dufs/releases
    2. 找到固定版本的 Windows 资产：dufs-vX.Y.Z-x86_64-pc-windows-msvc.zip
    3. 用 tools/dufs_checksums.json 里的 SHA256 校验下载到的压缩包
    4. 解压得到 dufs.exe，放到本项目的 bin\\ 目录

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

#: Python 3.12 起 tarfile 支持 filter 参数；3.9-3.11 用安全回退路径
_TAR_FILTER_SUPPORTED = sys.version_info >= (3, 12)


def detect_target() -> str:
    if os.name == "nt":
        return "win-arm64" if "ARM" in os.environ.get("PROCESSOR_ARCHITECTURE", "") else "win64"
    if sys.platform == "darwin":
        return "mac-arm64" if os.uname().machine in ("arm64", "aarch64") else "mac-x64"
    return "linux-arm64" if os.uname().machine in ("arm64", "aarch64") else "linux64"


def normalize_tag(version: str) -> str:
    v = (version or "").strip()
    return v if v.startswith("v") else "v" + v


def _http_get(url: str, timeout: int = 90) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                timeout=timeout) as r:
        return r.read()


def _member_name_matches(name: str, exe: str) -> bool:
    return name.endswith("/" + exe) or name == exe


def _write_atomic(dest: Path, data: bytes) -> None:
    """先写临时文件再替换，避免半截文件被误当成可用的 dufs。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        tmp.write_bytes(data)
        if os.name != "nt":
            tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _extract_zip(data: bytes, dest: Path, exe: str) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        member = next((n for n in z.namelist() if _member_name_matches(n, exe)), None)
        if member is None:
            raise ValueError(f"压缩包内没有 {exe}")
        with z.open(member) as src:
            _write_atomic(dest, src.read())


def _extract_tar(data: bytes, dest: Path, exe: str) -> None:
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        member = next((m for m in t.getmembers()
                       if m.isfile() and _member_name_matches(m.name, exe)), None)
        if member is None:
            raise ValueError(f"压缩包内没有普通文件 {exe}")
        # 只接受普通文件；路径不得是绝对路径或含 ..（filter="data" 也会拦，
        # 但旧版 Python 没有 filter，必须自己校验）。
        parts = Path(member.name).parts
        if member.name.startswith(("/", "\\")) or ".." in parts:
            raise ValueError(f"压缩包内路径非法：{member.name}")

        if _TAR_FILTER_SUPPORTED:
            with tempfile.TemporaryDirectory() as td:
                t.extract(member, td, filter="data")
                _write_atomic(dest, (Path(td) / member.name).read_bytes())
        else:
            # Python 3.9-3.11 不支持 filter：直接读成员内容，不落盘解包，
            # 同样不会发生路径穿越。
            src = t.extractfile(member)
            if src is None:
                raise ValueError(f"无法读取压缩包成员：{member.name}")
            with src:
                _write_atomic(dest, src.read())


def _extract(data: bytes, ext: str, dest: Path, exe: str) -> None:
    if ext == "zip":
        _extract_zip(data, dest, exe)
    else:
        _extract_tar(data, dest, exe)


def download(version: str, target: str, out_dir: Path,
             doc: dict | None = None, checksums: Path | None = None) -> Path:
    """下载并校验固定版本的 dufs；哈希不符时立即终止，不换源重试。"""
    doc = doc if doc is not None else _integrity.load(CHECKSUMS)
    checksums = checksums or CHECKSUMS

    triple, ext, exe = TARGETS[target]
    name = f"dufs-{version}-{triple}.{ext}"
    url = f"https://github.com/{REPO}/releases/download/{version}/{name}"

    entry = (doc.get("assets") or {}).get(target)
    if not isinstance(entry, dict):
        raise SystemExit(f"校验和清单缺少资产 {target}，拒绝下载：{checksums}")
    if entry.get("filename") != name:
        raise SystemExit(
            f"校验和清单里的文件名与目标不一致：{entry.get('filename')} != {name}\n"
            "请先更新 tools/dufs_checksums.json，不能跳过校验。")

    dest = out_dir / (exe if exe.endswith(".exe") else "dufs")
    data: bytes | None = None

    for source, prefix in MIRRORS:
        print(f"尝试 [{source}] {prefix}{url}" if prefix else f"下载 [{source}] {url}")
        try:
            raw = _http_get(prefix + url)
        except Exception as e:  # noqa: BLE001
            # 网络失败可以换下一个源；这是唯一允许换源的情况，且必须逐条报错
            print(f"  [{source}] 失败：{type(e).__name__}: {e}")
            continue

        expected = _integrity.source_sha256(doc, target, source)
        try:
            digest = _integrity.verify(raw, expected, target, source)
        except _integrity.IntegrityError as e:
            raise SystemExit(f"[X] {e}") from e

        if not expected:
            # 首次信任（TOFU）：先确认内容是能解包的压缩包，再记录哈希
            if raw[:2] not in (b"PK", b"\x1f\x8b"):
                print(f"  [{source}] 返回内容不像压缩包，跳过（未记录校验和）")
                continue
            try:
                _extract(raw, ext, dest, exe)
            except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as e:
                print(f"  [{source}] 内容无法解包：{type(e).__name__}: {e}")
                continue
            _integrity.record(doc, target, source, digest)
            try:
                _integrity.save(checksums, doc)
            except OSError as e:
                raise SystemExit(
                    f"[X] 已下载但无法写回校验和文件：{checksums}（{e}）\n"
                    "下次启动将无法校验，因此中止。") from e
            print(f"[!] TOFU：已记录 {target} / {source} 的 SHA256 {digest}\n"
                  "    该策略只能发现后续下载被替换，不能证明本次下载未被投毒。")
            data = raw
            break

        # 哈希已匹配：内容即官方资产，解包失败属于清单/资产问题，不再换源
        try:
            _extract(raw, ext, dest, exe)
        except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as e:
            raise SystemExit(f"[X] 哈希匹配但解包失败：{type(e).__name__}: {e}") from e
        data = raw
        break

    if data is None:
        raise SystemExit(DOWNLOAD_HELP)

    print(f"已保存到 {dest}（SHA256 校验通过）")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="",
                    help="版本号，如 v0.47.0；省略则使用校验和清单里的固定版本")
    ap.add_argument("--target", default="", choices=list(TARGETS), help="目标平台")
    ap.add_argument("--out", default="", help="输出目录，默认项目 bin/")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out) if args.out else root / "bin"

    try:
        doc = _integrity.load(CHECKSUMS)
    except _integrity.IntegrityError as e:
        raise SystemExit(f"[X] {e}") from e

    pinned = normalize_tag(str(doc.get("pinned_version") or ""))
    if not pinned:
        raise SystemExit(f"[X] 校验和清单缺少 pinned_version：{CHECKSUMS}")
    version = normalize_tag(args.version) if args.version else pinned
    if version != pinned:
        raise SystemExit(
            f"[X] 校验和清单只覆盖 {pinned}，拒绝下载 {version}。\n"
            "    升级 dufs 请先更新 tools/dufs_checksums.json（含官方 SHA256），"
            "不要跳过完整性校验。")

    target = args.target or detect_target()
    print(f"目标平台 {target}，固定版本 {version}")
    download(version, target, out_dir, doc=doc, checksums=CHECKSUMS)


if __name__ == "__main__":
    main()
