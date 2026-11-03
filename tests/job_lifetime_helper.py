"""集成测试辅助：父进程内启动长命子进程并启用生命周期守卫。

测试会强杀本进程，然后检查子进程是否随之退出。
用法：python tests/job_lifetime_helper.py <child_pid_file>
"""

from __future__ import annotations

import queue
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.server import DufsProcess  # noqa: E402


def main() -> None:
    pid_file = Path(sys.argv[1])
    proc = DufsProcess(queue.Queue())
    child_code = "import time\nwhile True:\n    time.sleep(1)"
    proc.start(sys.executable, ["-c", child_code])
    # 原子写，避免测试读到空文件
    tmp = pid_file.with_suffix(".tmp")
    tmp.write_text(str(proc.pid), encoding="utf-8")
    tmp.replace(pid_file)
    while True:
        time.sleep(0.5)


if __name__ == "__main__":
    main()
