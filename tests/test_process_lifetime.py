"""P0-3 子进程生命周期：父进程被强杀后子进程必须退出。

Windows 依赖 Job Object + JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE；
POSIX 走 atexit / SIGTERM 兜底（SIGKILL 无法被捕获，不在承诺范围内）。
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.server import _WinJob  # noqa: E402

HELPER = Path(__file__).resolve().with_name("job_lifetime_helper.py")


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                         wintypes.DWORD]
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x00000102  # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_pid(pid: int) -> None:
    if os.name == "nt":
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                         wintypes.DWORD]
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x0001, False, int(pid))  # TERMINATE
        if handle:
            try:
                kernel32.TerminateProcess(handle, 1)
            finally:
                kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


class ProcessLifetimeTest(unittest.TestCase):
    def _wait(self, predicate, timeout: float, interval: float = 0.1) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return predicate()

    @unittest.skipUnless(os.name == "nt", "Windows Job Object 专项")
    def test_win_job_close_kills_child(self):
        """句柄关闭时内核应结束作业内进程（父进程存活也成立）。"""
        job = _WinJob()
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(job.assign(child.pid), "AssignProcessToJobObject 失败")
            job.close()
            child.wait(timeout=10)
        finally:
            job.close()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_child_exits_when_parent_is_killed(self):
        with tempfile.TemporaryDirectory() as td:
            pid_file = Path(td) / "child.pid"
            parent = subprocess.Popen(
                [sys.executable, str(HELPER), str(pid_file)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            child_pid = 0
            try:
                self.assertTrue(
                    self._wait(lambda: pid_file.exists() and pid_file.read_text(
                        encoding="utf-8").strip() != "", 15),
                    "辅助进程未写出子进程 PID")
                child_pid = int(pid_file.read_text(encoding="utf-8").strip())
                self.assertTrue(_pid_alive(child_pid), "子进程应已启动")

                if os.name == "nt":
                    parent.kill()  # TerminateProcess：不会执行 Python 清理
                else:
                    parent.terminate()  # SIGTERM：触发 atexit/signal 兜底
                parent.wait(timeout=10)

                self.assertTrue(
                    self._wait(lambda: not _pid_alive(child_pid), 10),
                    "父进程结束后子进程仍在运行（生命周期守卫失效）")
            finally:
                if parent.poll() is None:
                    _kill_pid(parent.pid)
                    parent.wait(timeout=5)
                if child_pid and _pid_alive(child_pid):
                    _kill_pid(child_pid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
