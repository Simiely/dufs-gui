"""Dufs GUI 主界面（tkinter，固定深色）。

界面构建、表单状态、高级设置弹窗已拆到 ui/；启动决策在 core/launch.py；
多地址实例编排在 core/instances.py；这里只保留窗口生命周期与交互。
"""

from __future__ import annotations

import os
import queue
import subprocess
import time
import tkinter as tk
import webbrowser
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, ttk

from core import APP_VERSION  # 单一真源，见 core/__init__.py
from core import dufsbin, timing, webtweak
from core.config import (AppConfig, ServerConfig, config_file, load_config,
                         save_config)
from core.instances import InstanceManager
from core.launch import build_launch_plans
from core.netif import apply_saved, list_interfaces, sort_loopback_last
from core.netutil import find_free_port, port_in_use
from core.runtime import DufsRuntime
from core.theme import (DARK, apply_theme, enable_windows_dark_titlebar,
                        enable_windows_rounded_corners, fonts)
from ui import dialog as dialogs
from ui.advanced import AdvancedDialogMixin
from ui.bindlist import BindCheckList
from ui.common import fit_canvas_text
from ui.form import FormStateMixin
from ui.layout import MainLayoutMixin

#: 仍代表本轮共享的状态；「已停止」之后界面统一回到配置里的地址
LIVE_STATUS = frozenset({"运行中", "无响应", "启动中", "失败", "已退出"})


def normalize_share_path(raw: str) -> Path:
    """把配置里的共享路径转成绝对路径：展开 ~，保留 UNC，相对路径按 cwd。"""
    path = Path(raw.strip()).expanduser()
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def share_dir_action(raw: str) -> tuple[str, Path | None, str]:
    """「打开目录」的前置判断：返回 (动作, 目标, 提示)。

    动作为 ``dir`` / ``file``（打开父目录并选中）/ ``missing`` / ``empty``。
    只判断不执行，方便单测覆盖边界；实际打开由 GUI 处理器负责。
    """
    text = (raw or "").strip()
    if not text:
        return "empty", None, "尚未配置共享目录，请先选择或填写目录。"
    try:
        path = normalize_share_path(text)
        if not path.exists():
            return "missing", path, f"共享目录不存在：{path}"
        if path.is_file():
            return "file", path, ""
    except (OSError, ValueError, RuntimeError):
        return "missing", None, f"路径无效：{text}"
    return "dir", path, ""


class _IdleProcess:
    """未启动时的占位进程，只为了保持 ``gui.proc.running`` 这类旧调用可用。"""

    running = False
    recent = ()

    def stop(self) -> None:
        pass

    def recent_output(self, _lines: int = 0) -> str:
        return ""


_IDLE = _IdleProcess()


