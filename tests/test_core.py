"""核心逻辑单测（不依赖 tkinter / dufs 二进制）。

运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import queue
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys_path = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(sys_path))

REPO = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO))

import core as core_pkg  # noqa: E402
from core import crashlog, dufsbin, server  # noqa: E402
from core.dufsbin import verify_assets_dir, webui_dir  # noqa: E402
from core.config import (AppConfig, ServerConfig, load_config,  # noqa: E402
                         normalize_prefix, save_config)
from core.netutil import find_free_port, port_in_use  # noqa: E402


class PrefixTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_prefix("files"), "/files")
        self.assertEqual(normalize_prefix("/files/"), "/files")
        self.assertEqual(normalize_prefix(""), "")
        self.assertEqual(normalize_prefix("  a/b "), "/a/b")


class UiRegressionTest(unittest.TestCase):
    """源码级回归：防止已修的显示 bug 再回来。"""

    def test_no_hardcoded_wraplength(self):
        """写死 wraplength 会让等效命令换行错乱（曾被截成 `--e`）。"""
        src = (REPO / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("wraplength=760", src)
        self.assertNotIn("wraplength=", src.replace("wraplength=max", ""),
                         "命令预览标签不得写死 wraplength")

    def test_checkbutton_not_ttk(self):
        """复选框必须是 tk.Checkbutton + indicatoron=False，不能靠 ttk 配色。

        ttk 的 indicatorcolor 会**静默失效**（不报错、就是没效果），
        这正是之前"改了但界面没变化"的根因。
        """
        src = (REPO / "core" / "theme.py").read_text(encoding="utf-8")
        self.assertIn("class ThemedCheckbutton(tk.Checkbutton)", src)
        self.assertIn("indicatoron=False", src)
        self.assertIn("selectimage=", src)

    def test_app_uses_themed_checkbutton(self):
        app = (REPO / "app.py").read_text(encoding="utf-8")
        self.assertIn("ThemedCheckbutton(", app)
        self.assertNotIn("cb = ttk.Checkbutton(", app)

    def test_checkbox_contrast_meets_wcag(self):
        """未选中描边 vs 面板、白勾 vs 选中底，都要 >=3:1 才看得清。"""
        from core.theme import DARK, LIGHT

        def lum(h):
            h = h.lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
            f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

        def cr(a, b):
            la, lb = lum(a), lum(b)
            return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

        for c in (DARK, LIGHT):
            self.assertGreaterEqual(
                cr(c["check_border"], c["panel"]), 3.0,
                f"未选中描边 {c['check_border']} vs 面板 {c['panel']} 对比度不足")
            self.assertGreaterEqual(
                cr("#ffffff", c["check_on"]), 3.0,
                f"白勾 on {c['check_on']} 对比度不足")

    def test_tick_pixels_inside_box(self):
        """对勾像素必须落在 16x16 方框内部（1..14），否则会画到框外。"""
        from core.theme import _TICK
        for x, y in _TICK:
            self.assertTrue(1 <= x <= 13, f"对勾像素 x={x} 越界")
            self.assertTrue(1 <= y <= 13, f"对勾像素 y={y} 越界")
            self.assertTrue(1 <= y + 1 <= 14, f"加粗后的 y={y+1} 越界")


class BatEncodingTest(unittest.TestCase):
    """.bat 必须纯 ASCII：Windows 中文 cmd 按 GBK 读，UTF-8 中文会被当命令执行。

    这条不是理论风险——它真实发生过两次，其中一次就是我在修 bug 时
    顺手写了中文 rem 注释又踩了一遍。必须有测试拦着。
    """

    def test_all_bat_are_ascii(self):
        bats = list(REPO.glob("*.bat"))
        self.assertTrue(bats, "没找到任何 bat 文件")
        for f in bats:
            data = f.read_bytes()
            bad = [b for b in data if b >= 128]
            self.assertFalse(bad, f"{f.name} 含 {len(bad)} 个非 ASCII 字节")


class VersionTest(unittest.TestCase):
    """版本号必须单一真源，且被 CHANGELOG 记录。"""

    def test_version_is_semver(self):
        self.assertRegex(core_pkg.APP_VERSION, r"^\d+\.\d+\.\d+$",
                         "版本号应为 主.次.修订 形式")

    def test_changelog_has_current_version(self):
        txt = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"[{core_pkg.APP_VERSION}]", txt,
                      f"CHANGELOG 缺少 {core_pkg.APP_VERSION} 的版本节")

    def test_app_uses_shared_version(self):
        """app.py 不得自己写死版本号，必须引用 core.APP_VERSION。"""
        src = (REPO / "app.py").read_text(encoding="utf-8")
        self.assertIn("from core import APP_VERSION", src)
        self.assertNotIn('APP_VERSION = "', src,
                        "app.py 里仍有字面量版本号，应改为引用 core")

    def test_spec_reads_version_from_core(self):
        spec = (REPO / "DufsGui.spec").read_text(encoding="utf-8")
        self.assertIn("_read_version", spec, "spec 应从 core 读版本号")


class ConfigTest(unittest.TestCase):
    def test_args_and_roundtrip(self):
        cfg = ServerConfig(share_path="D:/share", port=8080, path_prefix="files",
                           allow_delete=True, allow_upload=True, hidden=".git,*.log")
        args = cfg.to_args()
        self.assertIn("--path-prefix", args)
        self.assertIn("/files", args)
        self.assertIn("--allow-delete", args)
        self.assertIn("--hidden", args)
        self.assertTrue(args[0].endswith("share"))

        back = ServerConfig.from_dict(cfg.to_dict())
        self.assertEqual(back.to_args(), args)

    def test_readonly_by_default(self):
        cfg = ServerConfig(share_path="/tmp", allow_upload=False, allow_search=False,
                           allow_archive=False)
        args = cfg.to_args()
        self.assertNotIn("--allow-delete", args)
        self.assertNotIn("--allow-upload", args)
        self.assertNotIn("--allow-search", args)

    def test_validate(self):
        self.assertTrue(ServerConfig().validate())
        cfg = ServerConfig(share_path="/tmp", tls_cert="/nope.crt")
        self.assertTrue(any("私钥" in e or "证书" in e for e in cfg.validate()))
        cfg2 = ServerConfig(share_path="/tmp", port=70000)
        self.assertTrue(any("端口" in e for e in cfg2.validate()))

    def test_url_and_command(self):
        cfg = ServerConfig(share_path="/tmp", bind="192.168.1.9", port=5000,
                           path_prefix="files")
        self.assertEqual(cfg.url(), "http://192.168.1.9:5000/files/")
        self.assertIn("--path-prefix", cfg.command_line())

    def test_ipv6_url_is_bracketed(self):
        """IPv6 字面量在 URL 里必须带方括号，否则生成非法地址。"""
        cfg = ServerConfig(share_path="/tmp", bind="::1", port=5000)
        self.assertEqual(cfg.url(), "http://[::1]:5000/")
        cfg.bind = "[::1]"
        self.assertEqual(cfg.url(), "http://[::1]:5000/")

    def test_health_url_uses_loopback_and_prefix(self):
        cfg = ServerConfig(share_path="/tmp", bind="0.0.0.0", port=5000,
                           path_prefix="files")
        self.assertEqual(cfg.health_url(),
                         "http://127.0.0.1:5000/files/__dufs__/health")
        cfg.bind = "::"
        self.assertEqual(cfg.health_url(),
                         "http://[::1]:5000/files/__dufs__/health")
        cfg.bind = "::1"
        cfg.path_prefix = ""
        self.assertEqual(cfg.health_url(),
                         "http://[::1]:5000/__dufs__/health")

    def test_persist(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.json"
            cfg = AppConfig(dark_mode=True, recent_paths=["/a"], profiles={"x": {"port": 1}})
            save_config(cfg, p)
            back = load_config(p)
            self.assertEqual(back.recent_paths, ["/a"])
            self.assertEqual(back.profiles["x"]["port"], 1)


class AuthConfigTest(unittest.TestCase):
    """P0-2 访问口令：参数生成、脱敏、非回环默认拒绝。"""

    def test_args_include_auth_and_command_line_redacts(self):
        cfg = ServerConfig(share_path="/tmp", auth_user="alice",
                           auth_pass="s3cret:with:colon")
        args = cfg.to_args()
        i = args.index("-a")
        # dufs 0.47 要求 user:pass@/path；裸 user:pass 会被拒绝启动
        self.assertEqual(args[i + 1], "alice:s3cret:with:colon@/:rw")
        line = cfg.command_line()
        self.assertIn("-a", line)
        self.assertIn("alice:***@/:rw", line)
        self.assertNotIn("s3cret", line, "命令预览不得泄露口令")

    def test_validate_rejects_at_slash_in_credentials(self):
        """口令里出现 "@/"" 会破坏 dufs 的 user:pass@/path 解析，必须拒绝。"""
        for user, pwd in (("alice@/x", "pw"), ("alice", "pw@/x")):
            cfg = ServerConfig(share_path="/tmp", auth_user=user, auth_pass=pwd)
            self.assertTrue(any("@/" in e for e in cfg.validate()), (user, pwd))

    def test_auth_roundtrip(self):
        cfg = ServerConfig(share_path="/tmp", auth_user="alice", auth_pass="pw")
        back = ServerConfig.from_dict(cfg.to_dict())
        self.assertEqual(back.to_args(), cfg.to_args())
        self.assertNotIn("pw", back.command_line())

    def test_validate_requires_both_parts(self):
        errs = ServerConfig(share_path="/tmp", auth_user="alice").validate()
        self.assertTrue(any("同时" in e for e in errs), errs)
        errs = ServerConfig(share_path="/tmp", auth_pass="pw").validate()
        self.assertTrue(any("同时" in e for e in errs), errs)

    def test_validate_rejects_colon_in_username(self):
        errs = ServerConfig(share_path="/tmp", auth_user="a:b",
                            auth_pass="pw").validate()
        self.assertTrue(any("冒号" in e for e in errs), errs)

    def test_validate_rejects_newline_in_credentials(self):
        cases = (("auth_user", "ali\nce", "pw"),
                 ("auth_pass", "alice", "p\nw"))
        for field, user, pwd in cases:
            cfg = ServerConfig(share_path="/tmp", auth_user=user, auth_pass=pwd)
            self.assertTrue(any("换行" in e for e in cfg.validate()), field)

    def test_non_loopback_without_auth_is_denied(self):
        cfg = ServerConfig(share_path="/tmp", bind="0.0.0.0")
        errs = cfg.validate()
        self.assertTrue(any("回环" in e and "口令" in e for e in errs), errs)
        # 拒绝必须发生在启动前，而不是只弹一个可忽略的警告
        self.assertTrue(errs)

    def test_non_loopback_with_auth_is_allowed(self):
        cfg = ServerConfig(share_path="/tmp", bind="0.0.0.0",
                           auth_user="alice", auth_pass="pw")
        self.assertFalse(any("回环" in e for e in cfg.validate()))

    def test_loopback_aliases_allow_no_auth(self):
        for bind in ("127.0.0.1", "localhost", "::1", "[::1]", "127.0.0.2"):
            with self.subTest(bind=bind):
                cfg = ServerConfig(share_path="/tmp", bind=bind)
                self.assertFalse(any("回环" in e for e in cfg.validate()), bind)

    def test_unknown_hostname_is_treated_as_non_loopback(self):
        cfg = ServerConfig(share_path="/tmp", bind="intranet-host")
        self.assertTrue(any("回环" in e for e in cfg.validate()))

    def test_empty_bind_is_rejected(self):
        errs = ServerConfig(share_path="/tmp", bind="").validate()
        self.assertTrue(any("不能为空" in e for e in errs), errs)

    def test_redaction_survives_share_path_named_dash_a(self):
        """共享目录名恰好是 "-a" 时，也不能漏掉真正的口令。"""
        cfg = ServerConfig(share_path="-a", bind="127.0.0.1",
                           auth_user="alice", auth_pass="topsecret")
        line = cfg.command_line()
        self.assertNotIn("topsecret", line)
        self.assertIn("alice:***", line)


