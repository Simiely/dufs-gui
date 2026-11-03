"""启动计时打点（默认关闭，零开销）。

仅在设置环境变量 ``DUFS_GUI_TIMING_FILE`` 时，把「标签、距脚本启动毫秒、
当前 epoch 毫秒」追加到该文件，用于区分 onefile 解包、Python 导入、
Tk/界面构建与系统映射各自的耗时；正常启动不读不写。
"""

from __future__ import annotations

import os
import time

_T0 = time.perf_counter()
_PATH = os.environ.get("DUFS_GUI_TIMING_FILE") or ""


def mark(label: str) -> None:
    if not _PATH:
        return
    try:
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(f"{label}\t{int((time.perf_counter() - _T0) * 1000)}"
                    f"\t{int(time.time() * 1000)}\n")
    except OSError:
        pass
