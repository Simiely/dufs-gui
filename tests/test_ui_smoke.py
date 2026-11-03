"""GUI 冒烟测试：在 tkinter 桩上完整构造一次界面并触发主要交互。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DUFS_GUI_HOME"] = tempfile.mkdtemp(prefix="dufsgui-")

import tk_stub  # noqa: E402

tk_stub.install()

import app as app_module  # noqa: E402
from core import dufsbin  # noqa: E402
from core.netutil import find_free_port  # noqa: E402


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

    def test_port_input_validation(self):
        """清空/非数字/越界时不得抛 TclError，只返回可读提示。"""
        for raw in ("", "abc", "70000", "0"):
            self.gui.v_port.set(raw)
            self.gui._refresh_preview()  # trace 路径不应抛异常
            port, msg = self.gui.port_from_form()
            self.assertIsNone(port, f"{raw!r} 不应解析成合法端口")
            self.assertTrue(msg, f"{raw!r} 应给出可读提示")
        self.gui.v_port.set("5000")
        port, msg = self.gui.port_from_form()
        self.assertEqual(port, 5000)
        self.assertEqual(msg, "")

    def test_profile_save_and_switch(self):
        with tempfile.TemporaryDirectory() as td:
            self.gui.v_path.set(td)
            self.gui.app_cfg.profiles["测试"] = self.gui.current_config().to_dict()
            self.gui._reload_profiles("测试")
            self.assertEqual(self.gui.v_profile.get(), "测试")
            self.gui._switch_profile()
            self.assertEqual(self.gui.v_path.get(), td)

    def test_empty_selection_blocks_start_without_dialog(self):
        """全部未选：不启动、不弹窗，只给一行状态提示。"""
        self.gui.bindlist.set_selection([])
        self.gui._start()
        self.assertEqual(self.gui.v_status.get(), "请至少选择一个共享网卡")
        self.assertFalse(self.gui.manager.running)
        self.gui.bindlist.set_selection(["127.0.0.1"])

    def test_wildcard_is_exclusive(self):
        """0.0.0.0 与具体地址互斥；勾「仅本机」可与其他网卡共存。"""
        items = self.gui.bindlist.items
        wildcard = next(i for i in items if i.is_wildcard)
        loopback = next(i for i in items if i.address == "127.0.0.1")
        self.gui.bindlist.set_selection([wildcard.address, loopback.address])
        self.assertEqual(self.gui.bindlist.selected(), [wildcard.address],
                         "恢复配置时通配地址必须独占")

        self.gui.bindlist.set_selection([loopback.address])
        index = self.gui.bindlist.items.index(wildcard)
        self.gui.bindlist._toggle(index)
        self.assertEqual(self.gui.bindlist.selected(), [wildcard.address])

        index = self.gui.bindlist.items.index(loopback)
        self.gui.bindlist._toggle(index)
        self.assertEqual(self.gui.bindlist.selected(), [loopback.address],
                         "仅本机勾选时应自动取消通配，不互斥")

    def test_keyboard_navigation_and_space_toggle(self):
        """方向键移动焦点、空格切换勾选。"""
        self.gui.bindlist.set_selection(["127.0.0.1"])
        self.gui.bindlist._focus_index = 0
        self.gui.bindlist._move(1)
        self.assertEqual(self.gui.bindlist._focus_index, 1)

        target = next(i for i, item in enumerate(self.gui.bindlist.items)
                      if item.bindable and item.address != "127.0.0.1")
        self.gui.bindlist._focus_index = target
        before = set(self.gui.bindlist.selected())
        self.gui.bindlist._toggle(target)
        after = set(self.gui.bindlist.selected())
        self.assertNotEqual(before, after)
        self.gui.bindlist.set_selection(["127.0.0.1"])

    def test_start_stop_flow(self):
        """用一个会真正监听端口的假 dufs，跑通开启→运行→停止全流程。

        用当前 Python 解释器直接执行 .py 假服务，而不是依赖 shebang 脚本：
        Windows 的 Popen 不能直接执行无扩展名的文本文件，这条测试以前只在
        POSIX 上成立。ensure_dufs 在这里注入为 sys.executable。
        """
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "fake_dufs.py"
            fake.write_text(
                "import sys, http.server, socketserver\n"
                "args = sys.argv[1:]\n"
                "port = int(args[args.index('-p') + 1]) if '-p' in args else 5000\n"
                "host = args[args.index('-b') + 1] if '-b' in args else '127.0.0.1'\n"
                "print('fake dufs on', host, port, flush=True)\n"
                "class H(http.server.BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        self.send_response(200); self.end_headers()\n"
                "        self.wfile.write(b'ok')\n"
                "    def log_message(self, *a): pass\n"
                "if ':' in host:\n"
                "    class S(socketserver.ThreadingTCPServer):\n"
                "        address_family = __import__('socket').AF_INET6\n"
                "else:\n"
                "    S = socketserver.ThreadingTCPServer\n"
                "S((host, port), H).serve_forever()\n",
                encoding="utf-8")

            self.gui.v_path.set(str(fake))
            self.gui.bindlist.set_selection(["127.0.0.1"])
            self.gui.v_port.set(str(find_free_port(5100)))
            self.gui.v_prefix.set("files")

            with mock.patch.object(dufsbin, "ensure_dufs",
                                   return_value=Path(sys.executable)):
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

    def test_open_browser_when_idle_has_feedback(self):
        """未运行点「打开网页」不能静默无反应。"""
        self.gui._stop(silent=True)
        opened = []
        infos = []
        logs = []
        orig_open = app_module.webbrowser.open
        orig_info = app_module.messagebox.showinfo
        orig_log = self.gui._log
        app_module.webbrowser.open = lambda *a, **k: opened.append(a)
        app_module.messagebox.showinfo = lambda title, msg: infos.append((title, msg))
        self.gui._log = lambda line: logs.append(line)
        try:
            self.gui._open_browser()
        finally:
            app_module.webbrowser.open = orig_open
            app_module.messagebox.showinfo = orig_info
            self.gui._log = orig_log
        self.assertEqual(opened, [], "未运行时不应打开浏览器")
        self.assertTrue(infos and "服务未运行" in infos[-1][0])
        self.assertTrue(any("服务未运行" in x for x in logs))

    def test_export_log_failure_is_reported(self):
        """保存路径不可写时要给可读提示，不能抛到回调层。"""
        with tempfile.TemporaryDirectory() as td:
            errors = []
            logs = []
            orig_save = app_module.filedialog.asksaveasfilename
            orig_err = app_module.messagebox.showerror
            orig_log = self.gui._log
            app_module.filedialog.asksaveasfilename = lambda **kw: td
            app_module.messagebox.showerror = lambda title, msg: errors.append((title, msg))
            self.gui._log = lambda line: logs.append(line)
            try:
                self.gui._export_log()  # 目录不能直接 write_text
            finally:
                app_module.filedialog.asksaveasfilename = orig_save
                app_module.messagebox.showerror = orig_err
                self.gui._log = orig_log
            self.assertTrue(errors and "导出失败" in errors[-1][0])
            self.assertTrue(any("日志导出失败" in x for x in logs))

    def test_health_status_transitions(self):
        """运行中 -> 无响应 -> 恢复 -> 已退出，全部经队列在主线程更新。"""
        from core.instances import InstanceState

        class FakeProc:
            pid = 123
            running = True

            def stop(self):
                self.running = False

            def recent_output(self, _n=0):
                return ""

        state = InstanceState(
            bind="127.0.0.1", label="仅本机",
            url="http://127.0.0.1:5000/", port=5000,
            status="运行中", process=FakeProc())
        self.gui.manager.states = [state]
        self.gui.log_queue.put(("health_fail", "127.0.0.1|timed out"))
        self.gui._drain_queues()
        self.assertIn("无响应", self.gui.v_status.get())
        self.assertEqual(self.gui.dot.cget("fg"), self.gui.colors["warn"])

        self.gui.log_queue.put(("health_ok", "127.0.0.1|HTTP 200"))
        self.gui._drain_queues()
        self.assertTrue(self.gui.v_status.get().startswith("运行中"))
        self.assertEqual(self.gui.dot.cget("fg"), self.gui.colors["ok"])

        state.process.running = False
        self.gui.log_queue.put(("exit", "127.0.0.1"))
        self.gui._drain_queues()
        self.assertEqual(self.gui.v_status.get(), "已退出")
        self.gui.manager.states = []

    def test_advanced_popup(self):
        """高级设置应弹出独立窗口，而不是在主界面展开。"""
        self.gui.adv_win = None
        self.gui._open_advanced()
        win = self.gui.adv_win
        self.assertIsNotNone(win, "应创建弹窗")
        self.gui._open_advanced()      # 再次调用应复用，不新建
        self.assertIs(self.gui.adv_win, win)
        self.gui.adv_win = None

    def test_theme_is_fixed_dark(self):
        """应用固定深色：不得有切换入口、隐藏状态或浅色分支。"""
        from core.theme import DARK
        self.assertFalse(hasattr(self.gui, "btn_theme"), "不应保留主题切换按钮")
        self.assertFalse(hasattr(self.gui, "_toggle_theme"), "不应保留切换方法")
        self.assertFalse(hasattr(self.gui, "dark"), "不应保留深浅状态开关")
        self.assertEqual(self.gui.colors["bg"], DARK["bg"])

    def test_advanced_popup_big_enough(self):
        """弹窗必须足够大：内容约 700px 高，小于它就一定被裁切。

        注意：不能靠 winfo_reqheight() 自适应 —— 窗口处于 withdrawn 状态时
        Tk 不计算子控件几何，返回值可能是 1，算出的高度反而更小、裁得更狠。
        """
        self.gui.adv_win = None
        self.gui._open_advanced()
        win = self.gui.adv_win
        w, h = (int(x) for x in win._geometry.split("+")[0].split("x"))
        self.assertGreaterEqual(h, 520, f"高度 {h} 过小，内容会被裁切")
        self.assertGreaterEqual(w, 640, "宽度过小")
        self.gui.adv_win = None

    def test_popup_size_not_from_measurement(self):
        """源码不得依赖实测高度定尺寸（withdrawn 时不可靠）。"""
        src = "\n".join(
            p.read_text(encoding="utf-8")
            for p in [ROOT / "app.py", ROOT / "ui" / "advanced.py"])
        self.assertNotIn("req_h", src, "弹窗尺寸不应依赖实测高度")

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

    def test_auth_config_and_preview_redaction(self):
        """高级设置里的口令应进入 -a 参数，但预览不得显示明文。"""
        try:
            self.gui.v_auth_user.set("alice")
            self.gui.v_auth_pass.set("s3cret")
            cfg = self.gui.current_config()
            args = cfg.to_args()
            self.assertIn("-a", args)
            # dufs 0.47 的 -a 必须带路径规则（user:pass@/path[:perm]）
            self.assertEqual(args[args.index("-a") + 1], "alice:s3cret@/:rw")
            self.gui._refresh_preview()
            self.assertNotIn("s3cret", self.gui.lbl_cmd["text"])
            self.assertIn("alice:***", self.gui.lbl_cmd["text"])
        finally:
            self.gui.v_auth_user.set("")
            self.gui.v_auth_pass.set("")
            self.gui._refresh_preview()

    def test_advanced_popup_password_masked(self):
        self.gui.adv_win = None
        self.gui._open_advanced()
        try:
            self.assertEqual(self.gui.ent_auth_pass.cget("show"), "*")
        finally:
            self.gui.adv_win = None

    def test_command_preview(self):
        self.gui._refresh_preview()
        self.assertIn("等效命令", self.gui.lbl_cmd["text"])


class SkinFallbackPersistenceTest(unittest.TestCase):
    """端到端覆盖“降级后仍会执行统一保存”的路径。

    多实例改造后降级发生在 InstanceManager 内部：首次带 --assets 未就绪，
    自动用不带皮肤的参数重试；这里用假进程验证重试流程与配置写盘。
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="dufsgui-fallback-")
        self.share = tempfile.mkdtemp(prefix="dufsgui-share-")
        self.env_patch = mock.patch.dict(
            os.environ, {"DUFS_GUI_HOME": self.home, "DUFS_BIN": ""})
        self.env_patch.start()
        self.ensure_patch = mock.patch.object(
            dufsbin, "ensure_dufs", return_value=Path(sys.executable))
        self.ensure_patch.start()
        self.gui = app_module.DufsGui()
        self.gui.bindlist.set_selection(["127.0.0.1"])
        self.calls = []

        calls = self.calls

        class FakeProc:
            def __init__(self, log_queue, job=None, prefix="", tag=""):
                self.running = False
                self.recent = []

            def start(self, binary, args, cwd=None):
                calls.append(list(args))

            def wait_ready(self, port, host, timeout=8):
                ok = "--assets" not in calls[-1]
                self.running = ok
                return ok

            def stop(self):
                self.running = False

            def recent_output(self, _n=0):
                return "带皮肤启动失败"

        self.proc_patch = mock.patch("core.instances.DufsProcess", FakeProc)
        self.proc_patch.start()

    def tearDown(self):
        self.proc_patch.stop()
        self.gui.destroy()
        self.ensure_patch.stop()
        self.env_patch.stop()
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.share, ignore_errors=True)

    def test_fallback_saves_but_keeps_custom_ui(self):
        self.gui.v_path.set(self.share)
        self.gui.v_port.set(find_free_port(5200))
        self.gui.v_custom_ui.set(True)
        self.gui._start()

        self.assertEqual(len(self.calls), 2, "应发生一次带皮肤启动 + 一次降级重试")
        self.assertIn("--assets", self.calls[0])
        self.assertNotIn("--assets", self.calls[1])

        cfg_path = Path(self.home) / "config.json"
        self.assertTrue(cfg_path.is_file(), "降级后仍应执行统一保存动作")
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))["current_config"]
        self.assertTrue(saved["custom_ui"], "运行时降级不得把 false 写进配置")
        self.assertNotIn("_user_set_custom_ui", saved,
                         "运行时降级不得留下“用户主动关闭”的标记")
        self.assertTrue(self.gui.v_custom_ui.get(),
                        "界面变量应保持原值，供下次启动继续尝试皮肤")


if __name__ == "__main__":
    unittest.main(verbosity=2)
