"""多地址实例编排：部分失败、端口占用隔离、统一停止。"""

from __future__ import annotations

import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import ServerConfig  # noqa: E402
from core.instances import InstanceManager  # noqa: E402
from core.launch import build_launch_plans  # noqa: E402


class FakeDufsProcess:
    fail_binds: set[str] = set()

    def __init__(self, log_queue, job=None, prefix="", tag=""):
        self.log_queue = log_queue
        self.tag = tag
        self.prefix = prefix
        self.running = False
        self.args = []

    def start(self, binary, args, cwd=None):
        self.args = list(args)
        self.running = True

    def wait_ready(self, port, host, timeout=8):
        self.running = self.tag not in self.fail_binds
        return self.running

    def stop(self):
        self.running = False

    def recent_output(self, _lines=0):
        return "模拟启动错误"


class InstanceManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = ServerConfig(
            share_path=self.tmp.name, port=5055, custom_ui=False,
            binds=["127.0.0.1", "10.4.240.16"])
        self.group = build_launch_plans(self.cfg, binary=sys.executable,
                                        diagnose_skin=False)
        self.labels = {"127.0.0.1": "仅本机", "10.4.240.16": "以太网"}

    def tearDown(self):
        self.tmp.cleanup()

    def _manager(self, fake):
        manager = InstanceManager(queue.Queue())
        patcher = mock.patch("core.instances.DufsProcess", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(manager.stop)
        return manager

    def test_all_binds_start_and_stop_together(self):
        fake = type("Fake", (FakeDufsProcess,), {"fail_binds": set()})
        manager = self._manager(fake)
        summary = manager.start(sys.executable, self.group.plans, self.labels)

        self.assertEqual(summary, "2 个地址均已启动")
        self.assertEqual(manager.status_text, "运行中 · 2 个地址")
        self.assertEqual(len(manager.running_states), 2)
        self.assertEqual({s.url for s in manager.states},
                         {"http://127.0.0.1:5055/",
                          "http://10.4.240.16:5055/"})
        for state in manager.states:
            self.assertEqual(
                state.process.args[state.process.args.index("-b") + 1],
                state.bind)

        manager.stop()
        self.assertFalse(manager.running)
        self.assertTrue(all(not s.running for s in manager.states))

    def test_partial_failure_is_reported_per_address(self):
        fake = type("Fake", (FakeDufsProcess,),
                    {"fail_binds": {"10.4.240.16"}})
        manager = self._manager(fake)
        summary = manager.start(sys.executable, self.group.plans, self.labels)

        self.assertEqual(len(manager.running_states), 1)
        self.assertEqual(manager.running_states[0].bind, "127.0.0.1")
        self.assertIn("2 个中 1 个已启动", summary)
        self.assertIn("10.4.240.16", summary)
        self.assertIn("模拟启动错误", summary)
        self.assertEqual(manager.status_text, "2 个中 1 个已启动 · 1 个失败")
        self.assertTrue(manager.failed_states())

    def test_occupied_port_only_skips_that_address(self):
        """某个 IP 的端口被占：只跳过该地址，其他照常启动。"""
        fake = type("Fake", (FakeDufsProcess,), {"fail_binds": set()})
        manager = self._manager(fake)
        probe = lambda port, host: host == "10.4.240.16"  # noqa: E731
        summary = manager.start(sys.executable, self.group.plans, self.labels,
                                probe=probe)

        states = {s.bind: s for s in manager.states}
        self.assertEqual(states["127.0.0.1"].status, "运行中")
        self.assertEqual(states["10.4.240.16"].status, "失败")
        self.assertIn("端口", states["10.4.240.16"].detail)
        self.assertIn("2 个中 1 个已启动", summary)
        self.assertIsNone(states["10.4.240.16"].process,
                          "端口被占的地址不应创建进程")

    def test_all_failed_status(self):
        fake = type("Fake", (FakeDufsProcess,),
                    {"fail_binds": {"127.0.0.1", "10.4.240.16"}})
        manager = self._manager(fake)
        summary = manager.start(sys.executable, self.group.plans, self.labels)
        self.assertEqual(manager.status_text, "启动失败 · 2 个失败")
        self.assertIn("全部启动失败", summary)

        # 主动停止后失败状态清空，界面据此收起失败详情区
        manager.stop()
        self.assertEqual(manager.failed_states(), [])
        self.assertEqual({s.status for s in manager.states}, {"已停止"})


if __name__ == "__main__":
    unittest.main()
