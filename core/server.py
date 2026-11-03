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


class _WinJob:
    """Windows Job Object：句柄关闭时由内核结束作业内所有进程。

    使用 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE 的原因：任务管理器强杀、主进程崩溃、
    注销等场景不会执行 Python 的 finally / atexit，只有内核级的句柄清理可靠。
    句柄必须活到 stop()，不能 assign 完就关。
    """

    _LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self) -> None:
        self._handle = None

    def assign(self, pid: int) -> bool:
        """把 pid 放进作业并保持句柄；失败时返回 False（由调用方降级）。"""
        if os.name != "nt":
            return False
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
        except (ImportError, AttributeError):
            return False

        class _IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class _BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BASIC_LIMIT_INFORMATION),
                ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        # 64 位下句柄不能按默认 int 传递，必须显式声明 restype/argtypes
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return False

        info = _EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = self._LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
                handle, self._EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(handle)
            return False

        # PROCESS_SET_QUOTA | PROCESS_TERMINATE 是 AssignProcessToJobObject 所需权限
        proc_handle = kernel32.OpenProcess(0x0100 | 0x0001, False, int(pid))
        if not proc_handle:
            kernel32.CloseHandle(handle)
            return False
        try:
            ok = bool(kernel32.AssignProcessToJobObject(handle, proc_handle))
        finally:
            kernel32.CloseHandle(proc_handle)
        if not ok:
            kernel32.CloseHandle(handle)
            return False

        self._handle = handle
        return True

    def close(self) -> None:
        if not self._handle:
            return
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(self._handle)
        except Exception:  # noqa: BLE001
            pass
        self._handle = None


if os.name != "nt":
    #: POSIX 下没有 Job Object，用 atexit + 信号兜底；只登记实际运行中的子进程
    _POSIX_CHILDREN: set[subprocess.Popen] = set()
    _POSIX_GUARD_INSTALLED = False

    def _terminate_posix_children() -> None:
        for proc in list(_POSIX_CHILDREN):
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
        for proc in list(_POSIX_CHILDREN):
            try:
                proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except OSError:
                    pass
        _POSIX_CHILDREN.clear()

    def _install_posix_guard() -> None:
        """首次启动子进程时安装守卫；重复调用无副作用。"""
        global _POSIX_GUARD_INSTALLED
        if _POSIX_GUARD_INSTALLED:
            return
        import atexit
        import signal

        atexit.register(_terminate_posix_children)
        for sig in (signal.SIGTERM, signal.SIGINT):
            prev = signal.getsignal(sig)

            def handler(signum, frame, _prev=prev):
                _terminate_posix_children()
                if _prev == signal.SIG_IGN:
                    return
                if callable(_prev):
                    return _prev(signum, frame)
                raise SystemExit(128 + signum)

            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                # 非主线程 / 受限环境装不上信号处理器，atexit 仍然有效
                pass
        _POSIX_GUARD_INSTALLED = True


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
        self._job: _WinJob | None = None
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
        if self.proc is not None:
            # 上一次进程已自然退出：释放旧 Job 句柄 / POSIX 登记，避免句柄泄漏
            self._close_job()
            if os.name != "nt":
                _POSIX_CHILDREN.discard(self.proc)
            self.proc = None

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

        if os.name == "nt":
            # Windows：加入 Job Object，父进程被强杀时由内核带走子进程
            self._job = _WinJob()
            if not self._job.assign(self.proc.pid):
                self._job.close()
                self._job = None
                hint = "提示：未能把 dufs 加入 Job Object，父进程被强杀时可能残留子进程"
                self.recent.append(hint)
                self.log_queue.put(("log", hint))
        else:
            # POSIX：登记到 atexit / SIGTERM / SIGINT 守卫
            _install_posix_guard()
            _POSIX_CHILDREN.add(self.proc)

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

    def _close_job(self) -> None:
        if self._job is not None:
            self._job.close()
            self._job = None

    def stop(self, timeout: float = 5.0) -> None:
        if not self.proc:
            self._close_job()
            return
        proc, self.proc = self.proc, None
        if os.name != "nt":
            _POSIX_CHILDREN.discard(proc)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=1.0)
        # 关闭 Job 句柄：即使上面的 terminate 失败，内核也会结束作业内所有进程
        self._close_job()
