"""dufs 可执行文件的定位与释放（支持 PyInstaller 内置打包）。"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

BINARY_NAME = "dufs.exe" if os.name == "nt" else "dufs"


def app_data_dir() -> Path:
    """用户数据目录：放置释放出来的 dufs 与配置文件。"""
    base = os.environ.get("DUFS_GUI_HOME")
    if base:
        return Path(base)
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return root / "DufsGui"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DufsGui"
    return Path.home() / ".local" / "share" / "dufs-gui"


def resource_dir() -> Path:
    """打包后的临时资源目录，或开发模式下的项目根目录。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def is_executable(path: Path) -> bool:
    return path.is_file() and (os.name == "nt" or os.access(path, os.X_OK))


def webui_dir() -> Path | None:
    """内置界面皮肤目录。

    关键：**必须含 index.html**。dufs 在启动时就硬性校验这一点：

        fn sanitize_assets_path(path) -> Result {
            let path = Self::sanitize_path(path)?;
            if !path.join("index.html").exists() {
                bail!("Path {} doesn't contains index.html", path.display());
            }
            Ok(path)
        }

    也就是说"缺的文件运行时回退内置"只对 index.css / index.js / favicon.ico 成立，
    index.html 不存在会直接 bail 退出——只放 CSS 是启动不了 dufs 的。
    """
    for d in (resource_dir() / "webui", resource_dir() / "assets"):
        if (d / "index.html").is_file():
            return d
    return None


def validate_assets_dir(path: str) -> tuple[bool, str]:
    """检查外部皮肤目录能否安全用于 --assets，返回 (可用, 说明)。"""
    p = (path or "").strip()
    if not p:
        return True, ""
    d = Path(p)
    if not d.exists():
        return False, f"目录不存在：{p}"
    if not d.is_dir():
        return False, f"不是目录：{p}"
    if not (d / "index.html").is_file():
        return False, f"缺少 index.html（dufs 要求必须有）：{p}"
    return True, ""


def _extract_embedded() -> Path | None:
    """若 core/dufs_embedded.py 存在（由 tools/embed_dufs.py 生成），释放其中的二进制。"""
    target = app_data_dir() / "bin" / BINARY_NAME
    try:
        import importlib

        importlib.invalidate_caches()
        from . import dufs_embedded  # type: ignore[attr-defined]
    except ImportError:
        return None
    try:
        import base64

        data = base64.b64decode("".join(dufs_embedded.DATA))
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        if os.name != "nt":
            tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp, target)
        return target
    except (OSError, ValueError, AttributeError):
        return None


def find_dufs() -> Path | None:
    """按优先级查找可用的 dufs。

    顺序：环境变量显式覆盖 > 内置资源 > 已落盘的用户副本 > PATH > 内嵌数据。
    把内置资源放在已落盘副本之前，是为了让升级 GUI 后随包的新版 dufs 能覆盖旧副本。
    """
    candidates: list[Path] = []

    env_path = os.environ.get("DUFS_BIN")
    if env_path:
        candidates.append(Path(env_path))

    res = resource_dir()
    candidates += [res / "bin" / BINARY_NAME, res / BINARY_NAME]
    candidates.append(app_data_dir() / "bin" / BINARY_NAME)

    for c in candidates:
        if is_executable(c):
            return c

    which = shutil.which("dufs")
    if which:
        return Path(which)

    return _extract_embedded()


def ensure_dufs() -> Path | None:
    """把找到的 dufs 落到用户数据目录，避免每次启动都从临时目录解压。

    内置版本比已落盘版本更新时（大小或 mtime 不同）会覆盖，便于升级 GUI 后同步升级 dufs。
    """
    found = find_dufs()
    if found is None:
        return None
    target = app_data_dir() / "bin" / BINARY_NAME
    try:
        if found.resolve() == target.resolve():
            return found
    except OSError:
        pass

    if is_executable(target) and _same_version(found, target):
        return target

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(found, target)
        if os.name != "nt":
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return target
    except OSError:
        return found


def _same_version(a: Path, b: Path) -> bool:
    """简单判断两个 dufs 是否为同一份：大小一致且 mtime 相差不超过 2 秒。"""
    try:
        sa, sb = a.stat(), b.stat()
    except OSError:
        return False
    return sa.st_size == sb.st_size and abs(sa.st_mtime - sb.st_mtime) < 2


def install_custom(path: str | os.PathLike) -> Path:
    """用户手动指定 dufs.exe，复制到用户数据目录以便长期使用。"""
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"文件不存在：{src}")
    target = app_data_dir() / "bin" / BINARY_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return target


def version(binary: Path) -> str:
    """读取 dufs 版本号，失败时返回空串。"""
    try:
        out = subprocess.run([str(binary), "--version"], capture_output=True,
                             text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""
