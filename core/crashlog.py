"""崩溃兜底：把 --noconsole 模式下看不见的异常落盘。

为什么需要：PyInstaller 打出的 GUI exe 用 --console=False 时，
stderr 和 traceback 完全丢失，任何未捕获异常都表现为"双击闪退"。
这里把异常写进 crash.log，并尽力弹窗提示。

用法：在入口最前面调用 install()，越早越好。
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from .dufsbin import resource_dir, verify_assets_dir, webui_dir

MAX_POPUP = 900


def log_dir() -> Path:
    """与业务配置同目录，保证有写权限（exe 放 Program Files 也能写）。"""
    base = os.environ.get("DUFS_GUI_HOME")
    if base:
        return Path(base)
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return root / "DufsGui"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DufsGui"
    return Path.home() / ".local" / "share" / "dufs-gui"


def log_path() -> Path:
    return log_dir() / "crash.log"


def write_report(title: str, text: str) -> Path:
    """追加一条记录，返回日志路径（写失败也不再抛）。"""
    p = log_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        frozen = "frozen" if getattr(sys, "frozen", False) else "source"
        with p.open("a", encoding="utf-8") as f:
            f.write(f"\n===== {stamp} [{frozen}] py{sys.version.split()[0]} =====\n")
            f.write(f"{title}\n{text}\n")
            f.write(f"---- 环境 ----\n{env_report()}\n")
    except OSError:
        pass
    return p


def _format(exc_type, exc_value, exc_tb) -> str:
    return "".join(traceback.format_exception(exc_type, exc_value, exc_tb)).strip()


def _popup(title: str, text: str, path: Path) -> None:
    """尽力弹窗。Tk 起不来或没有显示环境就静默放弃。"""
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, f"{text[:MAX_POPUP]}\n\n完整日志：\n{path}")
        try:
            root.destroy()
        except Exception:
            pass
    except Exception:
        pass


def install(popup: bool = True) -> None:
    """接管 sys.excepthook 与线程异常。"""

    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        text = _format(exc_type, exc_value, exc_tb)
        p = write_report("未捕获异常", text)
        try:
            sys.stderr.write(text + "\n")
        except Exception:
            pass
        if popup:
            _popup("Dufs GUI 出错了", text, p)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = hook

    try:
        import threading

        def thread_hook(args):
            text = _format(args.exc_type, args.exc_value, args.exc_traceback)
            p = write_report(f"线程异常：{getattr(args.thread, 'name', '?')}", text)
            if popup:
                _popup("Dufs GUI 后台线程出错", text, p)

        threading.excepthook = thread_hook
    except Exception:
        pass


def _skin_files(d) -> str:
    """列出皮肤目录内的文件，自检时用来确认打包是否完整。"""
    try:
        if not d or not d.is_dir():
            return "(无)"
        return ", ".join(sorted(f.name for f in d.iterdir() if f.is_file())) or "(空)"
    except OSError as e:
        return f"(读取失败 {e})"


def env_report() -> str:
    """环境快照，用于排错：frozen 状态、_MEIPASS、可执行文件位置、Tcl/Tk 情况。"""
    lines = [
        f"frozen      : {getattr(sys, 'frozen', False)}",
        f"_MEIPASS    : {getattr(sys, '_MEIPASS', '(none)')}",
        f"webui_dir   : {webui_dir()}",
        f"resource_dir: {resource_dir()}",
        f"验证结果    : {verify_assets_dir(webui_dir())[1]}",
        f"目录内容    : {_skin_files(webui_dir())}",
        f"executable  : {sys.executable}",
        f"argv0       : {sys.argv[0] if sys.argv else '(none)'}",
        f"cwd         : {os.getcwd()}",
        f"python      : {sys.version.split()[0]}",
    ]
    try:
        import tkinter

        lines.append(f"tkinter     : {tkinter.TkVersion}")
    except Exception as e:
        lines.append(f"tkinter     : 导入失败 -> {type(e).__name__}: {e}")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for sub in ("tcl", "tk", "_tk_data"):
            d = Path(meipass) / sub
            lines.append(f"{sub:<11}: {'存在' if d.exists() else '缺失'} ({d})")
    return "\n".join(lines)
