"""GUI 冒烟测试：在 tkinter 桩上完整构造一次界面并触发主要交互。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DUFS_GUI_HOME"] = tempfile.mkdtemp(prefix="dufsgui-")

import tk_stub  # noqa: E402

tk_stub.install()

import app as app_module  # noqa: E402


class UiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gui = app_module.DufsGui()

    @classmethod
    def tearDownClass(cls):
        cls.gui.destroy()

    def test_build(self):
        self.assertTrue(self.gui.v_path.get() == "")

    def test_config_flow(self):
        with tempfile.TemporaryDirectory() as td:
            self.gui.v_path.set(td)
            self.gui.v_port.set(5000)
            self.gui.v_prefix.set("files")
            self.gui.v_delete.set(True)
            cfg = self.gui.current_config()
            self.assertIn("--path-prefix", cfg.to_args())
            self.assertIn("--allow-delete", cfg.to_args())
            self.assertEqual(cfg.validate(), [])
            self.assertTrue(cfg.url().endswith("/files/"))

    def test_profile_save_and_switch(self):
        with tempfile.TemporaryDirectory() as td:
            self.gui.v_path.set(td)
            self.gui.app_cfg.profiles["测试"] = self.gui.current_config().to_dict()
            self.gui._reload_profiles("测试")
            self.assertEqual(self.gui.v_profile.get(), "测试")
            self.gui._switch_profile()
            self.assertEqual(self.gui.v_path.get(), td)

    def test_start_stop_flow(self):
        """用一个会真正监听端口的假 dufs，跑通开启→运行→停止全流程。"""
        from core.netutil import find_free_port

        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "dufs"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import sys, http.server, socketserver\n"
                "args = sys.argv[1:]\n"
                "port = int(args[args.index('-p') + 1]) if '-p' in args else 5000\n"
                "print('fake dufs on', port, flush=True)\n"
                "class H(http.server.BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        self.send_response(200); self.end_headers()\n"
                "        self.wfile.write(b'ok')\n"
                "    def log_message(self, *a): pass\n"
                "socketserver.TCPServer(('127.0.0.1', port), H).serve_forever()\n",
                encoding="utf-8")
            fake.chmod(0o755)

            os.environ["DUFS_BIN"] = str(fake)
            self.gui.v_path.set(td)
            self.gui.v_bind.set("127.0.0.1")
            self.gui.v_port.set(find_free_port(5100))
            self.gui.v_prefix.set("files")

            self.gui.btn_start.invoke()
            self.assertTrue(self.gui.proc.running, "服务应处于运行状态")
            self.assertTrue(self.gui.v_status.get().startswith("运行中"))
            self.assertTrue(self.gui.v_url.get().endswith("/files/"))
            self.assertEqual(self.gui.btn_start["state"], "disabled")
            self.assertEqual(self.gui.btn_stop["state"], "normal")

            self.gui.btn_stop.invoke()
            self.assertFalse(self.gui.proc.running)
            self.assertEqual(self.gui.v_status.get(), "未启动")
            self.assertEqual(self.gui.btn_start["state"], "normal")
            os.environ.pop("DUFS_BIN", None)

    def test_advanced_popup(self):
        """高级设置应弹出独立窗口，而不是在主界面展开。"""
        self.gui.adv_win = None
        self.gui._open_advanced()
        win = self.gui.adv_win
        self.assertIsNotNone(win, "应创建弹窗")
        self.gui._open_advanced()      # 再次调用应复用，不新建
        self.assertIs(self.gui.adv_win, win)
        self.gui.adv_win = None

    def test_theme_toggle(self):
        before = self.gui.dark
        self.gui._toggle_theme()
        self.assertNotEqual(before, self.gui.dark)
        self.gui._toggle_theme()

    def test_advanced_popup_sized_to_content(self):
        """弹窗高度必须按内容实测，不能写死——否则新增行会被裁切。"""
        self.gui.adv_win = None
        self.gui._open_advanced()
        win = self.gui.adv_win
        g = win._geometry          # 形如 "744x680+100+50"
        w, h = (int(x) for x in g.split("+")[0].split("x"))
        # 桩里 reqheight=720，窗口至少要装得下内容（+上下留白）
        self.assertGreaterEqual(h, 720, f"高度 {h} 装不下内容 720，会被裁切")
        self.assertGreaterEqual(w, 620, "宽度过小")
        self.gui.adv_win = None

    def test_advanced_popup_clamped_to_screen(self):
        """屏幕很矮时不能超出屏幕，超出的部分靠滚动而不是裁掉。"""
        self.gui.adv_win = None
        self.gui._open_advanced()
        win = self.gui.adv_win
        g = win._geometry
        w, h = (int(x) for x in g.split("+")[0].split("x"))
        self.assertLessEqual(h, 1080 - 120, "高度超过屏幕可用区")
        self.gui.adv_win = None

    def test_custom_ui_toggle(self):
        """网页美化界面开关应影响命令行是否带 --assets。"""
        self.gui.v_custom_ui.set(True)
        self.assertIn("--assets", self.gui.current_config().to_args())
        self.gui.v_custom_ui.set(False)
        self.assertNotIn("--assets", self.gui.current_config().to_args())
        self.gui.v_custom_ui.set(True)

    def test_command_preview(self):
        self.gui._refresh_preview()
        self.assertIn("等效命令", self.gui.lbl_cmd["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
