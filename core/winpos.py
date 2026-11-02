"""窗口定位工具：让弹窗稳定出现在父窗口中央，且不会跑到屏幕外。

多显示器 / 不同缩放比下，Toplevel 的默认位置经常很怪（跑到副屏角落、
甚至完全在可视区之外）。这里统一处理。
"""

from __future__ import annotations

import tkinter as tk


def center_on_parent(win: tk.Misc, parent: tk.Misc,
                     width: int, height: int) -> None:
    """把 win 摆到 parent 正中；parent 无效则退回屏幕中心。"""
    try:
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    except Exception:
        x = y = None

    if x is None or y is None or parent.winfo_width() <= 1:
        x = (win.winfo_screenwidth() - width) // 2
        y = (win.winfo_screenheight() - height) // 2

    x, y = clamp_to_screen(win, x, y, width, height)
    win.geometry(f"{width}x{height}+{x}+{y}")


def clamp_to_screen(win: tk.Misc, x: int, y: int,
                    width: int, height: int) -> tuple[int, int]:
    """确保窗口完整落在某个显示器内。

    多显示器时总可用区域可能是多屏拼接后的矩形，单纯按 screenwidth 钳制
    仍可能落在两屏之间的黑边里。这里逐个显示器判断是否装得下，
    装不下就选重叠面积最大的那块。
    """
    screens = _enumerate_screens(win)
    if not screens:
        return max(x, 0), max(y, 0)

    best, best_area = None, -1
    for sx, sy, sw, sh in screens:
        ox = max(0, min(x + width, sx + sw) - max(x, sx))
        oy = max(0, min(y + height, sy + sh) - max(y, sy))
        area = ox * oy
        if area > best_area:
            best, best_area = (sx, sy, sw, sh), area

    sx, sy, sw, sh = best  # type: ignore[misc]

    # 装得下就整体挪进去；装不下（窗口比屏幕大）就保证左上角可见
    if width <= sw:
        x = min(max(x, sx), sx + sw - width)
    else:
        x = max(x, sx)
    if height <= sh:
        y = min(max(y, sy), sy + sh - height)
    else:
        y = max(y, sy)

    return int(x), int(y)


def _enumerate_screens(win: tk.Misc) -> list[tuple[int, int, int, int]]:
    """返回所有显示器的 (x, y, w, h)。失败时退回单屏。"""
    screens: list[tuple[int, int, int, int]] = []
    try:
        # Windows：EnumDisplayMonitors 能拿到每块屏的真实工作区
        import ctypes
        from ctypes import wintypes

        monitors: list[tuple[int, int, int, int]] = []

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(wintypes.RECT), ctypes.c_double)

        def _cb(_hmon, _hdc, lprc, _data):
            r = lprc.contents
            monitors.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return 1

        ctypes.windll.user32.EnumDisplayMonitors(  # type: ignore[attr-defined]
            None, None, MonitorEnumProc(_cb), 0)
        screens = monitors
    except Exception:
        screens = []

    if not screens:
        try:
            screens = [(0, 0, win.winfo_screenwidth(), win.winfo_screenheight())]
        except Exception:
            screens = []
    return screens
