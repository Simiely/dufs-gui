"""Dufs GUI 入口。

崩溃兜底必须最先安装：打包后的 exe 用 --console=False，
未捕获异常会直接静默退出（表现为"双击闪退"），看不到任何报错。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import crashlog  # noqa: E402

crashlog.install()

# 自检要在 import app（可能失败）之前，否则 tkinter 坏了就啥也看不到
if "--selftest" in sys.argv:
    print(crashlog.env_report())
    sys.exit(0)

from app import main  # noqa: E402

if __name__ == "__main__":
    main()