class PortTest(unittest.TestCase):
    def test_in_use_and_free(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            self.assertTrue(port_in_use(port))
            # 连续探测必须稳定：Windows 上 connect_ex 第二次会失效，
            # 导致 find_free_port() 又把同一个端口推荐回来。
            self.assertTrue(port_in_use(port), "连续探测结果应稳定")
            self.assertNotEqual(find_free_port(port), port)
        finally:
            srv.close()

    def test_ipv6_in_use_and_free(self):
        try:
            srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            srv.bind(("::1", 0))
            srv.listen(1)
        except OSError:
            self.skipTest("本机不支持 IPv6")
        port = srv.getsockname()[1]
        try:
            self.assertTrue(port_in_use(port, "::1"))
            self.assertTrue(port_in_use(port, "[::1]"), "应兼容方括号写法")
            self.assertNotEqual(find_free_port(port, "::1"), port)
        finally:
            srv.close()


class TclTkReportTest(unittest.TestCase):
    """selftest 的 Tcl/Tk 目录判断：兼容 PyInstaller 新/旧布局与源码运行。"""

    def _frozen_report(self, root: Path) -> str:
        with mock.patch.object(sys, "_MEIPASS", str(root), create=True), \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.dict(os.environ, {"TCL_LIBRARY": "", "TK_LIBRARY": ""}):
            return crashlog.tcl_tk_report()

    def test_pyinstaller6_layout_is_reported_present(self):
        """PyInstaller 6.x 使用 _tcl_data / _tk_data，旧逻辑会误报缺失。"""
        with tempfile.TemporaryDirectory() as td:
            tcl = Path(td) / "_tcl_data"
            tk = Path(td) / "_tk_data"
            tcl.mkdir()
            tk.mkdir()
            (tcl / "init.tcl").write_text("# fake", encoding="utf-8")
            (tk / "tk.tcl").write_text("# fake", encoding="utf-8")

            report = self._frozen_report(Path(td))
            self.assertIn("tcl/tk 模式  : 打包运行", report)
            self.assertIn("tcl        : 存在", report)
            self.assertIn("tk         : 存在", report)
            self.assertNotIn("缺失", report)

    def test_legacy_layout_is_reported_present(self):
        """旧版本可能用 _MEIPASS/tcl、_MEIPASS/tk，也要能识别。"""
        with tempfile.TemporaryDirectory() as td:
            tcl = Path(td) / "tcl"
            tk = Path(td) / "tk"
            tcl.mkdir()
            tk.mkdir()
            (tcl / "init.tcl").write_text("# fake", encoding="utf-8")
            (tk / "tk.tcl").write_text("# fake", encoding="utf-8")

            report = self._frozen_report(Path(td))
            self.assertIn("tcl        : 存在", report)
            self.assertIn("tk         : 存在", report)

    def test_missing_marker_is_still_reported(self):
        """目录存在但缺 init.tcl / tk.tcl 时仍必须报缺失，不能一律显示 OK。"""
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "_tcl_data").mkdir()
            (Path(td) / "_tk_data").mkdir()

            report = self._frozen_report(Path(td))
            self.assertEqual(report.count("缺失"), 2, report)

    def test_source_mode_does_not_claim_frozen(self):
        """源码运行没有 _MEIPASS，不能按打包目录结构判断。"""
        with mock.patch.object(sys, "frozen", False, create=True), \
                mock.patch.dict(os.environ, {"TCL_LIBRARY": "", "TK_LIBRARY": ""}):
            report = crashlog.tcl_tk_report()
        self.assertIn("源码运行", report)
        self.assertNotIn("打包运行", report)


