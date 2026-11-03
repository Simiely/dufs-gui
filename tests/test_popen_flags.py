"""启动参数回归：dufs 子进程不得出现控制台，stdout/stderr 必须被接管。"""

from __future__ import annotations

import io
import os
import queue
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import server  # noqa: E402

CREATE_NO_WINDOW = 0x08000000


class _FakeProc:
    pid = 424242

    def __init__(self) -> None:
        self.stdout = io.StringIO("")
        self.returncode = None

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


class _FakeJob:
    def assign(self, pid: int) -> bool:
        return True

    def close(self) -> None:
        pass


@unittest.skipUnless(os.name == "nt", "仅 Windows 需要控制台抑制参数")
class PopenFlagsTest(unittest.TestCase):
    def test_start_hides_console_and_pipes_output(self):
        q: queue.Queue = queue.Queue()
        with mock.patch.object(server.subprocess, "Popen",
                               return_value=_FakeProc()) as popen, \
                mock.patch.object(server, "_clean_child_env", return_value=None):
            proc = server.DufsProcess(q, job=_FakeJob())
            proc.start("C:/fake/dufs.exe", ["--port", "5099"])
        kwargs = popen.call_args.kwargs
        self.assertTrue(kwargs["creationflags"] & CREATE_NO_WINDOW)
        self.assertIsNotNone(kwargs["stdout"])
        self.assertEqual(kwargs["stdout"], subprocess.PIPE)
        self.assertIsNotNone(kwargs["stderr"])
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
        si = kwargs["startupinfo"]
        self.assertTrue(si.dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(si.wShowWindow, 0)
        self.assertEqual(popen.call_args.args[0],
                         ["C:/fake/dufs.exe", "--port", "5099"])


class DialogKeysTest(unittest.TestCase):
    def test_escape_always_cancels(self):
        from ui.dialog import _key_results
        self.assertFalse(_key_results(True)["<Escape>"])
        self.assertFalse(_key_results(False)["<Escape>"])

    def test_destructive_enter_cancels(self):
        from ui.dialog import _key_results
        self.assertFalse(_key_results(False)["<Return>"])
        self.assertTrue(_key_results(True)["<Return>"])
