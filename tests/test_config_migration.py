"""配置 schema 版本化、迁移、坏配置恢复与原子写测试。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import (CONFIG_VERSION, AppConfig, ServerConfig,  # noqa: E402
                         load_config, save_config)


class ConfigMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, data) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_legacy_config_upgrades_to_current_version(self):
        """无版本号的旧配置按 v1 处理，载入即升级到 v2。"""
        self._write({
            "profiles": {"p1": {"port": "5001", "allow_delete": "no"}},
            "current": "p1",
            "recent_paths": ["C:\\data", 123],
            "dark_mode": "false",
            "current_config": {"port": "4000"},
        })
        cfg = load_config(self.path)
        self.assertEqual(cfg.config_version, CONFIG_VERSION)
        self.assertIn("升级", cfg.notice)
        self.assertEqual(cfg.profiles["p1"]["port"], 5001)
        # 类型不符 -> 回落默认 False，而不是把字符串 "no" 当布尔
        self.assertFalse(cfg.profiles["p1"]["allow_delete"])
        # 旧版的 dark_mode 字段已移除，载入时忽略且不再回写
        self.assertFalse(hasattr(cfg, "dark_mode"))
        self.assertEqual(cfg.current_config["port"], 4000)
        # v1.6.12 移除「最近目录」：先备份再丢弃
        backups = list(self.path.parent.glob("config.recent-backup-*.json"))
        self.assertEqual(len(backups), 1, "旧历史必须先备份")
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8"))
                         ["recent_paths"], ["C:\\data"])
        self.assertIn("已备份", cfg.notice)
        self.assertFalse(hasattr(cfg, "recent_paths"))

    def test_saved_config_contains_version_and_roundtrips(self):
        cfg = AppConfig(profiles={"p": {"port": 6000}}, current="p",
                        current_config={"bind": "127.0.0.1"})
        save_config(cfg, self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["config_version"], CONFIG_VERSION)
        self.assertNotIn("notice", raw)
        self.assertNotIn("dark_mode", raw, "固定深色后不再持久化主题状态")
        self.assertNotIn("recent_paths", raw, "「最近目录」功能已删除")
        back = load_config(self.path)
        self.assertEqual(back.profiles["p"]["port"], 6000)
        self.assertEqual(back.notice, "")

    def test_bad_json_is_backed_up_and_defaults_used(self):
        self.path.write_text("{not json", encoding="utf-8")
        cfg = load_config(self.path)
        bad = self.path.with_name("config.bad.json")
        self.assertTrue(bad.is_file(), "坏配置必须备份到 config.bad.json")
        self.assertFalse(self.path.exists(), "坏文件应移走，避免下次继续读取")
        self.assertIsInstance(cfg, AppConfig)
        self.assertEqual(cfg.profiles, {})
        self.assertIn("已备份为 config.bad.json", cfg.notice)
        self.assertEqual(bad.read_text(encoding="utf-8"), "{not json")

    def test_config_version_too_new_is_backed_up_not_silently_downgraded(self):
        self._write({"config_version": CONFIG_VERSION + 1,
                     "profiles": {"x": {"port": 7000}}})
        cfg = load_config(self.path)
        self.assertTrue(self.path.with_name("config.bad.json").is_file())
        self.assertEqual(cfg.profiles, {}, "未知版本不能按当前 schema 猜测读取")
        self.assertIn("高于当前支持", cfg.notice)

    def test_bad_field_types_are_ignored_per_field(self):
        self._write({
            "config_version": CONFIG_VERSION,
            "profiles": {"ok": {"port": 6000}, "bad": "not-a-dict"},
            "recent_paths": ["a", 3],
            "dark_mode": "yes",
            "current_config": ["not-a-dict"],
        })
        cfg = load_config(self.path)
        self.assertEqual(list(cfg.profiles), ["ok"])
        self.assertEqual(cfg.profiles["ok"]["port"], 6000)
        self.assertFalse(hasattr(cfg, "dark_mode"), "已删除的主题字段应被忽略")
        self.assertEqual(cfg.current_config, {})
        self.assertIn("类型无效", cfg.notice)

    def test_recent_history_backed_up_once_then_dropped(self):
        """已落盘的「最近目录」：备份一次、日志提示、下次保存即从配置消失。"""
        self._write({"config_version": CONFIG_VERSION,
                     "recent_paths": ["C:\\中文 目录", "D:\\另一个"]})
        cfg = load_config(self.path)
        backups = list(self.path.parent.glob("config.recent-backup-*.json"))
        self.assertEqual(len(backups), 1)
        data = json.loads(backups[0].read_text(encoding="utf-8"))
        self.assertEqual(data["recent_paths"], ["C:\\中文 目录", "D:\\另一个"])
        self.assertIn(str(self.path), data["source"])
        self.assertIn("已备份", cfg.notice)
        save_config(cfg, self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("recent_paths", raw)
        load_config(self.path)  # 已无历史：不得重复备份
        self.assertEqual(len(list(self.path.parent.glob("config.recent-backup-*.json"))), 1)

    def test_save_is_atomic_and_keeps_old_file_on_failure(self):
        cfg = AppConfig(profiles={"p": {"port": 5000}})
        save_config(cfg, self.path)
        before = self.path.read_text(encoding="utf-8")

        with mock.patch("core.config.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                save_config(AppConfig(profiles={"q": {"port": 6000}}), self.path)

        self.assertEqual(self.path.read_text(encoding="utf-8"), before,
                         "写失败时不得破坏已有配置")
        leftovers = list(self.path.parent.glob(self.path.name + ".*.tmp"))
        self.assertEqual(leftovers, [], "失败后应清理临时文件")

    def test_server_config_from_dict_validates_each_field(self):
        cfg = ServerConfig.from_dict({
            "port": "abc", "bind": 123, "allow_delete": "no",
            "assets_dir": None, "custom_ui": False,
        })
        self.assertEqual(cfg.port, 5000)
        self.assertEqual(cfg.bind, "127.0.0.1")
        self.assertFalse(cfg.allow_delete)
        self.assertEqual(cfg.assets_dir, "")
        self.assertTrue(cfg.custom_ui, "历史 false 且无用户标记时应自愈")

    def test_legacy_single_bind_upgrades_to_binds(self):
        """旧配置只有 bind，读入后自动升级为单元素 binds，不能失效。"""
        cfg = ServerConfig.from_dict({"bind": "192.168.1.5", "port": 5000})
        self.assertEqual(cfg.effective_binds(), ["192.168.1.5"])
        d = cfg.to_dict()
        self.assertEqual(d["bind"], "192.168.1.5")
        self.assertEqual(d["binds"], ["192.168.1.5"])

    def test_multi_binds_roundtrip_and_dedupe(self):
        cfg = ServerConfig.from_dict({
            "bind": "192.168.1.5", "binds": ["10.0.0.7", "192.168.1.5"],
        })
        self.assertEqual(cfg.effective_binds(), ["10.0.0.7", "192.168.1.5"])
        self.assertEqual(cfg.bind, "10.0.0.7", "bind 同步为首个地址以供旧代码读取")
        back = ServerConfig.from_dict(cfg.to_dict())
        self.assertEqual(back.effective_binds(), ["10.0.0.7", "192.168.1.5"])

    def test_all_loopback_semantics(self):
        """所有地址均为回环才算「仅本机」；混入任意非回环即为对外。"""
        self.assertTrue(ServerConfig(binds=["127.0.0.1", "::1"]).all_loopback())
        self.assertFalse(ServerConfig(binds=["127.0.0.1", "10.0.0.7"]).all_loopback())
        self.assertFalse(ServerConfig(bind="", binds=[]).all_loopback(),
                         "空地址不算仅本机")

    def test_wildcard_cannot_combine_with_specific_address(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = ServerConfig(share_path=td, binds=["0.0.0.0", "192.168.1.5"])
            self.assertTrue(any("0.0.0.0" in e for e in cfg.validate()))
            self.assertEqual(
                ServerConfig(share_path=td, binds=["0.0.0.0"]).validate(), [])


if __name__ == "__main__":
    unittest.main()
