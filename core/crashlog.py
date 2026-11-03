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


def _has_marker(path, marker: str) -> bool:
    """目录存在且包含指定标志文件，才算真正的 Tcl/Tk 数据目录。"""
    try:
        p = Path(path)
        return p.is_dir() and (p / marker).is_file()
    except OSError:
        return False


def _first_marker_dir(env_name: str, candidates, marker: str) -> Path | None:
    """优先用 PyInstaller 运行时设置的环境变量，再按候选目录查找。

    PyInstaller 6.x 的 pyi_rth__tkinter.py 会把 TCL_LIBRARY / TK_LIBRARY
    指向 _MEIPASS/_tcl_data、_MEIPASS/_tk_data；旧版本可能用 tcl / tk。
    直接读环境变量能同时兼容两种命名，也兼容 onedir 的 _internal 布局。
    """
    env_value = os.environ.get(env_name, "").strip()
    if env_value and _has_marker(env_value, marker):
        return Path(env_value)
    for c in candidates:
        if c and _has_marker(c, marker):
            return Path(c)
    return None


def _source_tcl_candidates() -> list[Path]:
    """源码运行时，Tcl 数据通常在 Python 安装目录的 tcl/ 下。"""
    roots = []
    for base in (getattr(sys, "base_prefix", ""), getattr(sys, "prefix", "")):
        if base:
            roots.append(Path(base))
    out: list[Path] = []
    for root in roots:
        tcl_root = root / "tcl"
        try:
            out += sorted(tcl_root.glob("tcl[0-9]*"))
        except OSError:
            pass
        out.append(tcl_root / "tcl8.6")
    # 最权威的来源：Tcl 解释器自己报告的 library 目录
    try:
        import tkinter

        out.append(Path(tkinter.Tcl().eval("info library")))
    except Exception:  # noqa: BLE001
        pass
    return out


def _source_tk_candidates(tcl_dir: Path | None) -> list[Path]:
    roots = []
    for base in (getattr(sys, "base_prefix", ""), getattr(sys, "prefix", "")):
        if base:
            roots.append(Path(base))
    out: list[Path] = []
    for root in roots:
        tcl_root = root / "tcl"
        try:
            out += sorted(tcl_root.glob("tk[0-9]*"))
        except OSError:
            pass
        out.append(tcl_root / "tk8.6")
    if tcl_dir:
        try:
            out += sorted(tcl_dir.parent.glob("tk[0-9]*"))
        except OSError:
            pass
    return out


def tcl_tk_report() -> str:
    """报告 Tcl/Tk 数据目录，打包与源码运行都给出可判定结论。

    旧实现只检查 _MEIPASS/tcl、_MEIPASS/tk、_MEIPASS/_tk_data：
    PyInstaller 6.x 实际使用 _tcl_data / _tk_data，于是 tcl/tk 必然显示缺失，
    而 _tk_data 又掩盖了“其实都在”的事实。这里改为按标志文件判定：
    Tcl 目录必须有 init.tcl，Tk 目录必须有 tk.tcl；目录存在但缺文件也算缺失。
    """
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        base = Path(getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable))
        roots = [base, base / "_internal"]
        tcl_names = ("_tcl_data", "tcl")
        tk_names = ("_tk_data", "tk")
        tcl = _first_marker_dir(
            "TCL_LIBRARY", [r / n for r in roots for n in tcl_names], "init.tcl")
        tk = _first_marker_dir(
            "TK_LIBRARY", [r / n for r in roots for n in tk_names], "tk.tcl")
        mode = "打包运行"
    else:
        tcl = _first_marker_dir("TCL_LIBRARY", _source_tcl_candidates(), "init.tcl")
        tk = _first_marker_dir(
            "TK_LIBRARY", _source_tk_candidates(tcl), "tk.tcl")
        mode = "源码运行"

    def line(name: str, path: Path | None, marker: str) -> str:
        if path:
            return f"{name:<11}: 存在 {path}（{marker}）"
        if frozen:
            return f"{name:<11}: 缺失（未找到含 {marker} 的目录）"
        return f"{name:<11}: 未定位（源码模式，由 tkinter/系统提供）"

    return "\n".join([
        f"tcl/tk 模式  : {mode}",
        line("tcl", tcl, "init.tcl"),
        line("tk", tk, "tk.tcl"),
    ])


def env_report() -> str:
    """环境快照，用于排错：frozen 状态、_MEIPASS、可执行文件位置、Tcl/Tk 情况。"""
    lines = [
        f"frozen      : {getattr(sys, 'frozen', False)}",
        f"_MEIPASS    : {getattr(sys, '_MEIPASS', '(none)')}",
        f"webui_dir   : {webui_dir()}",
        f"resource_dir: {resource_dir()}",
        f"验证结果    : {verify_assets_dir(webui_dir())[1]}",
        f"目录内容    : {_skin_files(webui_dir())}",
        f"licenses    : {_skin_files(resource_dir() / 'licenses')}",
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
    lines.append(tcl_tk_report())
    return "\n".join(lines)
