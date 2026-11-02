"""dufs 子进程管理：启动、停止、日志采集。"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from collections import deque
from typing import IO

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _unset_dll_directory() -> str | None:
    """撤销 PyInstaller bootloader 设置的 DLL 搜索路径，返回原值以便恢复。

    官方文档明确要求：Windows 上 bootloader 用 SetDllDirectoryW 把库搜索路径
    指向 _MEIPASS，而该设置**会被子进程继承**。外部程序（这里是 dufs.exe）
    可能因此加载到不兼容的同名 DLL 而启动失败。

    参见 PyInstaller "Common Issues and Pitfalls" →
    "Launching External Programs from the Frozen Application"。
    """
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return None
    try:
        import ctypes

        ctypes.windll.kernel32.SetDllDirectoryW(None)
        return getattr(sys, "_MEIPASS", None)
    except Exception:
        return None


def _restore_dll_directory(prev: str | None) -> None:
    """恢复主进程自己的 DLL 搜索路径（本进程后续还要正常加载 Tk）。"""
    if not prev:
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetDllDirectoryW(prev)
    except Exception:
        pass


def _clean_child_env() -> dict[str, str] | None:
    """从 PATH 中剔除锚定在 _MEIPASS 的条目，避免子进程误用打包进来的库。

    某些 runtime hook 会把 _MEIPASS 加进 PATH；对外部程序来说这是污染。
    """
    if not getattr(sys, "frozen", False):
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    env = os.environ.copy()
    path = env.get("PATH", "")
    if not path:
        return env
    kept = [p for p in path.split(os.pathsep)
            if not os.path.abspath(p).startswith(os.path.abspath(meipass))]
    env["PATH"] = os.pathsep.join(kept)
    return env


class DufsProcess:
    """管理一个 dufs 服务进程，并把它的输出实时投递到队列。"""

    #: 保留的最近输出行数，专门用于启动失败时定位原因
    #: （日志区消费完就没了，失败时需要回溯）
    RECENT_MAX = 60

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self.proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self.recent: deque[str] = deque(maxlen=self.RECENT_MAX)

    def recent_output(self, limit: int = 20) -> str:
        """返回最近若干行输出（启动失败时展示给用户）。"""
        return "\n".join(list(self.recent)[-limit:]).strip()

    def exited(self) -> bool:
        """进程是否已退出（用于提前判定启动失败，不必空等超时）。"""
        return self.proc is not None and self.proc.poll() is not None

    def wait_ready(self, port: int, host: str, timeout: float = 8.0) -> bool:
        """等待端口就绪；若进程提前退出则立即返回 False。

        单纯轮询端口有两个毛病：进程秒退时要白等一整个超时；
        真实启动慢时又可能误判。这里两者都兼顾。
        """
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc is None:
                return False
            if self.proc.poll() is not None:
                return False  # 已经死了，不用再等
            sock = None
            try:
                import socket
                fam = socket.AF_INET6 if ":" in host else socket.AF_INET
                sock = socket.socket(fam, socket.SOCK_STREAM)
                sock.settimeout(0.3)
                if sock.connect_ex((host.strip("[]"), port)) == 0:
                    return True
            except OSError:
                pass
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            time.sleep(0.15)
        return False

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    def start(self, binary: str | os.PathLike, args: list[str], cwd: str | None = None) -> None:
        if self.running:
            raise RuntimeError("服务已在运行")

        popen_kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
            "cwd": cwd or None,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = CREATE_NO_WINDOW
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            popen_kwargs["startupinfo"] = si

        # 给外部程序一个干净的库搜索环境，启动完立刻恢复本进程的设置
        env = _clean_child_env()
        if env is not None:
            popen_kwargs["env"] = env
        prev = _unset_dll_directory()
        try:
            self.proc = subprocess.Popen([str(binary), *args], **popen_kwargs)  # type: ignore[arg-type]
        finally:
            _restore_dll_directory(prev)

        self._reader = threading.Thread(target=self._pump,
                                        args=(self.proc.stdout,), daemon=True)
        self._reader.start()

    def _pump(self, stream: IO[str] | None) -> None:
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                line = line.rstrip()
                self.recent.append(line)
                self.log_queue.put(("log", line))
        except (ValueError, OSError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass
            self.log_queue.put(("exit", None))

    def stop(self, timeout: float = 5.0) -> None:
        if not self.proc:
            return
        proc, self.proc = self.proc, None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=1.0)
