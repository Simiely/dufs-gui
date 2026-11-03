"""界面公共工具：跨平台中文字体与 emoji 字体。"""

from __future__ import annotations

import os
import sys


def ui_font(size: int = 10, weight: str = "normal") -> tuple:
    if os.name == "nt":
        family = "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        family = "PingFang SC"
    else:
        family = "Noto Sans CJK SC"
    return (family, size, weight)


def emoji_font(size: int = 11) -> tuple:
    """Emoji 专用字体：避免中文主字体把彩色 emoji 显示成方块/单色小字。"""
    if os.name == "nt":
        family = "Segoe UI Emoji"
    elif sys.platform == "darwin":
        family = "Apple Color Emoji"
    else:
        family = "Noto Color Emoji"
    return (family, size)


def fit_canvas_text(canvas, item: int, text: str, max_width: int) -> tuple[str, bool]:
    """单行文本超宽时末尾省略；返回 (显示文本, 是否截断)。"""
    try:
        canvas.itemconfigure(item, text=text)
        x0, _, x1, _ = canvas.bbox(item)
    except Exception:
        return text, False
    if x1 - x0 <= max_width:
        return text, False
    best = "…"
    lo, hi = 0, len(text)
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + "…"
        canvas.itemconfigure(item, text=cand)
        x0, _, x1, _ = canvas.bbox(item)
        if x1 - x0 <= max_width:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    canvas.itemconfigure(item, text=best)
    return best, True


def text_width(text: str, font_spec) -> int:
    """文本像素宽度；测试桩没有 tkinter.font 时按 7px/字符估算。"""
    try:
        from tkinter import font as tkfont
        return int(tkfont.Font(font=font_spec).measure(text))
    except Exception:
        return int(len(text) * 7)


def ellipsize(text: str, max_px: int, font_spec) -> tuple[str, bool]:
    """按像素预算末尾省略；返回 (显示文本, 是否截断)。"""
    if max_px <= 0:
        return "", bool(text)
    if text_width(text, font_spec) <= max_px:
        return text, False
    best = "…"
    lo, hi = 0, len(text)
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + "…"
        if text_width(cand, font_spec) <= max_px:
            best, lo = cand, mid + 1
        else:
            hi = mid - 1
    return best, True