class DufsBinTest(unittest.TestCase):
    """验证内置 dufs 的查找与释放逻辑（onefile 打包后的核心机制）。"""

    def test_ensure_lands_in_appdata_executable(self):
        """无论 dufs 来自内置还是手工安装，ensure_dufs 都落到数据目录且可执行。"""
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as src:
            fake = Path(src) / ("dufs.exe" if os.name == "nt" else "dufs")
            fake.write_bytes(b"#!/bin/sh\nexit 0\n")
            fake.chmod(0o755)
            old = os.environ.get("DUFS_GUI_HOME")
            os.environ["DUFS_GUI_HOME"] = home
            try:
                installed = dufsbin.install_custom(fake)
                self.assertEqual(installed, Path(home) / "bin" /
                                 ("dufs.exe" if os.name == "nt" else "dufs"))
                self.assertTrue(dufsbin.is_executable(installed))

                ensured = dufsbin.ensure_dufs()
                self.assertEqual(ensured, installed)
                self.assertTrue(dufsbin.is_executable(ensured))
            finally:
                if old is None:
                    os.environ.pop("DUFS_GUI_HOME", None)
                else:
                    os.environ["DUFS_GUI_HOME"] = old

    def test_builtin_takes_precedence(self):
        """内置 dufs 优先于已落盘副本，这样升级 GUI 能覆盖旧版本。

        不依赖仓库里是否真有 bin/dufs.exe：用临时目录模拟内置资源，
        这样 Windows / Linux 都能稳定跑，也允许把伪造的 bin/dufs 移出 Git。
        """
        with tempfile.TemporaryDirectory() as home, \
                tempfile.TemporaryDirectory() as res:
            builtin = Path(res) / "bin" / dufsbin.BINARY_NAME
            builtin.parent.mkdir(parents=True, exist_ok=True)
            builtin.write_bytes(b"builtin")
            builtin.chmod(0o755)

            stale = Path(home) / "bin" / dufsbin.BINARY_NAME
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_bytes(b"stale")
            stale.chmod(0o755)

            old_home = os.environ.get("DUFS_GUI_HOME")
            old_bin = os.environ.get("DUFS_BIN")
            os.environ["DUFS_GUI_HOME"] = home
            os.environ.pop("DUFS_BIN", None)
            try:
                with mock.patch.object(dufsbin, "resource_dir", return_value=Path(res)):
                    found = dufsbin.find_dufs()
                self.assertEqual(found, builtin, "应优先返回临时目录里的内置 dufs")
            finally:
                if old_home is None:
                    os.environ.pop("DUFS_GUI_HOME", None)
                else:
                    os.environ["DUFS_GUI_HOME"] = old_home
                if old_bin is None:
                    os.environ.pop("DUFS_BIN", None)
                else:
                    os.environ["DUFS_BIN"] = old_bin

    def test_embedded_fallback(self):
        """无内置二进制时，从 base64 内嵌数据释放（tools/embed_dufs.py 的产物）。"""
        with tempfile.TemporaryDirectory() as home:
            import base64
            payload = base64.b64encode(b"\x7fELF-fake").decode()
            mod = sys_path / "core" / "dufs_embedded.py"
            created = not mod.exists()
            if created:
                mod.write_text(f'NAME = "dufs"\nSIZE = 9\nDATA = ("{payload}",)\n',
                               encoding="utf-8")
            try:
                old = os.environ.get("DUFS_GUI_HOME")
                os.environ["DUFS_GUI_HOME"] = home
                try:
                    out = dufsbin._extract_embedded()
                    self.assertIsNotNone(out)
                    self.assertTrue(out.exists())
                    self.assertEqual(out.read_bytes(), b"\x7fELF-fake")
                finally:
                    if old is None:
                        os.environ.pop("DUFS_GUI_HOME", None)
                    else:
                        os.environ["DUFS_GUI_HOME"] = old
            finally:
                if created:
                    mod.unlink(missing_ok=True)


