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
        self.assertEqual(cfg.recent_paths, ["C:\\data"])
        self.assertTrue(cfg.dark_mode)  # 类型不符 -> 默认 True
        self.assertEqual(cfg.current_config["port"], 4000)

    def test_saved_config_contains_version_and_roundtrips(self):
        cfg = AppConfig(profiles={"p": {"port": 6000}}, current="p",
                        recent_paths=["/a"], dark_mode=False,
                        current_config={"bind": "127.0.0.1"})
        save_config(cfg, self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["config_version"], CONFIG_VERSION)
        self.assertNotIn("notice", raw)
        back = load_config(self.path)
        self.assertEqual(back.profiles["p"]["port"], 6000)
        self.assertFalse(back.dark_mode)
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
        self.assertEqual(cfg.recent_paths, ["a"])
        self.assertTrue(cfg.dark_mode)
        self.assertEqual(cfg.current_config, {})
        self.assertIn("类型无效", cfg.notice)

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


if __name__ == "__main__":
    unittest.main()
