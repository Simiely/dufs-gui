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