class WinPosTest(unittest.TestCase):
    """弹窗定位：必须落在某块显示器内，多屏时不跑到缝里或屏外。"""

    class FakeWin:
        def __init__(self, screens):
            self._screens = screens
            self.w, self.h = 1920, 1080

        def winfo_screenwidth(self):
            return self.w

        def winfo_screenheight(self):
            return self.h

    def _patch(self, screens):
        wp = __import__("core.winpos", fromlist=["x"])
        wp._enumerate_screens = lambda win: screens
        return wp

    def test_clamp_inside_when_offscreen_right(self):
        wp = self._patch([(0, 0, 1920, 1080)])
        win = self.FakeWin([(0, 0, 1920, 1080)])
        x, y = wp.clamp_to_screen(win, 5000, 300, 620, 560)
        self.assertLessEqual(x + 620, 1920, "右边界越界")
        self.assertGreaterEqual(x, 0)

    def test_clamp_negative_coords(self):
        wp = self._patch([(0, 0, 1920, 1080)])
        win = self.FakeWin([(0, 0, 1920, 1080)])
        x, y = wp.clamp_to_screen(win, -800, -400, 620, 560)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)

    def test_multi_monitor_picks_best_overlap(self):
        # 主屏在左，副屏在右（常见于扩展模式）
        screens = [(0, 0, 1920, 1080), (1920, 0, 2560, 1440)]
        wp = self._patch(screens)
        win = self.FakeWin(screens)
        x, y = wp.clamp_to_screen(win, 2300, 100, 620, 560)
        self.assertGreaterEqual(x, 1920, "应被吸附到右侧副屏内")
        self.assertLessEqual(x + 620, 1920 + 2560)

    def test_window_larger_than_screen_keeps_topleft(self):
        wp = self._patch([(0, 0, 800, 600)])
        win = self.FakeWin([(0, 0, 800, 600)])
        x, y = wp.clamp_to_screen(win, 200, 150, 1200, 900)
        self.assertEqual((x, y), (200, 150), "窗口比屏幕大时不应把左上角推出去")


