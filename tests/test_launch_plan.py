"""启动决策 build_launch_plan 的表驱动测试（不弹窗、不启进程）。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import ServerConfig  # noqa: E402
from core.launch import build_launch_plan  # noqa: E402


def _skin_dir(root: Path) -> Path:
    d = root / "skin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (d / "index.js").write_text("// skin", encoding="utf-8")
    return d


def _asset_count(args: tuple[str, ...]) -> int:
    return sum(1 for a in args if a == "--assets")


class LaunchPlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.share = self.root / "share"
        self.share.mkdir()
        self.skin = _skin_dir(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _cfg(self, **kw) -> ServerConfig:
        base = dict(share_path=str(self.share), bind="127.0.0.1", port=5000,
                    assets_dir=str(self.skin), custom_ui=True)
        base.update(kw)
        return ServerConfig(**base)

    def test_table(self):
        cases = [
            {
                "name": "回环 + 内置皮肤：生成 --assets 与降级参数",
                "cfg": self._cfg(),
                "kw": {"diagnose_skin": True,
                       "skin_probe": lambda _d: (True, "index.html/index.js/favicon.ico 齐全"),
                       "skin_version": "0.47.0", "dufs_version": "0.47.0"},
                "check": {
                    "errors": (),
                    "host_check": "127.0.0.1",
                    "asset_count": 1,
                    "fallback_has_assets": False,
                    "auth_log_has": "未启用",
                    "skin_has": "已加入 --assets",
                    "url_prefix": "http://127.0.0.1:5000",
                },
            },
            {
                "name": "通配监听 + 口令：检查主机回落 127.0.0.1，日志不含密码",
                "cfg": self._cfg(bind="0.0.0.0", auth_user="alice", auth_pass="s3cret"),
                "kw": {"diagnose_skin": False},
                "check": {
                    "errors": (),
                    "host_check": "127.0.0.1",
                    "auth_log_has": "alice",
                    "auth_log_not": "s3cret",
                    "args_has_auth": "alice:s3cret@/:rw",
                },
            },
            {
                "name": "关闭美化：不传 --assets，也没有降级参数",
                "cfg": self._cfg(custom_ui=False),
                "kw": {"diagnose_skin": True,
                       "skin_probe": lambda _d: (True, "index.html/index.js/favicon.ico 齐全")},
                "check": {
                    "asset_count": 0,
                    "fallback_has_assets": None,
                    "skin_has": "未启用（配置中 custom_ui=false）",
                    "custom_ui": False,
                },
            },
            {
                "name": "外部皮肤目录无效：报错并停止启动",
                "cfg": self._cfg(assets_dir=str(self.root / "missing")),
                "kw": {"diagnose_skin": True,
                       "skin_probe": lambda _d: (False, "缺少 index.html")},
                "check": {
                    "errors_nonempty": True,
                    "can_start": False,
                    "skin_has": "目录不可用",
                    "asset_count": 0,
                },
            },
            {
                "name": "共享单个文件：提示只出现一次",
                "cfg": self._cfg(share_path=str(self.share / "a.txt")),
                "kw": {"diagnose_skin": True,
                       "skin_probe": lambda _d: (True, "ok")},
                "check": {
                    "share_is_file": True,
                    "skin_file_warning_count": 1,
                },
            },
            {
                "name": "皮肤与 dufs 版本不一致：给出升级提示",
                "cfg": self._cfg(),
                "kw": {"diagnose_skin": True,
                       "skin_probe": lambda _d: (True, "ok"),
                       "skin_version": "0.47.0", "dufs_version": "0.46.0"},
                "check": {"skin_has": "与 dufs 0.46.0 不一致"},
            },
        ]

        for case in cases:
            with self.subTest(case["name"]):
                (self.share / "a.txt").write_text("x", encoding="utf-8")
                cfg = case["cfg"]
                plan = build_launch_plan(cfg, config_path=str(self.root / "config.json"),
                                         **case["kw"])
                c = case["check"]
                if "errors" in c:
                    self.assertEqual(plan.errors, c["errors"])
                if c.get("errors_nonempty"):
                    self.assertTrue(plan.errors)
                if "can_start" in c:
                    self.assertEqual(plan.can_start, c["can_start"])
                if "host_check" in c:
                    self.assertEqual(plan.host_check, c["host_check"])
                if "asset_count" in c:
                    self.assertEqual(_asset_count(plan.args), c["asset_count"])
                if "fallback_has_assets" in c:
                    if c["fallback_has_assets"] is None:
                        self.assertIsNone(plan.fallback_args)
                    else:
                        self.assertIsNotNone(plan.fallback_args)
                        self.assertEqual(_asset_count(plan.fallback_args),
                                         int(c["fallback_has_assets"]))
                if "auth_log_has" in c:
                    self.assertIn(c["auth_log_has"], plan.auth_log)
                if "auth_log_not" in c:
                    self.assertNotIn(c["auth_log_not"], plan.auth_log)
                if "args_has_auth" in c:
                    self.assertIn(c["args_has_auth"], plan.args)
                if "skin_has" in c:
                    self.assertIn(c["skin_has"], "\n".join(plan.skin_logs))
                if "skin_file_warning_count" in c:
                    self.assertEqual(
                        sum("共享的是单个文件" in line for line in plan.skin_logs),
                        c["skin_file_warning_count"])
                if "url_prefix" in c:
                    self.assertTrue(plan.url.startswith(c["url_prefix"]), plan.url)
                if "custom_ui" in c:
                    self.assertEqual(plan.custom_ui, c["custom_ui"])

    def test_binary_is_injected_not_probed(self):
        plan = build_launch_plan(self._cfg(), binary=sys.executable,
                                 diagnose_skin=False)
        self.assertEqual(plan.binary, Path(sys.executable))

    def test_plan_does_not_touch_process(self):
        """纯函数只产出决定：不启动进程、不写文件。"""
        before = set(os.listdir(self.root))
        build_launch_plan(self._cfg(), diagnose_skin=False)
        self.assertEqual(set(os.listdir(self.root)), before)


if __name__ == "__main__":
    unittest.main()
