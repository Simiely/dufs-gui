"""界面公共工具：跨平台中文字体。"""

from __future__ import annotations

import os
import sys

APP_NAME = "Dufs 文件共享"


def ui_font(size: int = 10, weight: str = "normal") -> tuple:
    if os.name == "nt":
        family = "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        family = "PingFang SC"
    else:
        family = "Noto Sans CJK SC"
    return (family, size, weight)