class AssetsDirTest(unittest.TestCase):
    """--assets 目录必须含 index.html，否则 dufs 启动即 bail。

    源码依据（dufs src/args.rs）：
        fn sanitize_assets_path(path) -> Result {
            let path = Self::sanitize_path(path)?;
            if !path.join("index.html").exists() {
                bail!("Path {} doesn't contains index.html", path.display());
            }
            Ok(path)
        }
    """

    def test_missing_index_html_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.css").write_text("body{}", encoding="utf-8")
            ok, msg = dufsbin.validate_assets_dir(d)
            self.assertFalse(ok)
            self.assertIn("index.html", msg)

    def test_with_index_html_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_text("<html></html>", encoding="utf-8")
            ok, _ = dufsbin.validate_assets_dir(d)
            self.assertTrue(ok)

    def test_empty_is_ok(self):
        ok, msg = dufsbin.validate_assets_dir("")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_nonexistent_rejected(self):
        ok, msg = dufsbin.validate_assets_dir("/no/such/dir/xyz")
        self.assertFalse(ok)
        self.assertIn("不存在", msg)

    def test_builtin_skin_has_index_html(self):
        """dufs 启动硬性要求 --assets 目录含 index.html。"""
        d = dufsbin.webui_dir()
        if d is None:
            self.skipTest("未找到内置皮肤目录")
        self.assertTrue((d / "index.html").is_file())

    def test_skin_is_official_structure(self):
        """皮肤必须是 dufs 官方 assets 的副本，不能自造前端。

        曾自造过一整套 index.html/index.js，等于猜测 dufs 的内部契约
        （数据节点写法、IndexData 字段、DOM class、权限判定），
        结果是上传 / 下载 / 预览全部失效，且 dufs 端不报错、极难定位。

        官方方案（README "Customize UI"）：copy dufs's assets directory
        and modify it accordingly —— 完整搬运，只改 index.css 的变量。
        """
        html = (REPO / "assets" / "index.html").read_text(encoding="utf-8")
        # 官方用 <template id="index-data">，不是 div
        self.assertIn('<template id="index-data">', html)
        # 官方引用内置 JS/CSS/favicon
        self.assertIn("__ASSETS_PREFIX__index.js", html)
        self.assertIn("__ASSETS_PREFIX__index.css", html)
        # 占位符唯一
        self.assertEqual(html.count("__INDEX_DATA__"), 1)

    def test_skin_ships_official_js_and_css(self):
        """index.html 与 index.js 必须同版本随包提供。

        官方 assets 里 index.css / index.js / favicon.ico 缺失会回退内置版本，
        但 index.html 必须存在；若只提供自己版本的 HTML 而让 JS 回退内置，
        HTML 与 JS 版本可能不一致，DOM 对不上同样会功能失效。
        """
        a = REPO / "assets"
        for f in ("index.html", "index.css", "index.js", "favicon.ico",
                  "ASSETS_VERSION"):
            self.assertTrue((a / f).is_file(), f"缺少 {f}")
        css = (a / "index.css").read_text(encoding="utf-8")
        # 深色皮肤只覆盖官方变量，不改动结构
        self.assertIn("--bg-primary", css)
        self.assertIn("DufsGui 深色皮肤", css)
        # 必须有视觉改造，否则"加载了皮肤"和"官方默认界面"看起来毫无区别，
        # 用户会合理地认为皮肤没生效
        self.assertIn("DufsGui 视觉增强", css)

    def test_skin_visual_enhancement_is_real(self):
        """视觉增强要真的改变观感，不能只是换几个颜色变量。

        判据：存在卡片化表格、圆角、渐变顶条这类结构性样式，
        而不是仅有一组 :root 变量覆盖。
        """
        css = (REPO / "assets" / "index.css").read_text(encoding="utf-8")
        for feat in ["border-collapse: separate", "border-radius",
                     "linear-gradient", "backdrop-filter"]:
            self.assertIn(feat, css, f"视觉增强缺少 {feat}")

    def test_skin_keeps_official_js_untouched(self):
        """官方 index.js 必须原样保留 —— 交互逻辑全靠它，改坏就全功能失效。"""
        js = (REPO / "assets" / "index.js").read_text(encoding="utf-8")
        self.assertIn("document.getElementById('index-data')", js)
        self.assertIn('XMLHttpRequest', js)
        self.assertNotIn("DufsGui", js, "不应改动官方 JS")

    def test_args_omitted_when_no_index_html(self):
        """即使勾选了美化，目录不含 index.html 时也不能传 --assets。"""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.css").write_text("body{}", encoding="utf-8")
            cfg = ServerConfig(share_path="/tmp", custom_ui=True, assets_dir=d)
            self.assertNotIn("--assets", cfg.to_args())

    def test_args_present_when_valid(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_text("<html></html>", encoding="utf-8")
            cfg = ServerConfig(share_path="/tmp", custom_ui=True, assets_dir=d)
            self.assertIn("--assets", cfg.to_args())

    def test_default_is_on(self):
        """默认启用皮肤：index.html 自包含且必然存在，不会拖垮启动。"""
        self.assertTrue(ServerConfig().custom_ui)

    def test_packaged_skin_resolves_under_meipass(self):
        """打包后（frozen + _MEIPASS）皮肤必须能定位到。

        这是 v1.2.1 的关键回归：若 PyInstaller 把 assets 打成别的目录名
        （如 webui/），resource_dir()/'assets'/index.html 就找不到，
        --assets 静默失效，网页退回 dufs 默认样式。
        用 monkeypatch 模拟 PyInstaller 的 frozen 环境。
        """
        mei = Path(tempfile.mkdtemp(prefix="meipass_sim_"))
        try:
            assets = mei / "assets"
            assets.mkdir()
            (assets / "index.html").write_text("<html></html>", encoding="utf-8")

            saved_frozen = getattr(sys, "frozen", None)
            saved_meipass = getattr(sys, "_MEIPASS", None)
            sys.frozen = True
            sys._MEIPASS = str(mei)  # type: ignore[attr-defined]
            try:
                # 清掉模块级缓存，迫使 resource_dir() 重读 _MEIPASS
                for _m in ("core.dufsbin", "core.config"):
                    sys.modules.pop(_m, None)
                from core import dufsbin as db  # type: ignore[import-not-at-top]
                found = db.webui_dir()
                self.assertIsNotNone(found, "打包后未能定位内置皮肤目录")
                self.assertEqual(found, assets, "皮肤目录应为 _MEIPASS/assets")
                self.assertTrue((found / "index.html").is_file(),
                                "打包后 index.html 必须存在，否则 --assets 不生效")
            finally:
                if saved_frozen is None:
                    del sys.frozen
                else:
                    sys.frozen = saved_frozen
                if saved_meipass is None:
                    del sys._MEIPASS
                else:
                    sys._MEIPASS = saved_meipass
                sys.modules.pop("core.dufsbin", None)
                sys.modules.pop("core.config", None)
        finally:
            import shutil as _sh
            _sh.rmtree(mei, ignore_errors=True)


class ResourceDirTest(unittest.TestCase):
    """打包资源目录的定位。

    onefile 用 sys._MEIPASS；onedir 没有 _MEIPASS，资源在 exe 所在目录。
    原实现在 frozen 为真但无 _MEIPASS 时回退到**源码目录**，onedir 下必然找不到皮肤。
    """

    def _sim(self, frozen, meipass, exe_dir):
        saved = {k: getattr(sys, k, None) for k in ("frozen", "_MEIPASS")}
        saved_exe = sys.executable
        sys.modules.pop("core.dufsbin", None)
        try:
            if frozen:
                sys.frozen = True
            else:
                sys.__dict__.pop("frozen", None)
            if meipass is None:
                sys.__dict__.pop("_MEIPASS", None)
            else:
                sys._MEIPASS = meipass
            sys.executable = exe_dir
            from core import dufsbin as db
            return db.resource_dir()
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.__dict__.pop(k, None)
                else:
                    setattr(sys, k, v)
            sys.executable = saved_exe
            sys.modules.pop("core.dufsbin", None)

    def test_onedir_falls_back_to_exe_dir(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "DufsGui.exe")
            Path(exe).write_text("x", encoding="utf-8")
            got = self._sim(True, None, exe)   # frozen 但无 _MEIPASS = onedir
            self.assertEqual(got, Path(d), f"onedir 应回退到 exe 目录，实际 {got}")

    def test_onefile_uses_meipass(self):
        with tempfile.TemporaryDirectory() as d:
            got = self._sim(True, d, os.path.join(d, "x.exe"))
            self.assertEqual(got, Path(d))

    def test_dev_uses_project_root(self):
        got = self._sim(False, None, "/nowhere/x")
        self.assertTrue((got / "core").is_dir(), f"开发模式应回退项目根，实际 {got}")


class AssetsVerifyTest(unittest.TestCase):
    """verify_assets_dir 必须把"缺 index.html"说清楚，不能静默。"""

    def test_ok(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.html").write_text("<html>", encoding="utf-8")
            ok, msg = verify_assets_dir(d)
            self.assertTrue(ok)
            self.assertIn("index.html", msg)

    def test_missing_html_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.css").write_text("a{}", encoding="utf-8")
            ok, msg = verify_assets_dir(d)
            self.assertFalse(ok)
            self.assertIn("index.html", msg)
            self.assertIn("index.css", msg)   # 把现有文件列出来便于排查

    def test_none(self):
        ok, msg = verify_assets_dir(None)
        self.assertFalse(ok)
        self.assertIn("未找到", msg)

    def test_builtin_passes(self):
        ok, msg = verify_assets_dir(webui_dir())
        self.assertTrue(ok, f"内置皮肤核验失败：{msg}")


class SkinConfigTest(unittest.TestCase):
    """皮肤开关的持久化行为。

    曾出现的真实 bug：启动失败时"自动降级"把 custom_ui=false 写进 config.json，
    之后即使代码修好、打包修好，启动时仍从配置读回 false，--assets 永远不加。
    一次失败 = 永久关闭。
    """

    def test_polluted_false_is_healed_on_load(self):
        """历史污染的 false 载入时被自愈为 True。

        v1.2.1 的"降级写盘"把 custom_ui=false 存进了 config.json，
        之后即使代码与打包都修好，每次启动仍读回 false、--assets 永远不加，
        表现就是"目录核验通过但皮肤不生效"。
        """
        cfg = ServerConfig.from_dict({"custom_ui": False})
        self.assertTrue(cfg.custom_ui, "历史污染应被自愈为 True")
        self.assertTrue(ServerConfig().custom_ui)

    def test_user_disabled_is_respected(self):
        """用户主动取消勾选（带 _user_set_custom_ui 标记）时不得被自愈覆盖。"""
        cfg = ServerConfig.from_dict(
            {"custom_ui": False, "_user_set_custom_ui": True})
        self.assertFalse(cfg.custom_ui, "用户主动关闭必须尊重")

    def test_disabling_writes_marker(self):
        """主动关闭时要写标记，否则下次启动会被自愈改回，用户的选择丢失。"""
        d = ServerConfig(custom_ui=False).to_dict()
        self.assertTrue(d.get("_user_set_custom_ui"))
        self.assertFalse(ServerConfig.from_dict(d).custom_ui)
        # 重新勾选后标记消失
        self.assertNotIn("_user_set_custom_ui",
                         ServerConfig(custom_ui=True).to_dict())

    def test_assets_arg_follows_custom_ui(self):
        """--assets 只在 custom_ui 为真时入参 —— 这是"核验通过却不生效"的关键分界。

        目录核验只说明"文件在不在"；真正决定生效与否的是参数有没有进命令行。
        """
        self.assertIn("--assets", ServerConfig(share_path=".", custom_ui=True).to_args())
        self.assertNotIn("--assets", ServerConfig(share_path=".", custom_ui=False).to_args())

    def test_downgrade_must_not_touch_form_value(self):
        """自动降级只能改本次启动的临时 cfg，不能改界面变量。

        界面变量会在 _start() 末尾被 _save() 持久化；改成 False 就等于
        “用户主动关闭”，下次载入不会再自愈。写盘路径由
        test_ui_smoke.SkinFallbackPersistenceTest 做端到端覆盖。
        """
        src = (REPO / "app.py").read_text(encoding="utf-8")
        i = src.find("尝试不带自定义网页皮肤重新启动")
        self.assertGreater(i, 0, "未找到自动降级代码段")
        seg = src[i:i + 900]
        code = "\n".join(l for l in seg.splitlines()
                          if not l.strip().startswith("#"))
        self.assertNotIn("self.v_custom_ui", code,
                        "自动降级不得修改界面变量，否则会被末尾 _save() 持久化")
        self.assertNotIn("_save()", code,
                        "自动降级段内不得调用 _save()")

    def test_webui_dir_only_looks_at_assets(self):
        """webui_dir 只认 assets/，不再有 webui/ 死分支。"""
        src = (REPO / "core" / "dufsbin.py").read_text(encoding="utf-8")
        # 只禁真实表达式，注释里提到 webui 没关系
        self.assertNotIn('resource_dir() / "webui"', src)
        self.assertIn('resource_dir() / "assets"', src)


class WaitReadyTest(unittest.TestCase):
    """启动探测：进程死了要立刻返回 False，不能白等超时。"""

    def test_exited_process_returns_false_fast(self):
        import time

        proc = server.DufsProcess(queue.Queue())

        class Dead:
            def poll(self):
                return 1      # 已退出

        proc.proc = Dead()
        t0 = time.time()
        self.assertFalse(proc.wait_ready(59999, "127.0.0.1", timeout=8))
        self.assertLess(time.time() - t0, 2, "进程已退出却仍在空等超时")

    def test_recent_output_captured(self):
        q = queue.Queue()
        proc = server.DufsProcess(q)
        proc.recent.append("line1")
        proc.recent.append("line2")
        self.assertIn("line2", proc.recent_output())
        self.assertIn("line1", proc.recent_output())


class ChildEnvTest(unittest.TestCase):
    """PyInstaller 冻结后用 subprocess 启动外部程序，必须清理库搜索路径。

    官方 "Common Issues and Pitfalls → Launching External Programs"：
    Windows bootloader 用 SetDllDirectoryW 把搜索路径指向 _MEIPASS，
    该设置会被子进程继承，外部程序可能加载到不兼容的 DLL。
    """

    def setUp(self):
        self._frozen = getattr(sys, "frozen", False)
        self._meipass = getattr(sys, "_MEIPASS", None)
        self._path = os.environ.get("PATH")

    def tearDown(self):
        if self._frozen:
            sys.frozen = self._frozen
        else:
            try:
                del sys.frozen
            except AttributeError:
                pass
        if self._meipass is not None:
            sys._MEIPASS = self._meipass
        if self._path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = self._path

    def test_unfrozen_is_noop(self):
        """开发态不应改变任何东西。"""
        try:
            del sys.frozen
        except AttributeError:
            pass
        self.assertIsNone(server._clean_child_env())
        self.assertIsNone(server._unset_dll_directory())

    def test_frozen_strips_meipass_from_path(self):
        sys.frozen = True
        sys._MEIPASS = os.path.join(tempfile.gettempdir(), "_MEI_test")
        os.environ["PATH"] = os.pathsep.join([
            os.path.join(sys._MEIPASS, "bin"), "/usr/bin", sys._MEIPASS,
        ])
        env = server._clean_child_env()
        self.assertIsNotNone(env)
        for entry in env["PATH"].split(os.pathsep):
            self.assertNotIn("_MEI_test", entry, f"子进程 PATH 仍含 _MEIPASS：{entry}")
        self.assertIn("/usr/bin", env["PATH"])
        # 主进程环境不能被改坏
        self.assertIn("_MEI_test", os.environ["PATH"])

    @unittest.skipUnless(os.name == "nt", "SetDllDirectoryW 仅存在于 Windows")
    def test_dll_directory_reset(self):
        sys.frozen = True
        sys._MEIPASS = "C:\\Temp\\_MEI_test"
        prev = server._unset_dll_directory()
        self.assertEqual(prev, "C:\\Temp\\_MEI_test")
        server._restore_dll_directory(prev)


if __name__ == "__main__":
    unittest.main(verbosity=2)