class DufsGui(FormStateMixin, MainLayoutMixin, AdvancedDialogMixin, tk.Tk):
    def __init__(self) -> None:
        timing.mark("app_init")
        super().__init__()
        timing.mark("tk_root")
        self.app_cfg: AppConfig = load_config()
        timing.mark("config_loaded")
        # GUI 窗口标题固定：用户可定制的是浏览器标签页标题（高级设置里）
        self.title("Dufs GUI")
        # 窗口 / 任务栏 / Alt-Tab 图标：与 exe PE 资源、网页 favicon 同一枚图形。
        # -default 让后续所有 Toplevel 也继承（否则会退回 Tk 的羽毛图标）。
        icon_path = str(dufsbin.resource_dir() / "assets" / "app.ico")
        try:
            self.iconbitmap(default=icon_path)
        except Exception:  # noqa: BLE001 - 图标缺失不应阻断启动
            pass
        # Tk 只设置窗口类图标，WM_GETICON 会返回 0、由外壳回退到类图标。
        # 等窗口映射后（_apply_window_chrome）再显式给顶层窗口挂 32/16 两枚；
        # HICON 句柄必须存活到进程结束，挂在 self 上。
        self._icon_path = icon_path
        self._icon_handles: list[int] = []
        # 默认打开尺寸 = 最小可用尺寸（960x720）：该尺寸下底部按钮行、
        # 状态行与右侧日志列均完整可见，没有任何控件的右下缘越界。
        # 先设 minsize 再设 geometry，实测两者相同，不依赖生效顺序。
        self.minsize(960, 720)
        self.geometry("960x720")

        self.colors: dict[str, str] = dict(DARK)

        self.log_queue: queue.Queue = queue.Queue()
        self.runtime = DufsRuntime(self.log_queue)
        self.runtime.locate()
        timing.mark("runtime_located")
        self.manager = InstanceManager(self.log_queue)
        self.healths: list[tuple[str, object]] = []
        self.adv_win: tk.Toplevel | None = None
        self._adv_canvas: tk.Canvas | None = None
        self.config_widgets: list[tk.Widget] = []

        self._build_vars()
        timing.mark("vars_ready")
        self._build_ui()
        timing.mark("ui_built")
        timing.mark("theme_start")
        self._apply_theme()
        timing.mark("theme_done")
        timing.mark("restore_start")
        self._restore()
        self._refresh_preview()
        timing.mark("state_restored")
        # 窗口真正映射后再设一次 DWM 深色标题栏/圆角（部分系统在 map 前设置不生效）
        self.after(250, self._apply_window_chrome)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self._drain_queues)
        timing.mark("ui_ready")

    @property
    def proc(self):
        """兼容旧代码/测试：返回第一个实例的进程对象。"""
        for state in self.manager.states:
            if state.process is not None:
                return state.process
        return _IDLE

    def report_callback_exception(self, exc, val, tb) -> None:
        """tkinter 事件回调里的异常默认只打到 stderr，隐藏控制台后完全看不见。"""
        import traceback

        try:
            from core import crashlog

            text = "".join(traceback.format_exception(exc, val, tb))
            path = crashlog.write_report("界面回调异常", text)
            self._log(f"界面出错：{val}（详情见 {path}）")
            try:
                dialogs.show_error(self, "出错了", f"{val}\n\n完整日志：\n{path}")
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- 主题 ----------------
    def skin_dir(self) -> str:
        """当前生效的网页皮肤目录：外部指定优先，否则用内置。"""
        v = self.v_assets_dir.get().strip()
        if v:
            return v
        try:
            from core.dufsbin import webui_dir
            d = webui_dir()
            return str(d) if d else ""
        except Exception:  # noqa: BLE001
            return ""

    def _apply_theme(self) -> None:
        self.colors = apply_theme(self)
        c = self.colors
        timing.mark("theme_styles")
        self.log_text.configure(bg=c["well"], fg="#e5e5e7", insertbackground=c["fg"],
                                highlightbackground=c["well"],
                                highlightcolor=c["well"],
                                selectbackground=c["accent"],
                                selectforeground=c["accent_fg"])
        self.dot.configure(bg=c["panel"], fg=c["muted"])
        timing.mark("theme_widgets")

        if self.adv_win is not None and self.adv_win.winfo_exists():
            try:
                apply_theme(self.adv_win)
                self.adv_win.configure(bg=c["bg"])
                if self._adv_canvas is not None:
                    self._adv_canvas.configure(bg=c["bg"])
            except Exception:
                pass

    def _apply_window_chrome(self) -> None:
        """深色标题栏 + Win11 圆角；Win10 不支持圆角时静默保持直角。"""
        enable_windows_dark_titlebar(self.winfo_id())
        enable_windows_rounded_corners(self.winfo_id())
        self._apply_window_icon()

    def _apply_window_icon(self) -> None:
        """WM_SETICON：Tk 只设窗口类图标，这里给顶层窗口挂 32/16 两枚。

        与 iconbitmap / exe 资源 / 网页 favicon 同一枚 app.ico；
        任务栏与 Alt-Tab 读的 WM_GETICON 因此直接命中，而不是回退到类图标。
        """
        if self._icon_handles:  # 启动时会调用两次（首帧前 + 250ms），只挂一次
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                          wintypes.UINT, ctypes.c_int,
                                          ctypes.c_int, wintypes.UINT]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                            wintypes.WPARAM, wintypes.LPARAM]
            hwnd = int(self.winfo_id())
            hwnd = int(user32.GetAncestor(hwnd, 2) or hwnd)  # GA_ROOT：真正的顶层窗
            for size, which in ((32, 1), (16, 0)):  # ICON_BIG / ICON_SMALL
                h = user32.LoadImageW(None, self._icon_path, 1, size, size, 0x10)
                if h:
                    user32.SendMessageW(hwnd, 0x0080, which, h)  # WM_SETICON
                    self._icon_handles.append(h)
        except Exception:  # noqa: BLE001 - 非 Windows / 图标读取失败时退回 Tk 默认
            pass

    def _set_status_color(self, kind: str = "idle") -> None:
        color = {"run": self.colors["ok"], "err": self.colors["danger"],
                 "warn": self.colors["warn"]}.get(kind, self.colors["muted"])
        self.dot.configure(fg=color, bg=self.colors["panel"])

    # ---------------- 网页外观（浏览器标签页） ----------------
    def _apply_web_meta(self) -> None:
        """校验并保存网页标题；实际注入在下次开启共享时发生。"""
        ok, title = webtweak.check_title(self.v_web_title.get())
        if not ok:
            dialogs.show_warning(self.adv_win or self, "网页标题无效", title)
            return
        self.v_web_title.set(title)
        self._save()
        text = (f"网页标题已保存：{title}" if title
                else "网页标题已恢复为 dufs 官方标题")
        self._log(f"{text}（下次开启共享生效）")
        try:
            self.lbl_web_hint.configure(text=f"{text}；下次开启共享生效",
                                        foreground=self.colors["ok"])
        except Exception:
            pass

    def _pick_favicon(self) -> None:
        p = filedialog.askopenfilename(
            title="选择站点图标（favicon）",
            filetypes=[("图标", "*.ico"), ("所有文件", "*.*")])
        if not p:
            return
        data, msg = webtweak.favicon_bytes(p)
        if data is None:
            dialogs.show_error(self, "图标不可用", msg)
            return
        self.v_favicon_path.set(p)
        self._save()
        self._log(f"站点图标已保存：{p}（下次开启共享生效）")
        try:
            self.lbl_web_hint.configure(text="站点图标已保存；下次开启共享生效",
                                        foreground=self.colors["ok"])
        except Exception:
            pass

    def _reset_favicon(self) -> None:
        self.v_favicon_path.set("")
        self._save()
        self._log("站点图标已恢复为 dufs 官方图标（下次开启共享生效）")
        try:
            self.lbl_web_hint.configure(text="已恢复官方图标；下次开启共享生效",
                                        foreground=self.colors["muted"])
        except Exception:
            pass

    # ---------------- 配置交互 ----------------
    def _browse_dir(self) -> None:
        initial = self.v_path.get() or str(Path.home())
        d = filedialog.askdirectory(initialdir=initial, title="选择要共享的目录")
        if d:
            self.v_path.set(d)

    def _on_binds_change(self, count: int) -> None:
        self._pending_binds = self.bindlist.selected()
        self._refresh_preview()

    def _open_binds(self) -> None:
        """网卡勾选模态弹窗：确定立即生效；×/Esc 丢弃未确认的勾选。"""
        if self.manager.running:
            return
        chosen = dialogs.select_binds(self, list(self.bindlist.items),
                                      self.bindlist.selected())
        if chosen is None:
            return
        self.bindlist.set_selection(chosen)
        self._pending_binds = self.bindlist.selected()
        self._log("共享网卡已更新：" + ("、".join(self._pending_binds) or "无"))

    def _active_states(self) -> list:
        """本轮仍有效的实例状态；停止后归「已停止」，界面回到配置地址。"""
        return [st for st in self.manager.states
                if (st.bind or "").strip() and st.status in LIVE_STATUS]

    def _address_rows(self) -> list[tuple[str, str, str]]:
        """(url, 网卡名, 状态)：网址是主信息，网卡名只作右侧弱化注释。"""
        states = self._active_states()
        if states:
            return [(st.url, st.display, st.status)
                    for st in states if st.url]
        cfg = self.current_config()
        if not cfg.share_path:
            return []
        labels = self._current_labels()
        rows = []
        for bind in cfg.effective_binds():
            rows.append((cfg.url(bind=bind), labels.get(bind, bind), "预览"))
        return rows

    def _refresh_addr_list(self) -> None:
        if not hasattr(self, "addr_list"):
            return
        rows = self._address_rows()
        self.addr_list.set_rows(rows)
        self._render_aux_status()

    def _aux_ip_parts(self) -> list[tuple[str, str]]:
        """辅助状态的 IP 与颜色：运行中用实际地址，未运行用配置地址。"""
        states = self._active_states()
        if states:
            colors = {"运行中": self.colors["fg"], "启动中": self.colors["warn"],
                      "无响应": self.colors["warn"], "失败": self.colors["danger"],
                      "已退出": self.colors["danger"]}
            raw = [(st.bind, colors.get(st.status, self.colors["muted"]))
                   for st in states]
        else:
            cfg = self.current_config()
            raw = [(bind, self.colors["muted"]) for bind in cfg.effective_binds()]
        order = sort_loopback_last([ip for ip, _ in raw])
        color_of: dict[str, str] = {}
        for ip, color in raw:
            color_of.setdefault(ip, color)
        return [(ip, color_of[ip]) for ip in order]

    def _render_aux_status(self) -> None:
        """辅助状态只画 IP：单行、超宽末尾省略、悬停显示完整值。"""
        canvas = getattr(self, "aux_canvas", None)
        if canvas is None:
            return
        self._hide_aux_tooltip()
        try:
            canvas.delete("all")
        except Exception:
            return
        parts = self._aux_ip_parts()
        self._aux_full = " · ".join(ip for ip, _ in parts)
        self._aux_truncated = False
        if not parts:
            self._aux_full = ""
            try:
                canvas.create_text(2, 11, anchor="w", text="未选择地址",
                                   fill=self.colors["muted"],
                                   font=fonts()["caption"])
            except Exception:
                pass
            return
        colors = {color for _, color in parts}
        if self.colors["danger"] in colors:
            fill = self.colors["danger"]
        elif self.colors["warn"] in colors:
            fill = self.colors["warn"]
        elif self.colors["fg"] in colors:
            fill = self.colors["fg"]
        else:
            fill = self.colors["muted"]
        try:
            item = canvas.create_text(2, 11, anchor="w", text=self._aux_full,
                                      fill=fill, font=fonts()["mono"])
            width = canvas.winfo_width()
            if width > 40:
                _shown, truncated = fit_canvas_text(
                    canvas, item, self._aux_full, width - 6)
                self._aux_truncated = truncated
        except Exception:
            pass

    def _show_aux_tooltip(self, event=None) -> None:
        if not getattr(self, "_aux_truncated", False):
            return
        self._hide_aux_tooltip()
        try:
            tip = tk.Toplevel(self)
            tip.overrideredirect(True)
            tip.configure(bg=self.colors["border"])
            tk.Label(tip, text=self._aux_full, bg=self.colors["card"],
                     fg=self.colors["fg"], font=fonts()["caption"],
                     padx=8, pady=4).pack(padx=1, pady=1)
            x = (event.x_root + 12) if event is not None else self.winfo_rootx()
            y = (event.y_root + 16) if event is not None else self.winfo_rooty()
            tip.geometry(f"+{x}+{y}")
            self._aux_tip = tip
        except Exception:
            self._aux_tip = None

    def _hide_aux_tooltip(self, _event=None) -> None:
        tip = getattr(self, "_aux_tip", None)
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
        self._aux_tip = None

    def _on_addr_overflow(self, hidden: int) -> None:
        if not hasattr(self, "lbl_addr_count"):
            return
        try:
            self.lbl_addr_count.configure(
                text=f"还有 {hidden} 个未显示" if hidden else "")
        except Exception:
            pass

    def _copy_one_url(self, url: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(url)
        self._log(f"已复制：{url}")

    def _on_perm_change(self, var: tk.BooleanVar, _text: str) -> None:
        self._refresh_preview()

    def _on_savelog_change(self) -> None:
        if self.v_savelog.get() and not self.v_logpath.get().strip():
            default = str(dufsbin.app_data_dir() / "dufs-access.log")
            self.v_logpath.set(default)
        self._refresh_preview()

    def _check_port(self) -> None:
        port, err = self.port_from_form()
        if err:
            dialogs.show_warning(self, "端口无效", err)
            return
        cfg = self.current_config()
        binds = cfg.effective_binds()
        if not binds:
            dialogs.show_warning(self, "未选择网卡", "请先勾选至少一个共享网卡。")
            return
        occupied = [b for b in binds if port_in_use(port, cfg.check_host(b))]
        if not occupied:
            dialogs.show_info(self, "端口可用", f"端口 {port} 在所有已选地址上均可用")
            return
        free = find_free_port(port, cfg.check_host(occupied[0]))
        if dialogs.ask_yes_no(self, "端口已被占用",
                              f"端口 {port} 在以下地址上已被占用：\n"
                              + "\n".join(occupied)
                              + f"\n\n是否改用 {free}？", ok_text="改用"):
            self.v_port.set(str(free))
            self._log(f"端口 {port} 被占用，已切换到 {free}")

    def _pick_log(self) -> None:
        p = filedialog.asksaveasfilename(defaultextension=".log",
                                         initialfile="dufs-access.log")
        if p:
            self.v_logpath.set(p)

    def _pick_cert(self) -> None:
        p = filedialog.askopenfilename(title="选择证书文件",
                                       filetypes=[("证书", "*.crt *.pem"), ("所有文件", "*.*")])
        if p:
            self.v_cert.set(p)

    def _pick_key(self) -> None:
        p = filedialog.askopenfilename(title="选择私钥文件",
                                       filetypes=[("私钥", "*.key *.pem"), ("所有文件", "*.*")])
        if p:
            self.v_key.set(p)

    def _pick_assets(self) -> None:
        d = filedialog.askdirectory(title="选择网页皮肤目录（须含 index.html）")
        if not d:
            return
        ok, msg = dufsbin.validate_assets_dir(d)
        if not ok:
            dialogs.show_error(self, "皮肤目录无效", msg)
            return
        self.v_assets_dir.set(d)

    def _pick_dufs(self) -> None:
        p = filedialog.askopenfilename(
            title="选择 dufs 可执行文件",
            filetypes=[("可执行文件", "dufs.exe;dufs"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            info = self.runtime.adopt(p)
        except OSError as e:
            dialogs.show_error(self, "无法使用", str(e))
            return
        self.v_dufs.set(str(info.path))
        self._log(f"已更换 dufs：{info.path}")

    def _refresh_preview(self) -> None:
        cfg = self.current_config()
        if not self.manager.running:
            binds = cfg.effective_binds()
            if binds and cfg.share_path:
                self.v_url.set(cfg.url())
            else:
                self.v_url.set("—")
        self._refresh_addr_list()

    # ---------------- 方案 ----------------
    def _reload_profiles(self, select: str = "") -> None:
        names = list(self.app_cfg.profiles)
        self.cmb_profile.configure(values=names)
        self.v_profile.set(select if select in names else "")

    def _save_profile(self) -> None:
        name = dialogs.ask_string(self, "保存方案", "给这套配置起个名字：",
                                  initial=self.v_profile.get() or "", max_len=40)
        if not name:
            return
        self.app_cfg.profiles[name] = self.current_config().to_dict()
        self.app_cfg.current = name
        self._reload_profiles(name)
        self._save()
        self._log(f"已保存方案：{name}")

    def _switch_profile(self) -> None:
        name = self.v_profile.get()
        data = self.app_cfg.profiles.get(name)
        if data:
            cfg = ServerConfig.from_dict(data)
            self.load_to_form(cfg)
            if data.get("bind") or data.get("binds"):
                self._apply_saved_binds(cfg.effective_binds())
            else:
                self.bindlist.select_defaults()
                self._pending_binds = self.bindlist.selected()
            self.app_cfg.current = name
            self._log(f"已切换到方案：{name}")

    def _delete_profile(self) -> None:
        name = self.v_profile.get()
        if name and dialogs.ask_yes_no(
                self, "删除方案",
                f"删除方案「{name}」？\n此操作不可撤销",
                ok_text="删除", destructive=True, default_ok=False):
            self.app_cfg.profiles.pop(name, None)
            self._reload_profiles()
            self._save()

    def _save(self) -> None:
        self.app_cfg.current_config = self.current_config().to_dict()
        save_config(self.app_cfg)

    def _apply_saved_binds(self, binds: list[str]) -> None:
        selected, invalid = apply_saved(binds, self.bindlist.items)
        self.bindlist.set_selection(selected)
        self._pending_binds = selected
        if invalid:
            self._log("以下监听地址已失效，已自动回退："
                      + "、".join(invalid))

    def _restore(self) -> None:
        if self.app_cfg.notice:
            self._log(f"配置：{self.app_cfg.notice}")
        items = list_interfaces()
        timing.mark("netif_listed")
        self.bindlist.set_items(items)
        timing.mark("bindlist_items")
        raw = dict(self.app_cfg.current_config or {})
        cfg = ServerConfig.from_dict(raw)
        self.load_to_form(cfg)
        timing.mark("form_loaded")
        if raw.get("bind") or raw.get("binds"):
            # 用户保存过选择：保持（失效地址单独提示并回退）
            self._apply_saved_binds(cfg.effective_binds())
        else:
            # 首次启动：默认选最活跃的非回环网卡，而不是 127.0.0.1
            self.bindlist.select_defaults()
            self._pending_binds = self.bindlist.selected()
        self._reload_profiles(self.app_cfg.current)
        info = self.runtime.info
        if info is None:
            self._log("未找到 dufs 可执行文件，请在高级设置里手动指定，"
                      "或运行 tools/fetch_dufs.py 下载")
        else:
            self.v_dufs.set(str(info.path))
            self._log(f"dufs 就绪：{info.path}"
                      + (f"（{info.version}）" if info.version else ""))

    # ---------------- 启停 ----------------
    def _set_config_enabled(self, enabled: bool) -> None:
        for w in self.config_widgets:
            try:
                if isinstance(w, BindCheckList):
                    w.set_enabled(enabled)
                elif isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if enabled else "disabled")
                else:
                    w.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass

    def _current_labels(self) -> dict[str, str]:
        return {item.address: item.display_name for item in self.bindlist.items
                if item.address}

    def _start(self) -> None:
        cfg = self.current_config()
        if not cfg.effective_binds():
            # 不弹窗：状态栏给一行提示即可
            self.v_status.set("请至少选择一个共享网卡")
            self._set_status_color("warn")
            self._log("未选择任何共享网卡，已取消启动")
            return

        group = build_launch_plans(cfg, diagnose_skin=False)
        errs = list(group.errors)
        _, port_err = self.port_from_form()
        if port_err:
            errs.insert(0, port_err)
        if errs:
            dialogs.show_error(self, "配置有误", "\n".join(errs))
            return
        if group.auth_log:
            self._log(group.auth_log)

        info = self.runtime.ensure()
        if info is None:
            if dialogs.ask_yes_no(self, "缺少 dufs",
                                  "没有找到 dufs 可执行文件。\n是否手动选择 dufs.exe？",
                                  ok_text="选择"):
                p = filedialog.askopenfilename(title="选择 dufs.exe")
                if not p:
                    return
                info = self.runtime.adopt(p)
            else:
                return

        # 网页标题/favicon/中文文案/去彩条：复制皮肤到用户目录再注入，
        # 不改仓库/fetch 产物；只要启用网页美化界面就始终生成副本。
        launch_cfg = cfg
        skin_dir = self.skin_dir()
        if cfg.custom_ui:
            overlay = webtweak.prepare_overlay(
                skin_dir, cfg.web_title, cfg.favicon_path)
            for note in overlay.notes:
                self._log(f"[网页] {note}")
            if overlay.assets_dir:
                skin_dir = overlay.assets_dir
                launch_cfg = replace(cfg, assets_dir=overlay.assets_dir)

        group = build_launch_plans(
            launch_cfg, binary=info.path, dufs_version=self.runtime.semver,
            skin_dir=skin_dir, skin_version=dufsbin.assets_version(),
            config_path=str(config_file()))
        for line in group.skin_logs:
            self._log(line)

        if cfg.allow_symlink and not dialogs.ask_yes_no(
                self, "安全提示", "允许符号链接可能暴露共享目录之外的文件，确定开启？",
                ok_text="仍然开启"):
            return

        # 等效命令行改为日志：每个绑定地址一行，便于复制排查；口令已脱敏
        for plan in group.plans:
            self._log(f"[命令] {plan.bind}:{plan.port}  {plan.command}")

        self._stop_health()
        summary = self.manager.start(
            info.path, group.plans, self._current_labels(), wait=8)
        self._render_status_rows()
        running = len(self.manager.running_states)
        total = len(self.manager.states)

        if running == 0:
            self.v_status.set("启动失败")
            self._set_status_color("err")
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self._set_config_enabled(True)
            self._log(summary)
            self._log(self.manager.failures_text())
            self._update_detail_area(force_expand=True)
            return

        # 地址数量由左栏列表表达，状态栏只回状态，避免同屏重复
        self.v_status.set("运行中" if running == total else self.manager.status_text)
        self._set_status_color("run" if running == total else "warn")
        self._set_config_enabled(False)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._save()

        for st in self.manager.running_states:
            tag = "（已降级：未使用自定义皮肤）" if st.degraded else ""
            self._log(f"已启动：{st.display} · {st.url}{tag}")
        if self.manager.failed_states():
            self._log(summary)
            self._log(self.manager.failures_text())
        self._update_detail_area()

        self._start_health(cfg)
        if self.adv_win is not None:
            try:
                self._refresh_adv_hint()
            except Exception:
                pass

    def _start_health(self, cfg: ServerConfig) -> None:
        """每个运行中的地址一个健康探测，事件带地址前缀。"""
        self._stop_health()
        for st in self.manager.running_states:
            url = cfg.health_url(bind=st.bind)
            bind = st.bind

            def emit(kind, detail, b=bind):
                self.log_queue.put((kind, f"{b}|{detail}"))

            from core.health import HealthMonitor  # 启动时才用，避免拉高导入耗时

            monitor = HealthMonitor(lambda u=url: u, emit)
            monitor.start()
            self.healths.append((bind, monitor))
        if self.healths:
            first = self.healths[0][1]
            self._log(f"健康检查：每 {first.interval:g}s HEAD 每个地址"
                      f"（连续 {first.failure_threshold} 次失败判无响应）")

    def _stop_health(self) -> None:
        for _, monitor in self.healths:
            try:
                monitor.stop(timeout=0.5)
            except Exception:  # noqa: BLE001
                pass
        self.healths = []

    def _stop(self, silent: bool = False) -> None:
        self._stop_health()
        self.manager.stop()
        self.v_status.set("未启动")
        self._set_status_color("idle")
        self._render_status_rows()
        self._set_config_enabled(True)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._update_detail_area()
        if not silent:
            self._log("已停止服务")
            self._refresh_preview()
        else:
            self.v_url.set("—")
        if self.adv_win is not None:
            try:
                self._refresh_adv_hint()
            except Exception:
                pass

    # ---------------- 状态行 ----------------
    def _render_status_rows(self) -> None:
        """右栏只列异常地址（IP + 状态），不重复网址与网卡描述。"""
        host = getattr(self, "status_rows_host", None)
        if host is None:
            return
        for child in host.winfo_children():
            child.destroy()
        states = self._active_states()
        if states:
            problems = [st for st in states
                        if not st.running and st.status != "启动中"]
            colors = {"运行中": self.colors["ok"], "启动中": self.colors["warn"],
                      "无响应": self.colors["warn"], "失败": self.colors["danger"],
                      "已退出": self.colors["danger"]}
            for i, st in enumerate(problems):
                row = tk.Frame(host, bg=self.colors["panel"])
                row.grid(row=i, column=0, sticky="ew", pady=(0, 2))
                row.columnconfigure(1, weight=1)
                tk.Label(row, text="●", bg=self.colors["panel"],
                         fg=colors.get(st.status, self.colors["muted"]),
                         font=("Microsoft YaHei UI", 8)).grid(
                    row=0, column=0, padx=(0, 6))
                tk.Label(row, text=st.bind, bg=self.colors["panel"],
                         fg=self.colors["fg"], font=fonts()["mono"],
                         anchor="w").grid(row=0, column=1, sticky="w")
                tk.Label(row, text=st.status, bg=self.colors["panel"],
                         fg=colors.get(st.status, self.colors["muted"]),
                         font=("Microsoft YaHei UI", 9), anchor="e").grid(
                    row=0, column=2, sticky="e", padx=(8, 0))
            urls = [st.url for st in states if st.status in ("运行中", "无响应")]
            self.v_url.set("  ".join(urls) if urls else "—")
        self._refresh_addr_list()

    # ---------------- 浏览器 / 剪贴板 ----------------
    def _open_browser(self) -> None:
        running = self.manager.running_states
        if not running:
            self._log("服务未运行，请先开启共享")
            dialogs.show_info(self, "服务未运行", "请先开启共享，再打开网页。")
            return
        webbrowser.open(running[0].url)

    def _qr_urls(self) -> list[str]:
        """所有可访问地址：运行中用实际监听地址，未运行用配置地址。

        顺序沿用启动计划/网卡排序（活动网卡优先、回环垫底），首项即默认主推。
        """
        urls = [st.url for st in self.manager.running_states if st.url]
        if not urls:
            cfg = self.current_config()
            if cfg.effective_binds() and cfg.share_path:
                urls = [cfg.url(bind=b) for b in cfg.effective_binds()]
        result: list[str] = []
        for url in urls:
            if url and url not in result:
                result.append(url)
        return result

    def _open_qr(self) -> None:
        """二维码内容必须与实际共享地址一致；多地址时弹窗内可切换。"""
        urls = self._qr_urls()
        if not urls:
            self.v_status.set("没有可生成二维码的共享地址")
            self._set_status_color("warn")
            self._log("未选择网卡或共享目录，无法生成二维码")
            return
        dialogs.show_qr(self, urls[0], urls=urls)

    def _copy_url(self) -> None:
        # 与二维码同源：运行中用实际监听地址，未运行用全部配置地址
        urls = self._qr_urls()
        text = "\n".join(urls) if urls else self.v_url.get()
        self.clipboard_clear()
        self.clipboard_append(text)
        self._log(f"已复制：{text}")

    def _open_share_dir(self) -> None:
        """用资源管理器打开当前共享根目录（文件则打开父目录并选中）。"""
        action, path, note = share_dir_action(self.current_config().share_path)
        if action == "empty":
            dialogs.show_info(self, "尚未配置共享目录", note)
            return
        if action == "missing":
            self._log(note)
            dialogs.show_warning(self, "共享目录不存在",
                                 note + "\n\n请检查路径，或重新选择目录。")
            return
        try:
            if action == "file":
                # /select, 必须与路径连成一个参数，否则含空格时会被拆开
                subprocess.Popen(f'explorer /select,"{path}"')
            else:
                os.startfile(str(path))
        except Exception as exc:  # noqa: BLE001 - 交给弹窗，不让按钮抛异常
            self._log(f"打开目录失败：{exc}")
            dialogs.show_error(self, "打开目录失败", f"{path}\n\n{exc}")
            return
        self._log(f"已在资源管理器打开：{path}")

    # ---------------- 失败详情（有错误才出现） ----------------
    def _toggle_detail(self) -> None:
        self.detail_expanded = not self.detail_expanded
        self._render_detail_body()

    def _render_detail_body(self) -> None:
        try:
            if self.detail_expanded:
                self.detail_body.grid()
                self.btn_detail_toggle.configure(text="收起")
            else:
                self.detail_body.grid_remove()
                self.btn_detail_toggle.configure(text="展开")
        except Exception:
            pass

    def _update_detail_area(self, force_expand: bool = False) -> None:
        """无失败 → 整块收起（不占空白）；有失败 → 显示并可展开。"""
        failed = self.manager.failed_states()
        if not failed:
            try:
                self.detail_holder.grid_remove()
                self.detail_text.configure(state="normal")
                self.detail_text.delete("1.0", "end")
                self.detail_text.configure(state="disabled")
            except Exception:
                pass
            return
        text = self.manager.failures_text()
        try:
            self.lbl_detail_title.configure(text=f"启动失败详情（{len(failed)} 项）")
            self.detail_text.configure(state="normal")
            self.detail_text.delete("1.0", "end")
            self.detail_text.insert("1.0", text)
            self.detail_text.configure(state="disabled")
            if force_expand:
                self.detail_expanded = True
            self.detail_holder.grid()
            self._render_detail_body()
        except Exception:
            pass

    # ---------------- 日志 ----------------
    def _log(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {line}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _export_log(self) -> None:
        p = filedialog.asksaveasfilename(defaultextension=".log",
                                         initialfile="dufs-gui.log")
        if not p:
            return
        content = self.log_text.get("1.0", "end")
        try:
            Path(p).write_text(content, encoding="utf-8")
        except OSError as e:
            dialogs.show_error(self, "导出失败", f"{e}\n\n路径：{p}")
            self._log(f"日志导出失败：{e}")
            return
        self._log(f"日志已导出：{p}")

    # ---------------- 队列与关闭 ----------------
    def _drain_queues(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind in ("health_ok", "health_fail"):
                    bind, _, detail = str(payload).partition("|")
                    self._on_health(kind, bind, detail or str(payload))
                elif kind == "exit":
                    self._on_instance_exit(str(payload or ""))
        except queue.Empty:
            pass

        self.after(150, self._drain_queues)

    def _on_health(self, kind: str, bind: str, detail: str) -> None:
        state = next((s for s in self.manager.states if s.bind == bind), None)
        if state is None or state.process is None or not state.process.running:
            return
        if kind == "health_fail":
            if state.status == "运行中":
                state.status = "无响应"
                state.detail = "健康检查连续失败"
                self._render_status_rows()
                self.v_status.set("部分地址无响应 · 进程仍在")
                self._set_status_color("warn")
                self._log(f"[{state.display}] 服务无响应：健康检查连续失败（{detail}）")
        else:
            if state.status == "无响应":
                state.status = "运行中"
                state.detail = ""
                self._render_status_rows()
                self.v_status.set(self.manager.status_text)
                self._set_status_color("run"
                                       if len(self.manager.running_states)
                                       == len(self.manager.states) else "warn")
                self._log(f"[{state.display}] 服务已恢复响应（{detail}）")

    def _on_instance_exit(self, bind: str) -> None:
        state = next((s for s in self.manager.states if s.bind == bind), None)
        if state is None:
            return
        if state.process is not None and state.process.running:
            return
        # 「启动中」交给 wait_ready 定性；「已停止」是用户主动停止，不要改写。
        # 只有曾经运行过的实例意外退出才标成「已退出」；启动失败要保留失败原因，
        # 否则失败详情区会因为状态被覆盖而消失。
        if state.status in ("启动中", "已停止"):
            return
        if state.status == "失败":
            state.detail = state.detail or "进程已退出"
        else:
            state.status = "已退出"
            state.detail = "进程已退出"
        self._render_status_rows()
        if not self.manager.running:
            self._stop_health()
            if self.manager.failed_states():
                self.v_status.set(self.manager.status_text)
                self._set_status_color("err")
            else:
                self.v_status.set("已退出")
                self._set_status_color("warn")
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self._set_config_enabled(True)
            self._update_detail_area()
            self._refresh_preview()
            self._log("dufs 进程已退出")
        else:
            self.v_status.set(self.manager.status_text)
            self._set_status_color("warn")
            self._update_detail_area()
            self._log(f"[{state.display}] dufs 进程已退出，其余地址仍在运行")

    def on_close(self) -> None:
        if self.manager.running:
            if not dialogs.ask_yes_no(self, "退出",
                                      "服务正在运行，退出将停止共享，确定吗？",
                                      ok_text="退出", destructive=True):
                return
        self.manager.stop()
        self._stop_health()
        self._save()
        self.destroy()


def main() -> None:
    timing.mark("main_enter")
    app = DufsGui()
    # 只做一次布局：映射后再上深色标题栏，最后交给 update() 完成首帧绘制。
    app.update_idletasks()
    timing.mark("first_idle")
    try:
        app._apply_window_chrome()
    except Exception:
        pass
    timing.mark("chrome_ready")
    app.update()
    timing.mark("first_frame")
    app.update()
    timing.mark("second_update")
    timing.mark("mainloop")
    app.mainloop()


if __name__ == "__main__":
    main()
