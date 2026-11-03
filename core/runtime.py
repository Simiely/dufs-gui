"""dufs 运行时：二进制定位、版本探测与进程状态的统一入口。"""

from __future__ import annotations

import queue
from pathlib import Path

from . import dufsbin
from .server import DufsProcess


class DufsRuntime:
    """把"找二进制 → 读版本 → 起停进程"收敛到一处。

    app.py 之前同时维护 dufs_path 与 proc 两份状态，定位/版本探测分散在
    __init__、_restore、_start、_pick_dufs 四处；统一后只有这里能改状态。
    """

    def __init__(self, log_queue: queue.Queue):
        self.process = DufsProcess(log_queue)
        self.info: dufsbin.DufsInstall | None = None

    # ---------- 定位 / 版本 ----------
    def locate(self) -> dufsbin.DufsInstall | None:
        """只查找已存在的 dufs（不会复制到用户数据目录）。"""
        self.info = dufsbin.describe(dufsbin.find_dufs())
        return self.info

    def ensure(self) -> dufsbin.DufsInstall | None:
        """确保 dufs 已安装到用户数据目录（首次运行会复制内置副本）。"""
        self.info = dufsbin.describe(dufsbin.ensure_dufs())
        return self.info

    def adopt(self, path: str | Path) -> dufsbin.DufsInstall:
        """用户手动指定 dufs，复制到数据目录并刷新版本。"""
        target = dufsbin.install_custom(path)
        self.info = dufsbin.describe(target)
        return self.info

    @property
    def path(self) -> Path | None:
        return self.info.path if self.info else None

    @property
    def version(self) -> str:
        return self.info.version if self.info else ""

    @property
    def semver(self) -> str:
        return dufsbin.parse_version(self.version)

    # ---------- 进程状态 ----------
    @property
    def running(self) -> bool:
        return self.process.running

    @property
    def pid(self) -> int | None:
        return self.process.pid

    def status_text(self) -> str:
        """运行状态的统一文案，避免多处各写一遍导致不一致。"""
        return f"运行中 · PID {self.pid}" if self.running else "未启动"
