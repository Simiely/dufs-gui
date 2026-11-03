"""Dufs GUI 主界面（tkinter，深色模式优先）。

界面构建、表单状态、高级设置弹窗已拆到 ui/；启动决策在 core/launch.py；
这里只保留窗口生命周期与启停编排。
"""

from __future__ import annotations

import queue
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from core import dufsbin
from core.config import (AppConfig, ServerConfig, load_config, save_config,
                         config_file)
from core.health import HealthMonitor
from core.launch import build_launch_plan
from core.netutil import find_free_port, local_ips, port_in_use
from core.runtime import DufsRuntime
from core.theme import apply_theme, enable_windows_dark_titlebar, palette
from core import APP_VERSION  # 单一真源，见 core/__init__.py
from ui.advanced import AdvancedDialogMixin
from ui.common import APP_NAME
from ui.form import FormStateMixin
from ui.layout import MainLayoutMixin


class DufsGui(FormStateMixin, MainLayoutMixin, AdvancedDialogMixin, tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1020x760")
        self.minsize(940, 680)

        self.app_cfg: AppConfig = load_config()
        self.dark = bool(self.app_cfg.dark_mode)
        self.colors = palette(self.dark)

        self.log_queue: queue.Queue = queue.Queue()
        self.runtime = DufsRuntime(self.log_queue)
        self.runtime.locate()
        self.health: HealthMonitor | None = None
        self.adv_win: tk.Toplevel | None = None
        self._adv_canvas: tk.Canvas | None = None
        self.config_widgets: list[tk.Widget] = []

        self._build_vars()
        self._build_ui()
        self._apply_theme()
        self._restore()
        self._refresh_preview()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self._drain_queues)

    @property
    def proc(self):
        """兼容旧代码/测试：进程对象由 DufsRuntime 统一持有。"""
        return self.runtime.process

    def report_callback_exception(self, exc, val, tb) -> None:
        """tkinter 事件回调里的异常默认只打到 stderr，隐藏控制台后完全看不见。

        这里转写进日志并弹窗，保证按钮点了没反应时也能查到原因。
        """
        import traceback

        try:
            from core import crashlog

            text = "".join(traceback.format_exception(exc, val, tb))
            path = crashlog.write_report("界面回调异常", text)
            self._log(f"界面出错：{val}（详情见 {path}）")
            try:
                messagebox.showerror("出错了", f"{val}\n\n完整日志：\n{path}")
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- 主题 ----------------
    def skin_dir(self) -> str:
        """当前生效的网页皮肤目录：外部指定优先，否则用内置。

        统一入口，避免各处直接拼属性名。
        （曾在这里误写成 self.assets_dir —— 该属性并不存在，
         实际变量是 self.v_assets_dir(tk.StringVar)，导致 AttributeError。）
        """
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
        self.colors = apply_theme(self, self.dark)
        c = self.colors
        self.log_text.configure(bg=c["field"], fg=c["fg"], insertbackground=c["fg"],
                                highlightbackground=c["border"], highlightcolor=c["border"],
                                selectbackground=c["accent"])
        self.dot.configure(bg=c["panel"], fg=c["muted"])
        self.btn_theme.configure(text="深色" if not self.dark else "浅色")
        # 写一行可见日志：用户能直接确认主题到底生效了没（排"主题没变化"的关键证据）
        try:
            self._log("主题已应用：%s（ttk 主题 %s）"
                      % ("深色" if self.dark else "浅色", ttk.Style(self).theme_use()))
        except Exception:
            pass
        # 高级设置若正开着，也要跟着换主题（Canvas 是原生 tk 控件，style 管不到）
        if self.adv_win is not None and self.adv_win.winfo_exists():
            try:
                apply_theme(self.adv_win, self.dark)
                self.adv_win.configure(bg=c["bg"])
                if self._adv_canvas is not None:
                    self._adv_canvas.configure(bg=c["bg"])
            except Exception:
                pass

        try:
            self.update_idletasks()
            enable_windows_dark_titlebar(self.winfo_id(), self.dark)
        except Exception:
            pass

    def _toggle_theme(self) -> None:
        self.dark = not self.dark
        self.app_cfg.dark_mode = self.dark
        self._apply_theme()
        self._set_status_color()

    def _set_status_color(self, kind: str = "idle") -> None:
        color = {"run": self.colors["ok"], "err": self.colors["danger"],
                 "warn": self.colors["warn"]}.get(kind, self.colors["muted"])
        self.dot.configure(fg=color, bg=self.colors["panel"])

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

    def _on_bind_change(self) -> None:
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
            messagebox.showwarning("端口无效", err)
            return
        host = self.current_config().check_host()
        if port_in_use(port, host):
            free = find_free_port(port, host)
            if messagebox.askyesno("端口已被占用",
                                   f"端口 {port} 已被占用，是否改用 {free}？"):
                self.v_port.set(str(free))
                self._log(f"端口 {port} 被占用，已切换到 {free}")
        else:
            messagebox.showinfo("端口可用", f"端口 {port} 当前可用")

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
            messagebox.showerror("皮肤目录无效", msg)
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
            messagebox.showerror("无法使用", str(e))
            return
        self.v_dufs.set(str(info.path))
        self._log(f"已更换 dufs：{info.path}")

    def _refresh_preview(self) -> None:
        cfg = self.current_config()
        self.lbl_cmd.configure(text="等效命令：" + cfg.command_line())
        if not self.proc.running:
            self.v_url.set(cfg.share_path and cfg.url() or "—")

    # ---------------- 方案 ----------------
    def _reload_profiles(self, select: str = "") -> None:
        names = list(self.app_cfg.profiles)
        self.cmb_profile.configure(values=names)
        self.v_profile.set(select if select in names else "")

    def _save_profile(self) -> None:
        name = simpledialog.askstring("保存方案", "给这套配置起个名字：",
                                      initialvalue=self.v_profile.get() or "")
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
            self.load_to_form(ServerConfig.from_dict(data))
            self.app_cfg.current = name
            self._log(f"已切换到方案：{name}")

    def _delete_profile(self) -> None:
        name = self.v_profile.get()
        if name and messagebox.askyesno("删除方案", f"确定删除方案「{name}」？"):
            self.app_cfg.profiles.pop(name, None)
            self._reload_profiles()
            self._save()

    def _save(self) -> None:
        self.app_cfg.current_config = self.current_config().to_dict()
        save_config(self.app_cfg)

    def _restore(self) -> None:
        if self.app_cfg.notice:
            self._log(f"配置：{self.app_cfg.notice}")
        self.load_to_form(ServerConfig.from_dict(self.app_cfg.current_config))
        if self.v_path.get():
            self._add_recent(self.v_path.get())
        self.cmb_bind.configure(values=["127.0.0.1", "0.0.0.0"] + local_ips())
        self.cmb_recent.configure(values=self.app_cfg.recent_paths)
        self._reload_profiles(self.app_cfg.current)
        info = self.runtime.info
        if info is None:
            self._log("未找到 dufs 可执行文件，请在高级设置里手动指定，或运行 tools/fetch_dufs.py 下载")
        else:
            self.v_dufs.set(str(info.path))
            self._log(f"dufs 就绪：{info.path}" + (f"（{info.version}）" if info.version else ""))

    # ---------------- 启停 ----------------
    def _set_config_enabled(self, enabled: bool) -> None:
        for w in self.config_widgets:
            try:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if enabled else "disabled")
                else:
                    w.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass

    def _start(self) -> None:
        cfg = self.current_config()

        # 先做配置校验与口令日志：此时还不碰 dufs，失败可以立刻返回
        plan = build_launch_plan(cfg, diagnose_skin=False)
        errs = list(plan.errors)
        _, port_err = self.port_from_form()
        if port_err:
            errs.insert(0, port_err)
        if errs:
            messagebox.showerror("配置有误", "\n".join(errs))
            return
        self._log(plan.auth_log)

        info = self.runtime.ensure()
        if info is None:
            if messagebox.askyesno("缺少 dufs",
                                   "没有找到 dufs 可执行文件。\n是否手动选择 dufs.exe？"):
                p = filedialog.askopenfilename(title="选择 dufs.exe")
                if not p:
                    return
                info = self.runtime.adopt(p)
            else:
                return

        # ---- 皮肤诊断：决策与文案都在 core/launch.py，这里只负责写日志 ----
        # dufs 在 --assets 目录不含 index.html 时**不报错**，而是静默回退内置界面，
        # 用户看到"皮肤没生效"却毫无线索。启动前自己核验并写清结论。
        plan = build_launch_plan(
            cfg, binary=info.path, dufs_version=self.runtime.semver,
            skin_dir=self.skin_dir(), skin_version=dufsbin.assets_version(),
            config_path=str(config_file()))
        for line in plan.skin_logs:
            self._log(line)

        if port_in_use(cfg.port, plan.host_check):
            free = find_free_port(cfg.port, plan.host_check)
            if not messagebox.askyesno("端口被占用",
                                       f"端口 {cfg.port} 已被占用，改用 {free} 启动？"):
                return
            self.v_port.set(str(free))
            cfg.port = free
            # 端口变了，参数/URL 必须重算；皮肤日志不重复
            plan = build_launch_plan(cfg, binary=info.path, diagnose_skin=False)

        if cfg.allow_symlink and not messagebox.askyesno(
                "安全提示", "允许符号链接可能暴露共享目录之外的文件，确定开启？"):
            return

        args = list(plan.args)
        try:
            self.proc.start(info.path, args)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("启动失败", str(e))
            return

        if not self.proc.wait_ready(cfg.port, plan.host_check, timeout=8):
            out = self.proc.recent_output()
            self.proc.stop()

            # 若带了 --assets（自定义网页皮肤），很可能是它导致启动失败：
            # 自动去掉重试一次，保证皮肤永远不会挡住共享本身。
            retried = False
            if plan.fallback_args is not None:
                self._log("首次启动未就绪，尝试不带自定义网页皮肤重新启动…")
                # 只改本次启动参数，**不能动界面变量**：
                # 界面变量会在 _start() 末尾被 _save() 持久化，一旦改成 False，
                # 就会被当成“用户主动关闭”写进 config.json，下次启动不再自愈。
                args = list(plan.fallback_args)
                try:
                    self.proc.start(info.path, args)
                    retried = self.proc.wait_ready(cfg.port, plan.host_check, timeout=8)
                except Exception:  # noqa: BLE001
                    retried = False

            if retried:
                self._log("已不带自定义皮肤启动成功（本次临时使用 dufs 默认界面，不写盘）")
                messagebox.showwarning(
                    "已降级启动",
                    "自定义网页皮肤导致 dufs 无法启动，本次已临时使用 dufs 默认界面。\n"
                    "该调整不会写入配置，下次开启仍会尝试自定义皮肤。")
                self._refresh_preview()
            else:
                self.proc.stop()
                self._set_status_color("err")
                self.v_status.set("启动失败")
                detail = out or "(dufs 没有输出任何信息)"
                self._log(f"启动失败，dufs 输出：\n{detail}")
                messagebox.showerror(
                    "启动失败",
                    f"服务未能在端口 {cfg.port} 就绪。\n\ndufs 输出：\n{detail[:600]}")
                return

        self.v_status.set(self.runtime.status_text())
        self.v_url.set(cfg.url())
        self._set_status_color("run")
        self._set_config_enabled(False)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._add_recent(cfg.share_path)
        self._save()
        self._log(f"已启动：{cfg.url()}")
        self._start_health(cfg)
        if self.adv_win is not None:
            try:
                self._refresh_adv_hint()
            except Exception:
                pass

    def _start_health(self, cfg: ServerConfig) -> None:
        """启动后台健康探测；URL 在服务运行期间固定。"""
        self._stop_health()
        url = cfg.health_url()
        # dufs 0.47 的 /__dufs__/health 不校验访问口令，探测不发送任何凭据
        self.health = HealthMonitor(
            lambda: url,
            lambda kind, detail: self.log_queue.put((kind, detail)))
        self.health.start()
        self._log(f"健康检查：每 {self.health.interval:g}s HEAD {url}"
                  f"（连续 {self.health.failure_threshold} 次失败判无响应）")

    def _stop_health(self) -> None:
        if self.health is not None:
            try:
                # 探测本身有 1.5s 超时；停止时最多等 0.5s，避免卡住 UI 主线程
                self.health.stop(timeout=0.5)
            except Exception:  # noqa: BLE001
                pass
            self.health = None

    def _stop(self, silent: bool = False) -> None:
        self._stop_health()
        self.proc.stop()
        self.v_status.set("未启动")
        self._set_status_color("idle")
        self._set_config_enabled(True)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if self.adv_win is not None:
            try:
                self._refresh_adv_hint()
            except Exception:
                pass
        if not silent:
            self._log("已停止服务")
            self._refresh_preview()

    # ---------------- 浏览器 / 剪贴板 ----------------
    def _open_browser(self) -> None:
        if not self.proc.running:
            self._log("服务未运行，请先开启共享")
            messagebox.showinfo("服务未运行", "请先开启共享，再打开网页。")
            return
        # 加时间戳 fragment：URL 变了浏览器才会重新拉取，避免看到缓存的旧页面。
        # 用 fragment 而不是 query，是因为 fragment 不会发给服务端，
        # 不会影响 dufs 对 ?q= / ?zip 等参数的解析。
        import time
        webbrowser.open(self.current_config().url() + "#" + str(int(time.time())))

    def _copy_url(self) -> None:
        url = self.current_config().url() if self.proc.running else self.v_url.get()
        self.clipboard_clear()
        self.clipboard_append(url)
        self._log(f"已复制：{url}")

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
            messagebox.showerror("导出失败", f"{e}\n\n路径：{p}")
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
                elif kind == "health_ok":
                    if self.runtime.running:
                        self.v_status.set(self.runtime.status_text())
                        self._set_status_color("run")
                        self._log(f"服务已恢复响应（{payload}）")
                elif kind == "health_fail":
                    if self.proc.running and self.v_status.get().startswith("运行中"):
                        self.v_status.set("无响应 · 进程仍在")
                        self._set_status_color("warn")
                        self._log(f"服务无响应：健康检查连续失败（{payload}）")
                elif kind == "exit":
                    if self.proc.running is False:
                        current = self.v_status.get()
                        if current.startswith("运行中") or current.startswith("无响应"):
                            self._stop(silent=True)
                            self.v_status.set("已退出")
                            self._set_status_color("warn")
                            self._log("dufs 进程已退出")
        except queue.Empty:
            pass

        self.after(150, self._drain_queues)

    def on_close(self) -> None:
        if self.proc.running:
            if not messagebox.askyesno("退出", "服务正在运行，退出将停止共享，确定吗？"):
                return
            self.proc.stop()
        self._stop_health()
        self._save()
        self.destroy()


def main() -> None:
    app = DufsGui()
    app.mainloop()


if __name__ == "__main__":
    main()
