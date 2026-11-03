"""多地址实例管理：每块选中的网卡一个 dufs 进程。

为什么不用 dufs 原生的逗号多绑定：实测 0.47 支持 ``-b a,b``，但端口冲突等
失败是"全有或全无"——一个地址起不来整进程退出，无法满足"其他照常启动、
明确报出哪个地址失败"。因此这里按地址拆分进程，各自绑定自己的 IP、共用
同一端口（不同 IP 同端口合法）、同一目录与同一套参数。

所有子进程逐个加入同一个 Windows Job Object，父进程退出时一起结束。
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .launch import LaunchPlan, summarize_start_results
from .netutil import port_in_use
from .server import DufsProcess, _WinJob

#: 单实例等待就绪的最长时间；多个实例并行等待，不叠加
DEFAULT_WAIT = 8.0


@dataclass
class InstanceState:
    bind: str
    label: str
    url: str
    port: int
    status: str = "未启动"          # 未启动 / 启动中 / 运行中 / 失败 / 已停止 / 无响应
    detail: str = ""
    process: DufsProcess | None = None
    plan: LaunchPlan | None = None
    degraded: bool = False

    @property
    def running(self) -> bool:
        return self.status in ("运行中", "无响应") and self.process is not None \
            and self.process.running

    @property
    def display(self) -> str:
        return self.label or self.bind or "（未知地址）"


class InstanceManager:
    """一次操作启停全部地址，并保留每个地址的状态与失败原因。"""

    def __init__(self, log_queue) -> None:
        self.log_queue = log_queue
        self.states: list[InstanceState] = []
        self.last_summary = ""
        self._job: _WinJob | None = (_WinJob() if os.name == "nt" else None)

    # ---------- 状态 ----------
    @property
    def running_states(self) -> list[InstanceState]:
        return [s for s in self.states if s.running]

    @property
    def running(self) -> bool:
        return bool(self.running_states)

    @property
    def status_text(self) -> str:
        total = len(self.states)
        if total == 0:
            return "未启动"
        running = len(self.running_states)
        if running == total:
            return f"运行中 · {total} 个地址"
        if running:
            return f"{total} 个中 {running} 个已启动"
        failed = [s for s in self.states if s.status == "失败"]
        return "启动失败" if failed else "未启动"

    def failed_states(self) -> list[InstanceState]:
        return [s for s in self.states if s.status == "失败"]

    def failures_text(self) -> str:
        lines = []
        for s in self.failed_states():
            lines.append(f"{s.display}：{s.detail or '未知原因'}")
        return "\n".join(lines) or "没有失败项"

    # ---------- 启停 ----------
    def start(self, binary: str | os.PathLike, plans: list[LaunchPlan] | tuple[LaunchPlan, ...],
              labels: dict[str, str] | None = None,
              wait: float = DEFAULT_WAIT,
              probe: Callable[[int, str], bool] = port_in_use) -> str:
        """启动全部地址，返回可直接展示的汇总文案（不抛异常）。"""
        self.stop()
        labels = labels or {}
        plans = list(plans)
        self.states = [
            InstanceState(
                bind=plan.bind,
                label=labels.get(plan.bind, plan.bind),
                url=plan.url,
                port=plan.port,
                plan=plan,
            )
            for plan in plans
        ]
        if self._job is None and os.name == "nt":
            self._job = _WinJob()

        pending: list[InstanceState] = []
        for st in self.states:
            if not st.plan:
                st.status, st.detail = "失败", "缺少启动计划"
                continue
            if probe(st.port, st.plan.host_check):
                # 只影响该地址：不启动这一项，其他地址继续
                st.status, st.detail = "失败", f"端口 {st.port} 已被占用"
                self.log_queue.put(("log", f"[{st.display}] 端口 {st.port} 已被占用，跳过"))
                continue
            if self._spawn(st, binary):
                pending.append(st)

        self._wait_all(pending, wait)

        # 皮肤导致启动失败时，对失败项单独降级重试一次（不写盘、不影响其他实例）
        retry = [s for s in self.states if s.status == "失败" and s.plan
                 and s.plan.fallback_args]
        for st in retry:
            self._retry_without_skin(st, binary, wait)

        results = [(s.bind, s.status == "运行中", s.detail) for s in self.states]
        self.last_summary = summarize_start_results(results)
        self.log_queue.put(("log", self.last_summary))
        return self.last_summary

    def _spawn(self, st: InstanceState, binary: str | os.PathLike,
               args: tuple[str, ...] | None = None) -> bool:
        assert st.plan is not None
        st.process = DufsProcess(
            self.log_queue, job=self._job,
            prefix=f"[{st.display}] ", tag=st.bind)
        try:
            st.process.start(binary, list(args or st.plan.args))
        except Exception as e:  # noqa: BLE001
            st.status, st.detail = "失败", f"启动失败：{e}"
            self.log_queue.put(("log", f"[{st.display}] 启动失败：{e}"))
            return False
        st.status, st.detail = "启动中", ""
        return True

    def _wait_all(self, pending: list[InstanceState], wait: float) -> None:
        if not pending:
            return
        futures = {}
        with ThreadPoolExecutor(max_workers=min(8, len(pending))) as pool:
            for st in pending:
                plan = st.plan
                assert plan is not None and st.process is not None
                futures[pool.submit(st.process.wait_ready, st.port,
                                    plan.host_check, wait)] = st
            for fut, st in futures.items():
                try:
                    ready = bool(fut.result())
                except Exception:  # noqa: BLE001
                    ready = False
                if ready:
                    st.status, st.detail = "运行中", ""
                else:
                    st.status = "失败"
                    st.detail = self._failure_reason(st)

    def _failure_reason(self, st: InstanceState) -> str:
        if st.process is None:
            return "进程未启动"
        out = st.process.recent_output(6)
        if out:
            return out.replace("\n", " / ")[-300:]
        return f"端口 {st.port} 未就绪（进程可能已退出）"

    def _retry_without_skin(self, st: InstanceState, binary: str | os.PathLike,
                            wait: float) -> None:
        assert st.plan is not None
        if st.process is not None:
            st.process.stop()
        self.log_queue.put(("log", f"[{st.display}] 首次启动未就绪，尝试不带网页皮肤重试…"))
        if not self._spawn(st, binary, st.plan.fallback_args):
            return
        ready = st.process.wait_ready(st.port, st.plan.host_check, wait) \
            if st.process else False
        if ready:
            st.status = "运行中"
            st.degraded = True
            st.detail = "已降级：本次未使用自定义网页皮肤"
            self.log_queue.put(("log", f"[{st.display}] 已不带皮肤启动成功（本次临时降级）"))
        else:
            st.status = "失败"
            st.detail = self._failure_reason(st)

    def stop(self) -> None:
        for st in self.states:
            if st.process is not None:
                st.process.stop()
                st.process = None
            if st.status in ("运行中", "启动中", "无响应"):
                st.status = "已停止"
        if self._job is not None:
            # 关闭共享 Job：即使个别 terminate 失败，内核也会结束作业内所有进程
            self._job.close()
            self._job = None
