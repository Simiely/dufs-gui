"""dufs 健康检查：区分“进程活着”和“服务真的可用”。

dufs 官方提供 ``/__dufs__/health``，返回 200 + ``{"status":"OK"}``，
并且支持 HEAD（见 dufs v0.47.0 的 src/server.rs：HEALTH_CHECK_PATH 与
head_only 分支）。这里用 HEAD 探测，避免每次拉取响应体。

探测在后台线程执行，只通过回调把事件交给 app 的队列；任何控件操作都在
Tk 主线程的 after 轮询里完成。
"""

from __future__ import annotations

import http.client
import queue
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

#: 参考 Kubernetes 探针的常见组合（文档示例 periodSeconds=5、timeoutSeconds=3、
#: failureThreshold=3；概念文档默认 periodSeconds=10、failureThreshold=3）。
#: 本机 HEAD /__dufs__/health 实测通常 <30ms，因此取更快的 2 秒间隔、
#: 1.5 秒超时、连续 3 次失败才判无响应；恢复 1 次成功即恢复。
DEFAULT_INTERVAL = 2.0
DEFAULT_TIMEOUT = 1.5
DEFAULT_FAILURE_THRESHOLD = 3


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    detail: str
    latency_ms: float


def probe_once(url: str, timeout: float = DEFAULT_TIMEOUT) -> HealthResult:
    """对 dufs 的 /__dufs__/health 发一次 HEAD 请求。

    dufs 0.47 的 health 接口不受访问口令保护，这里不发送任何凭据。
    """
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        return HealthResult(False, "健康检查 URL 缺少主机", 0.0)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    start = time.monotonic()
    conn = None
    try:
        if parsed.scheme == "https":
            # 本地自签名证书也要能探测；这里只验证服务是否响应，不验证证书链。
            conn = http.client.HTTPSConnection(
                host, port, timeout=timeout,
                context=ssl._create_unverified_context())
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("HEAD", path,
                     headers={"User-Agent": "DufsGui-health"})
        resp = conn.getresponse()
        latency = (time.monotonic() - start) * 1000
        ok = 200 <= resp.status < 400
        return HealthResult(ok, f"HTTP {resp.status}", round(latency, 1))
    except Exception as e:  # noqa: BLE001
        latency = (time.monotonic() - start) * 1000
        return HealthResult(False, f"{type(e).__name__}: {e}", round(latency, 1))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


class HealthMonitor:
    """后台周期探测；只向外部队列发事件，不直接接触 Tk 控件。

    事件：
      - ``health_ok``：从“无响应”恢复，或首次健康时（只发一次）
      - ``health_fail``：连续失败达到阈值，且当前仍被认为是健康的
    """

    def __init__(
        self,
        url_getter: Callable[[], str],
        emit: Callable[[str, str], None],
        interval: float = DEFAULT_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        probe: Callable[[str, float], HealthResult] = probe_once,
    ) -> None:
        self.url_getter = url_getter
        self.emit = emit
        # 下限只防误传 0/负数；生产默认 3s，测试可注入更小值
        self.interval = max(0.05, float(interval))
        self.timeout = max(0.1, float(timeout))
        self.failure_threshold = max(1, int(failure_threshold))
        self.probe = probe
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._healthy = True
        self._failures = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        # 每次 start 用独立的 Event，避免 stop 超时后旧线程被新 start 复活
        stop_event = threading.Event()
        self._stop = stop_event
        self._healthy = True
        self._failures = 0
        self._thread = threading.Thread(
            target=self._run, args=(stop_event,),
            name="dufs-health", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=timeout)
        self._thread = None

    def evaluate(self, ok: bool, detail: str) -> tuple[str, str] | None:
        """状态机：连续失败达到阈值才发 health_fail；一次成功即恢复。"""
        if ok:
            self._failures = 0
            if not self._healthy:
                self._healthy = True
                return ("health_ok", detail)
            return None
        self._failures += 1
        if self._healthy and self._failures >= self.failure_threshold:
            self._healthy = False
            return ("health_fail", detail)
        return None

    def _run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                url = self.url_getter()
            except Exception as e:  # noqa: BLE001
                ok, detail = False, f"URL 生成失败：{type(e).__name__}: {e}"
            else:
                result = self.probe(url, self.timeout)
                ok, detail = result.ok, result.detail
            if stop_event.is_set():
                break
            event = self.evaluate(ok, detail)
            if event:
                try:
                    self.emit(*event)
                except queue.Full:
                    pass
            stop_event.wait(self.interval)
