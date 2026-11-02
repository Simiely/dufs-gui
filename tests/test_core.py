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

sys_path = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(sys_path))

REPO = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO))

import core as core_pkg  # noqa: E402
from core import dufsbin, server  # noqa: E402
from core.config import (AppConfig, ServerConfig, load_config,  # noqa: E402
                         normalize_prefix, save_config)
from core.netutil import find_free_port, port_in_use  # noqa: E402


class PrefixTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_prefix("files"), "/files")
        self.assertEqual(normalize_prefix("/files/"), "/files")
        self.assertEqual(normalize_prefix(""), "")
        self.assertEqual(normalize_prefix("  a/b "), "/a/b")


class VersionTest(unittest.TestCase):
    """版本号必须单一真源，且被 CHANGELOG 记录。"""

    def test_version_is_semver(self):
        import re
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

    def test_persist(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.json"
            cfg = AppConfig(dark_mode=True, recent_paths=["/a"], profiles={"x": {"port": 1}})
            save_config(cfg, p)
            back = load_config(p)
            self.assertEqual(back.recent_paths, ["/a"])
            self.assertEqual(back.profiles["x"]["port"], 1)


class PortTest(unittest.TestCase):
    def test_in_use_and_free(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            self.assertTrue(port_in_use(port))
            self.assertNotEqual(find_free_port(port), port)
        finally:
            srv.close()


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

    @unittest.skipUnless((sys_path / "bin" / "dufs").exists()
                         or (sys_path / "bin" / "dufs.exe").exists(),
                         "需要 bin/ 下有内置 dufs")
    def test_builtin_takes_precedence(self):
        """内置 dufs 优先于已落盘副本，这样升级 GUI 能覆盖旧版本。"""
        with tempfile.TemporaryDirectory() as home:
            old = os.environ.get("DUFS_GUI_HOME")
            os.environ["DUFS_GUI_HOME"] = home
            try:
                stale = Path(home) / "bin" / ("dufs.exe" if os.name == "nt" else "dufs")
                stale.parent.mkdir(parents=True, exist_ok=True)
                stale.write_bytes(b"stale")
                stale.chmod(0o755)

                found = dufsbin.find_dufs()
                self.assertIsNotNone(found)
                self.assertNotEqual(found, stale, "内置版本应覆盖已落盘的旧副本")
            finally:
                if old is None:
                    os.environ.pop("DUFS_GUI_HOME", None)
                else:
                    os.environ["DUFS_GUI_HOME"] = old

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
        """打包内置皮肤必须三件套齐全，否则启动必失败。"""
        d = dufsbin.webui_dir()
        if d is None:
            self.skipTest("未找到内置皮肤目录")
        for f in ("index.html", "index.css", "index.js"):
            self.assertTrue((d / f).is_file(), f"内置皮肤缺少 {f}")

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

    def test_default_is_off(self):
        """默认不启用皮肤：宁可样式朴素，也不能挡住共享本身。"""
        self.assertFalse(ServerConfig().custom_ui)


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
