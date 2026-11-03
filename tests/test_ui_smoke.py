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

    def test_delete_profile_cancel_keeps_it(self):
        self.gui.app_cfg.profiles["待删"] = self.gui.current_config().to_dict()
        self.gui._reload_profiles("待删")
        with mock.patch.object(app_module.dialogs, "ask_yes_no",
                               return_value=False):
            self.gui._delete_profile()
        self.assertIn("待删", self.gui.app_cfg.profiles)
        self.gui.app_cfg.profiles.pop("待删", None)
        self.gui._reload_profiles("")

    def test_delete_profile_confirm_removes(self):
        self.gui.app_cfg.profiles["待删"] = self.gui.current_config().to_dict()
        self.gui._reload_profiles("待删")
        with mock.patch.object(app_module.dialogs, "ask_yes_no",
                               return_value=True) as asked:
            self.gui._delete_profile()
        self.assertNotIn("待删", self.gui.app_cfg.profiles)
        self.assertEqual(asked.call_args.kwargs["ok_text"], "删除")
        self.assertTrue(asked.call_args.kwargs["destructive"])
        self.assertFalse(asked.call_args.kwargs["default_ok"])

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
        orig_info = app_module.dialogs.show_info
        orig_log = self.gui._log
        app_module.webbrowser.open = lambda *a, **k: opened.append(a)
        app_module.dialogs.show_info = lambda parent, title, msg: infos.append((title, msg))
        self.gui._log = lambda line: logs.append(line)
        try:
            self.gui._open_browser()
        finally:
            app_module.webbrowser.open = orig_open
            app_module.dialogs.show_info = orig_info
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
            orig_err = app_module.dialogs.show_error
            orig_log = self.gui._log
            app_module.filedialog.asksaveasfilename = lambda **kw: td
            app_module.dialogs.show_error = lambda parent, title, msg: errors.append((title, msg))
            self.gui._log = lambda line: logs.append(line)
            try:
                self.gui._export_log()  # 目录不能直接 write_text
            finally:
                app_module.filedialog.asksaveasfilename = orig_save
                app_module.dialogs.show_error = orig_err
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

    def test_auth_config_and_command_redaction(self):
        """口令进入 -a 参数；日志/等效命令不得显示明文。"""
        try:
            self.gui.v_auth_user.set("alice")
            self.gui.v_auth_pass.set("s3cret")
            cfg = self.gui.current_config()
            args = cfg.to_args()
            self.assertIn("-a", args)
            # dufs 0.47 的 -a 必须带路径规则（user:pass@/path[:perm]）
            self.assertEqual(args[args.index("-a") + 1], "alice:s3cret@/:rw")
            line = cfg.command_line(binary="dufs.exe")
            self.assertIn("-a", line)
            self.assertIn("alice:***@/:rw", line)
            self.assertNotIn("s3cret", line)
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

    # ---------------- 本轮新增交互 ----------------
    def test_web_title_applies_and_persists(self):
        """网页标题保存到配置；空值回落官方标题，不影响 GUI 窗口标题。"""
        self.gui.v_web_title.set("实验室文件共享")
        self.gui._apply_web_meta()
        self.assertEqual(self.gui.app_cfg.current_config["web_title"],
                         "实验室文件共享")

        self.gui.v_web_title.set("   ")
        self.gui._apply_web_meta()
        self.assertEqual(self.gui.app_cfg.current_config["web_title"], "")

    def test_gui_window_title_is_fixed(self):
        """上一轮误做的 GUI 窗口标题设置必须已移除。"""
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('self.title("Dufs GUI")', src)
        self.assertNotIn("effective_window_title", src)
        self.assertNotIn("v_window_title", src)

    def test_qr_button_is_text_outline(self):
        """二维码入口是文字 + 描边按钮，尺寸与 32px 控件一致。"""
        from ui.roundrect import RoundButton

        btn = self.gui.btn_qr
        self.assertIsInstance(btn, RoundButton)
        self.assertEqual(btn.text, "二维码")
        self.assertEqual(int(btn.cget("width")), 74)
        self.assertEqual(int(btn.cget("height")), 32)
        self.assertEqual(btn["state"], "normal")

    def test_round_button_states(self):
        """hover / pressed / disabled 状态必须有独立预渲染图。"""
        btn = self.gui.btn_qr
        self.assertEqual(set(btn._images),
                         {"normal", "hover", "pressed", "disabled"})
        btn.set_state("disabled")
        self.assertEqual(btn["state"], "disabled")
        btn.set_state("normal")

    def test_failure_detail_hidden_until_error(self):
        from core.instances import InstanceState

        self.gui.manager.states = []
        self.gui._update_detail_area()
        self.assertFalse(self.gui.detail_holder.winfo_ismapped(),
                         "无失败时详情区必须整块收起")

        self.gui.manager.states = [InstanceState(
            bind="192.168.1.5", label="以太网", url="http://192.168.1.5:5000/",
            port=5000, status="失败", detail="端口被占用")]
        self.gui._update_detail_area()
        self.assertTrue(self.gui.detail_holder.winfo_ismapped())
        self.assertEqual(self.gui.btn_detail_toggle["text"], "收起")
        self.gui._toggle_detail()
        self.assertEqual(self.gui.btn_detail_toggle["text"], "展开")

        self.gui.manager.states = []
        self.gui._update_detail_area()
        self.assertFalse(self.gui.detail_holder.winfo_ismapped(),
                         "错误消除后应自动收起")

    def test_command_logged_on_start_and_redacted(self):
        """启动时把等效命令行写进运行日志，口令脱敏。"""
        with tempfile.TemporaryDirectory() as td:
            self.gui.v_path.set(td)
            self.gui.v_port.set(str(find_free_port(5300)))
            self.gui.bindlist.set_selection(["127.0.0.1"])
            self.gui.v_auth_user.set("alice")
            self.gui.v_auth_pass.set("s3cret")
            logs, started = [], []
            orig_log = self.gui._log
            orig_start = self.gui.manager.start

            def fake_start(*_a, **_kw):
                started.append(True)
                self.gui.manager.states = []
                return "汇总"

            self.gui._log = logs.append
            self.gui.manager.start = fake_start
            try:
                with mock.patch.object(dufsbin, "ensure_dufs",
                                       return_value=Path(sys.executable)):
                    self.gui._start()
            finally:
                self.gui._log = orig_log
                self.gui.manager.start = orig_start
                self.gui.v_auth_user.set("")
                self.gui.v_auth_pass.set("")
                self.gui.manager.states = []

            joined = "\n".join(logs)
            self.assertTrue(started)
            self.assertIn("[命令]", joined)
            self.assertIn("alice:***@/:rw", joined)
            self.assertNotIn("s3cret", joined, "日志不得泄露明文口令")

    def test_qr_payload_matches_shared_url(self):
        url = "http://192.168.1.5:5000/files/"
        win = app_module.dialogs.build_qr_window(self.gui, url)
        try:
            self.assertEqual(win.qr_payload, url)
            self.assertEqual(len(win.qr_matrix), 25)
            self.assertEqual(len(win.qr_matrix[0]), 25)
            self.assertEqual(win.qr_link.get(), url)
            self.assertIsNone(win.qr_selector)     # 单地址不显示选择器
        finally:
            win.destroy()

    def test_qr_selector_switches_immediately_from_cache(self):
        u1 = "http://10.4.240.16:5099/files/"
        u2 = "http://127.0.0.1:5099/files/"
        win = app_module.dialogs.build_qr_window(
            self.gui, u1, urls=[u1, u2])
        try:
            self.assertEqual(win.qr_choices, [u1, u2])
            self.assertIsNotNone(win.qr_selector)
            self.assertEqual(set(win.qr_cache), {u1, u2})
            self.assertEqual(win.qr_payload, u1)   # 默认主推第一项
            win.qr_var.set(u2)                     # 模拟下拉切换
            win.qr_select()
            self.assertEqual(win.qr_payload, u2)
            self.assertEqual(win.qr_link.get(), u2)
            self.assertEqual(win.qr_matrix, win.qr_cache[u2][0])
            self.assertEqual(set(win.qr_cache), {u1, u2})  # 复用缓存，不新增
        finally:
            win.destroy()

    def test_qr_urls_running_first_and_deduplicated(self):
        u1 = "http://10.4.240.16:5099/files/"
        u2 = "http://127.0.0.1:5099/files/"
        states = [mock.Mock(url=u1, running=True),
                  mock.Mock(url=u1, running=True),
                  mock.Mock(url=u2, running=False)]
        self.gui.manager.states = states
        try:
            self.assertEqual(self.gui._qr_urls(), [u1])
        finally:
            self.gui.manager.states = []

    def test_header_subtitle_removed(self):
        layout = (ROOT / "ui" / "layout.py").read_text(encoding="utf-8")
        self.assertNotIn("固定深色", layout)
        self.assertNotIn("轻量文件共享", layout)

    # ---------------- 辅助状态 / 网卡弹窗 ----------------
    def test_ip_summary_only_ips_and_loopback_last(self):
        from core.netif import ip_summary

        self.assertEqual(ip_summary(["10.4.240.16"]), "10.4.240.16")
        self.assertEqual(ip_summary(["127.0.0.1", "10.4.240.16"]),
                         "10.4.240.16 · 127.0.0.1")
        self.assertEqual(ip_summary(["10.4.240.16", "192.168.1.20"]),
                         "10.4.240.16 · 192.168.1.20")
        self.assertEqual(ip_summary(["10.4.240.16", "10.4.240.16"]),
                         "10.4.240.16")
        self.assertEqual(ip_summary([]), "")

    def test_aux_status_uses_config_ips_when_idle(self):
        from core.netif import NetIf

        items = [NetIf("以太网", "10.4.240.16", 4, "ethernet", True),
                 NetIf("回环", "127.0.0.1", 4, "loopback", True)]
        orig_items = list(self.gui.bindlist.items)
        orig_sel = self.gui.bindlist.selected()
        try:
            self.gui.bindlist.set_items(items, ["10.4.240.16"])
            self.gui._refresh_preview()
            self.assertEqual(self.gui._aux_full, "10.4.240.16")
            self.gui.bindlist.set_selection(["127.0.0.1", "10.4.240.16"])
            self.assertEqual(self.gui._aux_full, "10.4.240.16 · 127.0.0.1")
        finally:
            self.gui.bindlist.set_items(orig_items, orig_sel)

    def test_aux_status_uses_running_states(self):
        from core.instances import InstanceState

        states = [
            InstanceState(bind="127.0.0.1", label="回环",
                          url="http://127.0.0.1:5099/files/", port=5099,
                          status="运行中"),
            InstanceState(bind="10.4.240.16", label="以太网",
                          url="http://10.4.240.16:5099/files/", port=5099,
                          status="运行中"),
        ]
        self.gui.manager.states = states
        try:
            self.gui._render_status_rows()
            self.assertEqual(self.gui._aux_full, "10.4.240.16 · 127.0.0.1")
            self.assertNotIn("以太网", self.gui._aux_full)
        finally:
            self.gui.manager.states = []
            self.gui._refresh_preview()

    def test_fit_canvas_text_truncates_with_ellipsis(self):
        from ui.common import fit_canvas_text

        class FakeCanvas:
            text = ""

            def itemconfigure(self, _item, **kw):
                self.text = kw.get("text", self.text)

            def bbox(self, _item):
                return (0, 0, 7 * len(self.text), 12)

        canvas = FakeCanvas()
        shown, truncated = fit_canvas_text(
            canvas, 1, "10.4.240.16 · 192.168.1.20 · 127.0.0.1", 100)
        self.assertTrue(truncated)
        self.assertTrue(shown.endswith("…"))
        self.assertLessEqual(7 * len(shown), 100)
        shown2, truncated2 = fit_canvas_text(canvas, 1, "10.4.240.16", 200)
        self.assertFalse(truncated2)
        self.assertEqual(shown2, "10.4.240.16")

    def test_aux_status_after_stop_falls_back_to_config(self):
        from core.instances import InstanceState
        from core.netif import NetIf

        items = [NetIf("以太网", "10.4.240.16", 4, "ethernet", True),
                 NetIf("回环", "127.0.0.1", 4, "loopback", True)]
        orig_items = list(self.gui.bindlist.items)
        orig_sel = self.gui.bindlist.selected()
        self.gui.manager.states = [
            InstanceState(bind="127.0.0.1", label="回环",
                          url="http://127.0.0.1:5099/files/", port=5099,
                          status="已停止")]
        try:
            self.gui.bindlist.set_items(items, ["10.4.240.16", "127.0.0.1"])
            self.gui._render_status_rows()
            self.assertEqual(self.gui._aux_full, "10.4.240.16 · 127.0.0.1")
        finally:
            self.gui.manager.states = []
            self.gui.bindlist.set_items(orig_items, orig_sel)

    def test_copy_url_multi_idle_copies_all(self):
        from core.netif import NetIf

        items = [NetIf("以太网", "10.4.240.16", 4, "ethernet", True),
                 NetIf("回环", "127.0.0.1", 4, "loopback", True)]
        orig_items = list(self.gui.bindlist.items)
        orig_sel = self.gui.bindlist.selected()
        orig_path = self.gui.v_path.get()
        self.gui.v_port.set("5099")
        self.gui.v_prefix.set("files")
        try:
            with tempfile.TemporaryDirectory() as td:
                self.gui.v_path.set(td)
                self.gui.bindlist.set_items(items, ["10.4.240.16", "127.0.0.1"])
                self.gui.manager.states = []
                with mock.patch.object(self.gui, "clipboard_clear"), \
                        mock.patch.object(self.gui, "clipboard_append") as append:
                    self.gui._copy_url()
                append.assert_called_once_with(
                    "http://10.4.240.16:5099/files/\n"
                    "http://127.0.0.1:5099/files/")
        finally:
            self.gui.v_path.set(orig_path)
            self.gui.bindlist.set_items(orig_items, orig_sel)
            self.gui._refresh_preview()

    def test_bind_dialog_confirm_and_empty_disabled(self):
        from core.netif import NetIf

        items = [NetIf("以太网", "10.4.240.16", 4, "ethernet", True),
                 NetIf("回环", "127.0.0.1", 4, "loopback", True)]
        win = app_module.dialogs.build_bind_window(
            self.gui, items, ["10.4.240.16"])
        win.binds_list.set_selection(["10.4.240.16", "127.0.0.1"])
        self.assertEqual(win.binds_ok_button["state"], "normal")
        win.binds_confirm()
        self.assertEqual(win._result, ["10.4.240.16", "127.0.0.1"])

        empty = app_module.dialogs.build_bind_window(self.gui, items, [])
        self.assertEqual(empty.binds_ok_button["state"], "disabled")
        self.assertEqual(empty.binds_reason["text"], "至少选择一个")
        empty.binds_confirm()                 # 置灰时确认不得关闭窗口
        self.assertIsNone(getattr(empty, "_result", None))
        self.assertFalse(empty._binds_done)
        empty.destroy()

    def test_bind_dialog_height_adapts_without_scrollbar(self):
        from core.netif import NetIf

        def make(n):
            return [NetIf(f"网卡{i}", f"10.4.240.{i + 1}", 4, "ethernet", True)
                    for i in range(n)]

        five = app_module.dialogs.build_bind_window(self.gui, make(5), [])
        self.assertEqual(five._binds_rows, 5)
        self.assertFalse(five._binds_scroll)
        self.assertEqual(five._binds_size[1], 5 * 32 + 196)
        self.assertFalse(five.binds_list._scrollable)

        twenty = app_module.dialogs.build_bind_window(self.gui, make(20), [])
        self.assertEqual(twenty._binds_rows, 20)
        self.assertFalse(twenty._binds_scroll)
        self.assertEqual(twenty._binds_size[1], 20 * 32 + 196)
        self.assertFalse(twenty.binds_list._scrollable)

        many = app_module.dialogs.build_bind_window(self.gui, make(21), [])
        self.assertEqual(many._binds_rows, 20)
        self.assertTrue(many._binds_scroll)
        self.assertTrue(many.binds_list._scrollable)
        for win in (five, twenty, many):
            win.destroy()

    def test_bind_dialog_height_falls_back_on_small_screen(self):
        from core.netif import NetIf

        items = [NetIf(f"网卡{i}", f"10.4.240.{i % 250 + 1}", 4, "ethernet", True)
                 for i in range(20)]
        with mock.patch.object(app_module.dialogs, "work_area_height",
                               return_value=480):
            win = app_module.dialogs.build_bind_window(self.gui, items, [])
        self.assertLess(win._binds_rows, 20)
        self.assertTrue(win._binds_scroll)
        self.assertLessEqual(win._binds_size[1], 480 - 80)
        win.destroy()

    def test_bind_dialog_width_adapts_and_caps(self):
        from core.netif import NetIf

        short = [NetIf("回环", "127.0.0.1", 4, "loopback", True)]
        a = app_module.dialogs.build_bind_window(self.gui, short, [])
        self.assertEqual(a._binds_size[0], app_module.dialogs.BIND_MIN_W)

        long_name = "A" * 200
        long_items = [NetIf(long_name, "fd00:0000:0000:0000:0000:0000:0000:0001",
                            6, "virtual", True)]
        b = app_module.dialogs.build_bind_window(self.gui, long_items, [])
        self.assertEqual(b._binds_size[0], app_module.dialogs.BIND_MAX_W)
        self.assertTrue(b.binds_list._rows[0]["full_text"])
        for win in (a, b):
            win.destroy()

    def test_bind_dialog_hides_no_address_rows(self):
        from core.netif import NetIf

        items = [NetIf("以太网", "10.4.240.16", 4, "ethernet", True),
                 NetIf("蓝牙", "", 4, "virtual", False),
                 NetIf("占位", "", 4, "other", False),
                 NetIf("回环", "127.0.0.1", 4, "loopback", True)]
        win = app_module.dialogs.build_bind_window(self.gui, items, [])
        self.assertEqual([i.address for i in win.binds_list.items],
                         ["10.4.240.16", "127.0.0.1"])
        self.assertEqual(win._binds_rows, 2)
        self.assertFalse(win._binds_empty)
        win.destroy()

    def test_bind_dialog_empty_state(self):
        from core.netif import NetIf

        win = app_module.dialogs.build_bind_window(
            self.gui, [NetIf("蓝牙", "", 4, "virtual", False)], [])
        self.assertTrue(win._binds_empty)
        self.assertEqual(win._binds_rows, 0)
        self.assertEqual(win._binds_size[1], app_module.dialogs.BIND_CHROME_H)
        self.assertEqual(win.binds_ok_button._state, "disabled")
        self.assertEqual(win.binds_cancel(), "break")
        self.assertIsNone(getattr(win, "_result", None))
        win.destroy()

    def test_bind_dialog_cancel_x_and_esc(self):
        from core.netif import NetIf

        items = [NetIf("以太网", "10.4.240.16", 4, "ethernet", True),
                 NetIf("回环", "127.0.0.1", 4, "loopback", True)]
        a = app_module.dialogs.build_bind_window(
            self.gui, items, ["10.4.240.16"])
        a.binds_list.set_selection(["10.4.240.16", "127.0.0.1"])  # 未确认
        a.binds_cancel()
        self.assertIsNone(a._result)
        self.assertIs(a.binds_esc, a.binds_cancel)

        b = app_module.dialogs.build_bind_window(
            self.gui, items, ["10.4.240.16"])
        b.binds_list.set_selection(["10.4.240.16", "127.0.0.1"])
        b.destroy()                            # 模拟标题栏 ×
        self.assertIsNone(b._result)

    def test_bind_dialog_confirm_applies_preview(self):
        from core.netif import NetIf

        items = [NetIf("以太网", "10.4.240.16", 4, "ethernet", True),
                 NetIf("回环", "127.0.0.1", 4, "loopback", True)]
        orig_items = list(self.gui.bindlist.items)
        orig_sel = self.gui.bindlist.selected()
        orig_path = self.gui.v_path.get()
        self.gui.v_port.set("5099")
        self.gui.v_prefix.set("files")
        try:
            with tempfile.TemporaryDirectory() as td:
                self.gui.v_path.set(td)
                self.gui.bindlist.set_items(items, ["10.4.240.16"])
                with mock.patch.object(app_module.dialogs, "select_binds",
                                       return_value=["127.0.0.1"]):
                    self.gui._open_binds()
                self.assertEqual(self.gui.bindlist.selected(), ["127.0.0.1"])
                self.assertEqual(self.gui._aux_full, "127.0.0.1")
                self.assertEqual(self.gui.v_url.get(),
                                 "http://127.0.0.1:5099/files/")
                self.assertEqual(self.gui._qr_urls(),
                                 ["http://127.0.0.1:5099/files/"])

                with mock.patch.object(app_module.dialogs, "select_binds",
                                       return_value=None):
                    self.gui._open_binds()     # × / Esc：丢弃改动
                self.assertEqual(self.gui.bindlist.selected(), ["127.0.0.1"])
        finally:
            self.gui.v_path.set(orig_path)
            self.gui.bindlist.set_items(orig_items, orig_sel)




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
