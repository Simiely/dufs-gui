"""Dufs GUI 入口。

崩溃兜底必须最先安装：打包后的 exe 用 --console=False，
未捕获异常会直接静默退出（表现为"双击闪退"），看不到任何报错。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import timing  # noqa: E402

timing.mark("script")

from core import crashlog  # noqa: E402

crashlog.install()
timing.mark("crashlog")

# 自检要在 import app（可能失败）之前，否则 tkinter 坏了就啥也看不到
if "--selftest" in sys.argv:
    print(crashlog.env_report())
    # 顺带验证二维码模块已打进冻结产物（纯标准库，不依赖 PIL）
    try:
        from core.qr import matrix_for, png_bytes

        modules = matrix_for("http://127.0.0.1:5000/")
        print(f"qr          : {len(modules)}x{len(modules)}，"
              f"png {len(png_bytes(modules))} 字节")
    except Exception as e:  # noqa: BLE001
        print(f"qr          : 失败 -> {type(e).__name__}: {e}")
    sys.exit(0)

from app import main  # noqa: E402

timing.mark("imports_done")

if __name__ == "__main__":
    main()
