"""生成构建元数据：dist/BUILD-INFO.txt 与 dist/SHA256SUMS。

用法：
    python tools/build_info.py [exe路径]

不传 exe 时自动在 dist/ 下找最新的 DufsGui*.exe。
SHA256SUMS 使用 sha256sum 兼容格式（`<hash>  <相对仓库根的路径>`）；
除产物本身外，其余条目都是被打进 exe 的构建输入（dufs、皮肤、许可证等），
用于回答"这个产物由哪份输入构建"，不是独立分发的文件。
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _cmd(*args: str) -> str:
    try:
        out = subprocess.check_output(
            args, cwd=str(ROOT), stderr=subprocess.DEVNULL, text=True
        )
        return out.strip()
    except Exception:  # noqa: BLE001
        return ""


def _git_state() -> str:
    commit = _cmd("git", "rev-parse", "--short", "HEAD") or "(未知)"
    dirty = _cmd("git", "status", "--porcelain")
    return f"{commit}（工作区{'有未提交改动' if dirty else '干净'}）"


def _pyinstaller_version() -> str:
    try:
        import PyInstaller

        return PyInstaller.__version__
    except Exception:  # noqa: BLE001
        return "(未安装)"


def _tk_version() -> str:
    try:
        import tkinter

        return str(tkinter.TkVersion)
    except Exception:  # noqa: BLE001
        return "(不可用)"


def _app_version() -> str:
    sys.path.insert(0, str(ROOT))
    try:
        from core import APP_VERSION

        return APP_VERSION
    except Exception:  # noqa: BLE001
        return "(未知)"


def _pinned_dufs() -> tuple[str, str]:
    try:
        data = json.loads((ROOT / "tools" / "dufs_checksums.json").read_text(encoding="utf-8"))
        version = str(data.get("pinned_version", "(未知)"))
        digest = str(data.get("assets", {}).get("win64", {}).get("sha256", ""))
        return version, digest
    except Exception:  # noqa: BLE001
        return "(未知)", ""


def _assets_version() -> str:
    try:
        return (ROOT / "assets" / "ASSETS_VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "(未知)"


def find_exe() -> Path:
    if not DIST.is_dir():
        raise SystemExit("[X] dist/ 不存在，请先打包")
    found = sorted(DIST.glob("DufsGui*.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not found:
        raise SystemExit("[X] dist/ 下没有 DufsGui*.exe")
    return found[0]


def key_files(exe: Path) -> list[Path]:
    """产物 + 打进产物的关键输入（存在才收录）。"""
    out: list[Path] = [exe]
    for name in ("bin/dufs.exe", "requirements.txt", "DufsGui.spec",
                 "tools/dufs_checksums.json", "tools/skin_checksums.json"):
        p = ROOT / name
        if p.is_file():
            out.append(p)
    for name in ("assets", "licenses"):
        d = ROOT / name
        if d.is_dir():
            out += sorted((p for p in d.rglob("*") if p.is_file()), key=lambda p: rel(p))
    return out


def write_metadata(exe: Path, out_dir: Path | None = None) -> tuple[Path, Path]:
    exe = exe.resolve()
    if not exe.is_file():
        raise SystemExit(f"[X] 产物不存在：{exe}")
    out = out_dir or (DIST if DIST.is_dir() else exe.parent)
    out.mkdir(parents=True, exist_ok=True)

    dufs_version, dufs_digest = _pinned_dufs()
    size = exe.stat().st_size
    exe_digest = sha256_file(exe)
    mode = "onefile" if exe.parent.resolve() == DIST.resolve() else "onedir"
    actual_dufs = ROOT / "bin" / "dufs.exe"

    info = "\n".join([
        "Dufs GUI 构建信息",
        f"生成时间        : {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"应用版本        : v{_app_version()}",
        f"Git 状态        : {_git_state()}",
        f"Python          : {sys.version.split()[0]} ({platform.architecture()[0]})",
        f"Python 路径     : {sys.executable}",
        f"PyInstaller     : {_pyinstaller_version()}",
        f"Tk              : {_tk_version()}",
        f"操作系统        : {platform.platform()}",
        f"打包模式        : {mode}",
        f"产物            : {rel(exe)}",
        f"产物大小        : {size} 字节",
        f"产物 SHA256     : {exe_digest}",
        f"内置 dufs 版本  : {dufs_version}",
        f"内置 dufs 文件  : {rel(actual_dufs) if actual_dufs.is_file() else '(未找到 bin/dufs.exe)'}",
        f"内置 dufs SHA256: {sha256_file(actual_dufs) if actual_dufs.is_file() else '(无)'}",
        f"官方清单 SHA256 : {dufs_digest or '(无)'}",
        f"网页皮肤版本    : {_assets_version()}",
        "",
        "说明：SHA256SUMS 中除产物外，其余条目都是打进 exe 的构建输入",
        "（dufs / 皮肤 / 许可证 / 打包配置等），用于审计产物来源，",
        "它们不会作为独立文件分发。",
        "校验：在仓库根目录执行 `sha256sum -c dist/SHA256SUMS`；",
        "Windows 可用 `Get-FileHash <文件> -Algorithm SHA256`。",
        "",
    ])
    info_path = out / "BUILD-INFO.txt"
    info_path.write_text(info, encoding="utf-8")

    lines = [f"{sha256_file(p)}  {rel(p)}" for p in key_files(exe)]
    sums_path = out / "SHA256SUMS"
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return info_path, sums_path


def main() -> int:
    arg = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    exe = Path(arg) if arg else find_exe()
    info_path, sums_path = write_metadata(exe)
    print(f"[ok] {rel(info_path)}")
    print(f"[ok] {rel(sums_path)}（{len(key_files(exe.resolve()))} 个文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
