"""Dufs GUI 主界面（tkinter，固定深色）。

界面构建、表单状态、高级设置弹窗已拆到 ui/；启动决策在 core/launch.py；
多地址实例编排在 core/instances.py；这里只保留窗口生命周期与交互。
"""

from __future__ import annotations

import queue
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk

from core import APP_VERSION  # 单一真源，见 core/__init__.py
from core import dufsbin
from core.config import (AppConfig, ServerConfig, check_window_title, config_file,
                         load_config, save_config)
from core.health import HealthMonitor
from core.instances import InstanceManager
from core.launch import build_launch_plans
from core.netif import apply_saved, list_interfaces
from core.netutil import find_free_port, port_in_use
from core.runtime import DufsRuntime
from core.theme import DARK, apply_theme, enable_windows_dark_titlebar
from ui import dialog as dialogs
from ui.advanced import AdvancedDialogMixin
from ui.bindlist import BindCheckList
from ui.common import emoji_font
from ui.form import FormStateMixin
from ui.layout import MainLayoutMixin


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
        super().__init__()
        self.app_cfg: AppConfig = load_config()
        self.title(self.app_cfg.effective_window_title())
        self.geometry("1040x780")
        self.minsize(960, 720)

        self.colors: dict[str, str] = dict(DARK)

        self.log_queue: queue.Queue = queue.Queue()
        self.runtime = DufsRuntime(self.log_queue)
        self.runtime.locate()
        self.manager = InstanceManager(self.log_queue)
        self.healths: list[tuple[str, HealthMonitor]] = []
        self.adv_win: tk.Toplevel | None = None
        self._adv_canvas: tk.Canvas | None = None
        self.config_widgets: list[tk.Widget] = []

        self._build_vars()
        self._build_ui()
        self._apply_theme()
        self._apply_window_title()
        self._restore()
        self._refresh_preview()
        # 窗口真正映射后再设一次 DWM 深色标题栏（部分系统在 map 前设置不生效）
        self.after(250, lambda: enable_windows_dark_titlebar(self.winfo_id()))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self._drain_queues)

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
        self.log_text.configure(bg=c["well"], fg="#e5e5e7", insertbackground=c["fg"],
                                highlightbackground=c["well"],
                                highlightcolor=c["well"],
                                selectbackground=c["accent"],
                                selectforeground=c["accent_fg"])
        for sb in getattr(self, "log_scrollbars", ()):
            try:
                sb.configure(background=c["card"], troughcolor=c["well"],
                             bordercolor=c["well"], arrowcolor=c["muted"])
            except Exception:
                pass
        self.dot.configure(bg=c["panel"], fg=c["muted"])

        if self.adv_win is not None and self.adv_win.winfo_exists():
            try:
                apply_theme(self.adv_win)
                self.adv_win.configure(bg=c["bg"])
                if self._adv_canvas is not None:
                    self._adv_canvas.configure(bg=c["bg"])
            except Exception:
                pass

        try:
            self.update_idletasks()
            enable_windows_dark_titlebar(self.winfo_id())
        except Exception:
            pass

    def _set_status_color(self, kind: str = "idle") -> None:
        color = {"run": self.colors["ok"], "err": self.colors["danger"],
                 "warn": self.colors["warn"]}.get(kind, self.colors["muted"])
        self.dot.configure(fg=color, bg=self.colors["panel"])

    # ---------------- 窗口标题 ----------------
    def _apply_window_title(self) -> None:
        """窗口标题 / 任务栏名称 / 顶部标题统一取自配置（空值回落默认）。"""
        title = self.app_cfg.effective_window_title()
        try:
            self.title(title)
        except Exception:
            pass
        try:
            self.v_app_title.set(title)
        except Exception:
            pass

    def _apply_window_title_setting(self) -> None:
        """高级设置里的「应用」：校验 → 落盘 → 立即生效。"""
        ok, msg = check_window_title(self.v_window_title.get())
        if not ok:
            self._set_title_hint(msg, error=True)
            return
        self.app_cfg.window_title = msg
        self._apply_window_title()
        self._save()
        if msg:
            self._set_title_hint(f"已应用：{msg}")
        else:
            self._set_title_hint("已恢复默认标题（Dufs GUI）")
        self._log(f"窗口标题已更新：{self.app_cfg.effective_window_title()}")

    def _set_title_hint(self, text: str, error: bool = False) -> None:
        try:
            self.lbl_title_hint.configure(
                text=text, foreground=self.colors["danger"] if error
                else self.colors["muted"])
        except Exception:
            pass

    # ---------------- 配置交互 ----------------
    def _browse_dir(self) -> None:
        initial = self.v_path.get() or str(Path.home())
        d = filedialog.askdirectory(initialdir=initial, title="选择要共享的目录")
        if d:
            self.v_path.set(d)
            self._add_recent(d)

    def _add_recent(self, path: str) -> None:
        rec = [p for p in self.app_cfg.recent_paths if p != path]
        rec.insert(0, path)
        self.app_cfg.recent_paths = rec[:10]
        self.cmb_recent.configure(values=self.app_cfg.recent_paths)

    def _use_recent(self, _e=None) -> None:
        val = self.cmb_recent.get()
        if val:
            self.v_path.set(val)

    def _on_binds_change(self, count: int) -> None:
        try:
            self.lbl_binds.configure(text=f"共享网卡（已选 {count} 个）")
        except Exception:
            pass
        self._refresh_preview()

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
        if name and dialogs.ask_yes_no(self, "删除方案", f"确定删除方案「{name}」？",
                                       ok_text="删除", destructive=True):
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
        self.bindlist.set_items(list_interfaces())
        raw = dict(self.app_cfg.current_config or {})
        cfg = ServerConfig.from_dict(raw)
        self.load_to_form(cfg)
        if raw.get("bind") or raw.get("binds"):
            # 用户保存过选择：保持（失效地址单独提示并回退）
            self._apply_saved_binds(cfg.effective_binds())
        else:
            # 首次启动：默认选最活跃的非回环网卡，而不是 127.0.0.1
            self.bindlist.select_defaults()
            self._pending_binds = self.bindlist.selected()
        if self.v_path.get():
            self._add_recent(self.v_path.get())
        self.cmb_recent.configure(values=self.app_cfg.recent_paths)
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

        group = build_launch_plans(
            cfg, binary=info.path, dufs_version=self.runtime.semver,
            skin_dir=self.skin_dir(), skin_version=dufsbin.assets_version(),
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

        self.v_status.set(self.manager.status_text)
        self._set_status_color("run" if running == total else "warn")
        self._set_config_enabled(False)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._add_recent(cfg.share_path)
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
        host = getattr(self, "status_rows_host", None)
        if host is None:
            return
        for child in host.winfo_children():
            child.destroy()
        states = self.manager.states
        if not states:
            tk.Label(host, text="尚未开启共享 · 勾选网卡后点「开启共享」",
                     bg=self.colors["panel"], fg=self.colors["muted"],
                     font=("Microsoft YaHei UI", 9), anchor="w").grid(
                row=0, column=0, sticky="ew", pady=(0, 2))
            return

        colors = {"运行中": self.colors["ok"], "启动中": self.colors["warn"],
                  "无响应": self.colors["warn"], "失败": self.colors["danger"]}
        icons = {item.address: item.icon for item in self.bindlist.items
                 if item.address}
        for i, st in enumerate(states):
            row = tk.Frame(host, bg=self.colors["panel"])
            row.grid(row=i, column=0, sticky="ew", pady=(0, 2))
            row.columnconfigure(2, weight=1)
            tk.Label(row, text="●", bg=self.colors["panel"],
                     fg=colors.get(st.status, self.colors["muted"]),
                     font=("Microsoft YaHei UI", 8)).grid(row=0, column=0,
                                                          padx=(0, 6))
            tk.Label(row, text=icons.get(st.bind, "🔗"), bg=self.colors["panel"],
                     fg=self.colors["fg"], font=emoji_font(10), width=2).grid(
                row=0, column=1, sticky="w")
            tk.Label(row, text=f"{st.display} · {st.bind}", bg=self.colors["panel"],
                     fg=self.colors["fg"], font=("Microsoft YaHei UI", 9),
                     anchor="w").grid(row=0, column=2, sticky="w")
            # 失败原因只在下方「失败详情」里写一次；列表右侧仅回状态，避免重复长文案
            detail_text = "失败" if st.status == "失败" else (st.detail or st.status)
            tk.Label(row, text=detail_text, bg=self.colors["panel"],
                     fg=colors.get(st.status, self.colors["muted"]),
                     font=("Microsoft YaHei UI", 9), anchor="e").grid(
                row=0, column=3, sticky="e", padx=(8, 0))
            tk.Label(row, text=st.url, bg=self.colors["panel"],
                     fg=self.colors["muted"], font=("Consolas", 8),
                     anchor="w").grid(row=1, column=2, columnspan=2,
                                      sticky="ew", pady=(0, 4))
        urls = [st.url for st in states if st.running]
        self.v_url.set("  ".join(urls) if urls else "—")

    # ---------------- 浏览器 / 剪贴板 ----------------
    def _open_browser(self) -> None:
        running = self.manager.running_states
        if not running:
            self._log("服务未运行，请先开启共享")
            dialogs.show_info(self, "服务未运行", "请先开启共享，再打开网页。")
            return
        url = running[0].url + "#" + str(int(time.time()))
        webbrowser.open(url)

    def _open_qr(self) -> None:
        """二维码内容必须与实际共享地址一致：优先取运行中的地址。"""
        urls = [st.url for st in self.manager.running_states if st.url]
        url = urls[0] if urls else ""
        if not url:
            cfg = self.current_config()
            if cfg.effective_binds() and cfg.share_path:
                url = cfg.url()
        if not url:
            self.v_status.set("没有可生成二维码的共享地址")
            self._set_status_color("warn")
            self._log("未选择网卡或共享目录，无法生成二维码")
            return
        dialogs.show_qr(self, url)

    def _copy_url(self) -> None:
        urls = [st.url for st in self.manager.running_states]
        if not urls:
            urls = [self.v_url.get()]
        text = "\n".join(urls)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._log(f"已复制：{text}")

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
    app = DufsGui()
    app.mainloop()


if __name__ == "__main__":
    main()
