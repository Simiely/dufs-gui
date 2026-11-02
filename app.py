"""Dufs GUI 主界面（tkinter，深色模式优先）。"""

from __future__ import annotations

import traceback
import os
import re
import queue
import time
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from core import dufsbin
from core.theme import ThemedCheckbutton, ThemedCombobox
from core.winpos import center_on_parent
from core.config import (AppConfig, RENDER_MODES, ServerConfig, load_config,
                         save_config, config_file)
from core.netutil import find_free_port, local_ips, port_in_use
from core.server import DufsProcess
from core.theme import apply_theme, enable_windows_dark_titlebar, palette

APP_NAME = "Dufs 文件共享"
from core import APP_VERSION  # 单一真源，见 core/__init__.py


def ui_font(size: int = 10, weight: str = "normal") -> tuple:
    if os.name == "nt":
        family = "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        family = "PingFang SC"
    else:
        family = "Noto Sans CJK SC"
    return (family, size, weight)


class DufsGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1020x760")
        self.minsize(940, 680)

        self.app_cfg: AppConfig = load_config()
        self.dark = bool(self.app_cfg.dark_mode)
        self.colors = palette(self.dark)

        self.log_queue: queue.Queue = queue.Queue()
        self.proc = DufsProcess(self.log_queue)

        self.dufs_path: Path | None = dufsbin.find_dufs()
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

    # ---------------- 变量 ----------------
    def _build_vars(self) -> None:
        self.v_path = tk.StringVar(value="")
        self.v_bind = tk.StringVar(value="127.0.0.1")
        # 用字符串输入：IntVar 在清空/输入非数字时 .get() 会抛 TclError，
        # 而 v_port 绑了 trace，用户在编辑框里删字就会触发错误弹窗。
        self.v_port = tk.StringVar(value="5000")
        self.v_prefix = tk.StringVar(value="")
        self.v_upload = tk.BooleanVar(value=True)
        self.v_delete = tk.BooleanVar(value=False)
        self.v_search = tk.BooleanVar(value=True)
        self.v_archive = tk.BooleanVar(value=True)
        self.v_symlink = tk.BooleanVar(value=False)
        self.v_cors = tk.BooleanVar(value=False)
        self.v_custom_ui = tk.BooleanVar(value=True)
        self.v_assets_dir = tk.StringVar(value="")
        self.v_hidden = tk.StringVar(value="")
        self.v_render = tk.StringVar(value="自动列表（默认）")
        self.v_savelog = tk.BooleanVar(value=False)
        self.v_logpath = tk.StringVar(value="")
        self.v_cert = tk.StringVar(value="")
        self.v_key = tk.StringVar(value="")
        self.v_dufs = tk.StringVar(value="")
        self.v_profile = tk.StringVar(value="")
        self.v_status = tk.StringVar(value="未启动")
        self.v_url = tk.StringVar(value="—")

        for v in (self.v_path, self.v_bind, self.v_port, self.v_prefix, self.v_hidden,
                  self.v_render, self.v_logpath, self.v_cert, self.v_key, self.v_profile,
                  self.v_custom_ui, self.v_assets_dir):
            v.trace_add("write", lambda *_: self._refresh_preview())

    def port_from_form(self) -> tuple[int | None, str]:
        """解析端口输入；无效时返回可读提示，不在编辑过程中抛异常。"""
        raw = str(self.v_port.get() or "").strip()
        if not raw:
            return None, "端口不能为空"
        try:
            port = int(raw)
        except ValueError:
            return None, "端口必须是 1-65535 的整数"
        if not 1 <= port <= 65535:
            return None, "端口需在 1-65535 之间"
        return port, ""

    def current_config(self) -> ServerConfig:
        port, _ = self.port_from_form()
        return ServerConfig(
            share_path=self.v_path.get().strip(),
            bind=self.v_bind.get().strip() or "127.0.0.1",
            # 编辑过程中允许暂时非法；用 5000 占位，提交时由 port_from_form 报错
            port=port if port is not None else 5000,
            path_prefix=self.v_prefix.get().strip(),
            allow_upload=self.v_upload.get(),
            allow_delete=self.v_delete.get(),
            allow_search=self.v_search.get(),
            allow_archive=self.v_archive.get(),
            allow_symlink=self.v_symlink.get(),
            enable_cors=self.v_cors.get(),
            custom_ui=self.v_custom_ui.get(),
            assets_dir=self.v_assets_dir.get(),
            hidden=self.v_hidden.get().strip(),
            render_mode=self.v_render.get(),
            save_log=self.v_savelog.get(),
            log_path=self.v_logpath.get().strip(),
            tls_cert=self.v_cert.get().strip(),
            tls_key=self.v_key.get().strip(),
        )

    def load_to_form(self, cfg: ServerConfig) -> None:
        self.v_path.set(cfg.share_path)
        self.v_bind.set(cfg.bind)
        self.v_port.set(str(cfg.port))
        self.v_prefix.set(cfg.path_prefix)
        self.v_upload.set(cfg.allow_upload)
        self.v_delete.set(cfg.allow_delete)
        self.v_search.set(cfg.allow_search)
        self.v_archive.set(cfg.allow_archive)
        self.v_symlink.set(cfg.allow_symlink)
        self.v_cors.set(cfg.enable_cors)
        self.v_custom_ui.set(cfg.custom_ui)
        self.v_assets_dir.set(cfg.assets_dir)
        self.v_hidden.set(cfg.hidden)
        self.v_render.set(cfg.render_mode)
        self.v_savelog.set(cfg.save_log)
        self.v_logpath.set(cfg.log_path)
        self.v_cert.set(cfg.tls_cert)
        self.v_key.set(cfg.tls_key)

    # ---------------- 界面 ----------------
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(18, 14, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="先配置，再开启 · 基于 dufs 的轻量文件共享",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.btn_theme = ttk.Button(header, text="浅色", width=8, command=self._toggle_theme)
        self.btn_theme.grid(row=0, column=1, rowspan=2, sticky="e")

        body = ttk.Frame(self, padding=(14, 4, 14, 4))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3, uniform="col")
        body.columnconfigure(1, weight=4, uniform="col")
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._build_profile_section(left, 0)
        self._build_path_section(left, 1)
        self._build_net_section(left, 2)
        self._build_perm_section(left, 3)
        self._build_advanced_section(left, 4)

        self._build_status_section(right, 0)
        self._build_log_section(right, 1)

        self._build_footer()

    def _section(self, parent: ttk.Frame, row: int, title: str) -> ttk.Frame:
        box = ttk.LabelFrame(parent, text=title, padding=(12, 8, 12, 10))
        box.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        box.columnconfigure(1, weight=1)
        return box

    def _build_profile_section(self, parent: ttk.Frame, row: int) -> None:
        box = self._section(parent, row, "配置方案（可保存多套目录/端口，随时切换）")
        ttk.Label(box, text="方案", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.cmb_profile = ThemedCombobox(box, textvariable=self.v_profile, state="readonly")
        self.cmb_profile.grid(row=0, column=1, sticky="ew", padx=6)
        self.cmb_profile.bind("<<ComboboxSelected>>", lambda e: self._switch_profile())
        btns = ttk.Frame(box)
        btns.grid(row=0, column=2, sticky="e")
        ttk.Button(btns, text="保存", width=6,
                   command=self._save_profile).pack(side="left", padx=2)
        ttk.Button(btns, text="删除", width=6,
                   command=self._delete_profile).pack(side="left", padx=2)
        self.config_widgets += [self.cmb_profile]

    def _build_path_section(self, parent: ttk.Frame, row: int) -> None:
        box = self._section(parent, row, "共享目录")
        self.ent_path = ttk.Entry(box, textvariable=self.v_path)
        self.ent_path.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.btn_browse = ttk.Button(box, text="选择目录…", command=self._browse_dir)
        self.btn_browse.grid(row=0, column=2, padx=(6, 0))
        ttk.Label(box, text="最近使用", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.cmb_recent = ThemedCombobox(box, state="readonly", values=[])
        self.cmb_recent.grid(row=1, column=1, sticky="ew", padx=6)
        self.cmb_recent.bind("<<ComboboxSelected>>", self._use_recent)
        ttk.Label(box, text="要分享单个文件时，直接在上面填文件的完整路径即可",
                  style="Muted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w",
                                             pady=(6, 0))
        self.config_widgets += [self.ent_path, self.btn_browse, self.cmb_recent]

    def _build_net_section(self, parent: ttk.Frame, row: int) -> None:
        box = self._section(parent, row, "网络与接口")
        ttk.Label(box, text="监听地址", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.cmb_bind = ThemedCombobox(box, textvariable=self.v_bind, width=18)
        self.cmb_bind.grid(row=0, column=1, sticky="w", padx=6)
        self.cmb_bind.bind("<<ComboboxSelected>>", lambda e: self._on_bind_change())

        ttk.Label(box, text="端口", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        self.ent_port = ttk.Entry(box, textvariable=self.v_port, width=8)
        self.ent_port.grid(row=0, column=3, sticky="w", padx=6)
        self.btn_port = ttk.Button(box, text="检测", width=6, command=self._check_port)
        self.btn_port.grid(row=0, column=4)

        ttk.Label(box, text="路径前缀", style="Muted.TLabel").grid(row=1, column=0, sticky="w",
                                                                 pady=(8, 0))
        self.ent_prefix = ttk.Entry(box, textvariable=self.v_prefix)
        self.ent_prefix.grid(row=1, column=1, columnspan=3, sticky="ew", padx=6, pady=(8, 0))
        ttk.Label(box, text="留空则用 / ；填 files 会变成 http://ip:5000/files/",
                  style="Muted.TLabel").grid(row=2, column=0, columnspan=5, sticky="w",
                                            pady=(4, 0))
        self.config_widgets += [self.cmb_bind, self.ent_port, self.btn_port, self.ent_prefix]

    def _build_perm_section(self, parent: ttk.Frame, row: int) -> None:
        box = self._section(parent, row, "网页端能力")
        items = [
            (self.v_upload, "允许上传", "网页端可拖拽上传；关闭后为纯只读分享"),
            (self.v_delete, "允许删除", "网页端显示删除按钮并可删除文件/文件夹"),
            (self.v_search, "允许搜索", "网页端显示搜索框"),
            (self.v_archive, "打包下载", "文件夹可下载为 zip"),
            (self.v_symlink, "允许符号链接", "可访问指向共享目录之外的链接（有越权风险）"),
            (self.v_cors, "启用 CORS", "允许跨域访问，前端直连时需要"),
            (self.v_custom_ui, "网页美化界面", "替换 dufs 默认页面样式（自研皮肤，不影响功能）"),
        ]
        for i, (var, text, hint) in enumerate(items):
            cb = ThemedCheckbutton(box, text=text, variable=var, bg_key="panel",
                                   command=lambda v=var, t=text: self._on_perm_change(v, t))
            cb.grid(row=i, column=0, sticky="w")
            ttk.Label(box, text=hint, style="Muted.TLabel").grid(row=i, column=1, sticky="w",
                                                                padx=(10, 0))
            self.config_widgets.append(cb)
        box.columnconfigure(1, weight=1)

    def _build_advanced_section(self, parent: ttk.Frame, row: int) -> None:
        """高级设置只放一个入口按钮，具体内容在弹窗里（避免主界面被撑破）。"""
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=0, sticky="ew")
        holder.columnconfigure(1, weight=1)
        self.btn_adv = ttk.Button(holder, text="高级设置…", command=self._open_advanced)
        self.btn_adv.grid(row=0, column=0, sticky="w")
        ttk.Label(holder, text="隐藏规则 / 渲染模式 / 日志 / HTTPS / dufs 程序",
                  style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=12)

    def _open_advanced(self) -> None:
        """打开高级设置弹窗。已打开则直接置顶。"""
        if self.adv_win is not None and self.adv_win.winfo_exists():
            self.adv_win.lift()
            self.adv_win.focus_force()
            return

        win = tk.Toplevel(self)
        win.title("高级设置")
        win.transient(self)
        # 先 withdraw，等尺寸算完再显示：否则会先闪一下默认位置（多屏时尤其明显）
        win.withdraw()
        self.adv_win = win
        apply_theme(win, self.dark)          # 弹窗跟随当前深浅主题
        win.configure(bg=self.colors["bg"])
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)

        # 可滚动容器：内容超过窗口高度时不会裁切，屏幕矮也能完整操作
        wrap = ttk.Frame(win)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        canvas = tk.Canvas(wrap, highlightthickness=0, borderwidth=0,
                           bg=self.colors["bg"])
        canvas.grid(row=0, column=0, sticky="nsew")
        self._adv_canvas = canvas
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        sb.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=sb.set)

        outer = ttk.Frame(canvas, padding=16)
        outer.columnconfigure(1, weight=1)
        win_id = canvas.create_window((0, 0), window=outer, anchor="nw")

        def _sync_scroll(_e=None) -> None:
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

        def _fit_width(e) -> None:
            try:
                canvas.itemconfigure(win_id, width=e.width)
            except Exception:
                pass

        outer.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", _fit_width)

        def _wheel(e) -> None:
            try:
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass

        def row_label(text: str, r: int) -> None:
            ttk.Label(outer, text=text, style="Muted.TLabel").grid(
                row=r, column=0, sticky="w", pady=(10, 0))

        # 隐藏规则
        row_label("隐藏规则", 0)
        e1 = ttk.Entry(outer, textvariable=self.v_hidden)
        e1.grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=(10, 0))
        ttk.Label(outer, text="逗号分隔，支持通配，如 .git,*.log,tmp",
                  style="Muted.TLabel").grid(row=1, column=1, columnspan=2,
                                             sticky="w", padx=8, pady=(2, 0))

        # 渲染模式
        row_label("渲染模式", 2)
        c1 = ThemedCombobox(outer, textvariable=self.v_render, state="readonly",
                            values=list(RENDER_MODES), width=30)
        c1.grid(row=2, column=1, sticky="w", padx=8, pady=(10, 0))

        # 日志
        cblog = ThemedCheckbutton(outer, text="同时保存日志到文件", bg_key="panel",
                                  variable=self.v_savelog,
                                  command=self._on_savelog_change)
        cblog.grid(row=3, column=0, columnspan=3, sticky="w", pady=(14, 0))
        e2 = ttk.Entry(outer, textvariable=self.v_logpath)
        e2.grid(row=4, column=1, sticky="ew", padx=8, pady=(4, 0))
        ttk.Button(outer, text="选择…", width=8, command=self._pick_log).grid(
            row=4, column=2, padx=(6, 0), pady=(4, 0))

        # HTTPS
        row_label("HTTPS 证书", 5)
        e3 = ttk.Entry(outer, textvariable=self.v_cert)
        e3.grid(row=5, column=1, sticky="ew", padx=8, pady=(10, 0))
        ttk.Button(outer, text="选择…", width=8, command=self._pick_cert).grid(
            row=5, column=2, padx=(6, 0), pady=(10, 0))

        row_label("私钥", 6)
        e4 = ttk.Entry(outer, textvariable=self.v_key)
        e4.grid(row=6, column=1, sticky="ew", padx=8, pady=(4, 0))
        ttk.Button(outer, text="选择…", width=8, command=self._pick_key).grid(
            row=6, column=2, padx=(6, 0), pady=(4, 0))

        # 网页皮肤目录
        row_label("网页皮肤目录", 7)
        ttk.Entry(outer, textvariable=self.v_assets_dir).grid(
            row=7, column=1, sticky="ew", padx=8, pady=(10, 0))
        ttk.Button(outer, text="选择…", width=8, command=self._pick_assets).grid(
            row=7, column=2, padx=(6, 0), pady=(10, 0))
        ttk.Label(outer, text="留空用内置皮肤；也可指向第三方皮肤包（须含 index.html）",
                  style="Muted.TLabel").grid(row=8, column=1, columnspan=2,
                                             sticky="w", padx=8, pady=(2, 0))

        # dufs 程序
        row_label("dufs 程序", 9)
        e5 = ttk.Entry(outer, textvariable=self.v_dufs, state="readonly")
        e5.grid(row=9, column=1, sticky="ew", padx=8, pady=(10, 0))
        ttk.Button(outer, text="更换…", width=8, command=self._pick_dufs).grid(
            row=9, column=2, padx=(6, 0), pady=(10, 0))

        # 底部提示 + 关闭
        hint = ttk.Frame(outer)
        hint.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        hint.columnconfigure(0, weight=1)
        self.lbl_adv_hint = ttk.Label(hint, text="", style="Muted.TLabel",
                                      font=ui_font(9))
        self.lbl_adv_hint.grid(row=0, column=0, sticky="w")
        ttk.Button(hint, text="关闭", width=10, command=win.destroy).grid(row=0, column=1)
        self._refresh_adv_hint()

        def on_close():
            self.adv_win = None
            self._adv_canvas = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

        # 鼠标滚轮：需要绑到每个子控件，否则指针停在输入框上时滚不动
        def _bind_wheel(w) -> None:
            try:
                w.bind("<MouseWheel>", _wheel)
                for c in w.winfo_children():
                    _bind_wheel(c)
            except Exception:
                pass

        _bind_wheel(outer)
        canvas.bind("<MouseWheel>", _wheel)

        # 固定一个足够大的尺寸，再用滚动兜底。
        # 不能依赖 winfo_reqheight()：窗口此时是 withdrawn 状态，Tk 不会计算
        # 子控件几何，reqheight 常常返回 1，算出来的高度反而更小、裁得更狠。
        try:
            sh = win.winfo_screenheight()
            sw = win.winfo_screenwidth()
        except Exception:
            sh, sw = 1080, 1920
        h = max(520, min(760, sh - 120))
        w = max(640, min(720, sw - 80))
        win.minsize(min(640, w), min(480, h))
        win.geometry(f"{w}x{h}")
        center_on_parent(win, self, w, h)
        _sync_scroll()

        win.deiconify()
        win.grab_set()
        win.focus_force()

    def _refresh_adv_hint(self) -> None:
        if self.proc.running:
            self.lbl_adv_hint.configure(
                text="服务运行中，此处修改将在停止后重新开启才生效")
        else:
            self.lbl_adv_hint.configure(text="修改会在下次开启共享时生效")

    def _build_status_section(self, parent: ttk.Frame, row: int) -> None:
        card = ttk.LabelFrame(parent, text="服务状态", padding=(12, 10))
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.columnconfigure(1, weight=1)
        self.dot = tk.Label(card, text="●", font=ui_font(13), bg=self.colors["panel"],
                            fg=self.colors["muted"])
        self.dot.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        self.lbl_status = ttk.Label(card, textvariable=self.v_status, style="Card.TLabel",
                                    font=ui_font(11, "bold"))
        self.lbl_status.grid(row=0, column=1, sticky="w")
        ttk.Label(card, textvariable=self.v_url, style="MutedCard.TLabel",
                  font=ui_font(10)).grid(row=1, column=1, sticky="w", pady=(2, 0))
        ops = ttk.Frame(card)
        ops.grid(row=0, column=2, rowspan=2, sticky="e")
        self.btn_open = ttk.Button(ops, text="打开网页", width=10, command=self._open_browser)
        self.btn_open.pack(side="left", padx=3)
        self.btn_copy = ttk.Button(ops, text="复制地址", width=10, command=self._copy_url)
        self.btn_copy.pack(side="left", padx=3)

    def _build_log_section(self, parent: ttk.Frame, row: int) -> None:
        box = ttk.LabelFrame(parent, text="运行日志", padding=(12, 8))
        box.grid(row=row, column=0, sticky="nsew", pady=(0, 10))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(box, height=10, wrap="none", relief="flat",
                                     font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")
        ops = ttk.Frame(box)
        ops.grid(row=1, column=0, sticky="e", pady=(6, 0))
        ttk.Button(ops, text="清空", width=8, command=self._clear_log).pack(side="left", padx=3)
        ttk.Button(ops, text="导出…", width=8, command=self._export_log).pack(side="left", padx=3)

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, padding=(14, 6, 14, 14))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.lbl_cmd = ttk.Label(footer, text="", style="Muted.TLabel",
                                 font=("Consolas", 9), justify="left", anchor="w")
        self.lbl_cmd.grid(row=0, column=0, sticky="w")
        # 写死 wraplength 会与标签实际宽度不符：换行位置错乱，命令被截成怪样子。
        # 改为按标签真实宽度自适应。
        self.lbl_cmd.bind(
            "<Configure>",
            lambda e: self.lbl_cmd.configure(wraplength=max(160, e.width - 4)))
        self.btn_start = ttk.Button(footer, text="开启共享", style="Accent.TButton",
                                    command=self._start)
        self.btn_start.grid(row=0, column=1, rowspan=2, padx=(10, 0))
        self.btn_stop = ttk.Button(footer, text="停止", style="Danger.TButton",
                                   command=self._stop, state="disabled")
        self.btn_stop.grid(row=0, column=2, padx=(6, 0))

    # ---------------- 异常 ----------------
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
        host = self.v_bind.get().strip() or "127.0.0.1"
        if host in ("0.0.0.0", "::", "[::]"):
            host = "127.0.0.1"
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
            self.dufs_path = dufsbin.install_custom(p)
        except OSError as e:
            messagebox.showerror("无法使用", str(e))
            return
        self.v_dufs.set(str(self.dufs_path))
        self._log(f"已更换 dufs：{self.dufs_path}")

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
        self.load_to_form(ServerConfig.from_dict(self.app_cfg.current_config))
        if self.v_path.get():
            self._add_recent(self.v_path.get())
        self.cmb_bind.configure(values=["127.0.0.1", "0.0.0.0"] + local_ips())
        self.cmb_recent.configure(values=self.app_cfg.recent_paths)
        self._reload_profiles(self.app_cfg.current)
        if self.dufs_path is None:
            self._log("未找到 dufs 可执行文件，请在高级设置里手动指定，或运行 tools/fetch_dufs.py 下载")
        else:
            self.v_dufs.set(str(self.dufs_path))
            v = dufsbin.version(self.dufs_path)
            self._log(f"dufs 就绪：{self.dufs_path}" + (f"（{v}）" if v else ""))

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
        errs = cfg.validate()
        _, port_err = self.port_from_form()
        if port_err:
            errs.insert(0, port_err)
        if errs:
            messagebox.showerror("配置有误", "\n".join(errs))
            return

        binary = dufsbin.ensure_dufs()
        if binary is None:
            if messagebox.askyesno("缺少 dufs",
                                   "没有找到 dufs 可执行文件。\n是否手动选择 dufs.exe？"):
                p = filedialog.askopenfilename(title="选择 dufs.exe")
                if p:
                    binary = dufsbin.install_custom(p)
                else:
                    return
            else:
                return
        self.dufs_path = binary

        # ---- 皮肤诊断 ----
        # dufs 在 --assets 目录不含 index.html 时**不报错**，而是静默回退内置界面，
        # 用户看到"皮肤没生效"却毫无线索。这里在启动前自己核验并写清结论。
        #
        # 目录优先级：用户在高级设置里指定的外部目录 > 内置皮肤目录
        # 皮肤诊断分两步，**必须分开说**：
        #   1) 目录本身是否可用 —— 只是"文件在不在"
        #   2) --assets 是否真的进了命令行 —— 才是"会不会生效"
        # 曾把 1) 单独当作结论打印，导致"核验通过但皮肤没生效"这种自相矛盾的日志：
        # 目录明明是好的，但 cfg.custom_ui 为 False，--assets 压根没传。
        from core.dufsbin import verify_assets_dir

        _args = cfg.to_args()
        _skin_arg = ""
        for _i, _a in enumerate(_args):
            if _a == "--assets" and _i + 1 < len(_args):
                _skin_arg = _args[_i + 1]
                break

        try:
            _ok, _msg = verify_assets_dir(self.skin_dir() or None)
            self._log(("网页皮肤：目录核验通过 " if _ok else "网页皮肤：目录不可用 —— ") + _msg)
        except Exception as e:  # noqa: BLE001
            _tb = traceback.format_exc().strip().splitlines()
            _loc = _tb[-2].strip() if len(_tb) >= 2 else "未知位置"
            self._log(f"网页皮肤：核验异常（{_loc}）{type(e).__name__}: {e}")

        if _skin_arg:
            self._log(f"网页皮肤：已加入 --assets → {_skin_arg}")
        else:
            # custom_ui 的实际值来自 %APPDATA%\DufsGui\config.json，会覆盖代码默认值。
            # 旧版在"皮肤启动失败自动降级"时把它写成 false 并存盘，
            # 一次失败 = 永久关闭。现在降级已不写盘，但**已存在的旧值不会被自动清掉**。
            try:
                _cf = str(config_file())
            except Exception:  # noqa: BLE001
                _cf = "config.json"
            self._log("网页皮肤：本次未传 --assets，网页将是 dufs 默认界面\n"
                      "              原因：配置中 custom_ui=false（勾选「网页美化界面」即可启用）\n"
                      "              该值存于 " + _cf + "，删除此文件可恢复默认")
            if cfg.share_path.strip() and os.path.isfile(cfg.share_path):
                self._log("提示：共享的是单个文件，dufs 会绕过 index.html 模板，皮肤不生效（官方行为）")

        # 官方限制：serve-path 传文件（而非目录）时 index.html 模板被完全绕过，
        # 皮肤必然不生效。提前说明，避免用户以为是皮肤坏了。
        if cfg.share_path.strip() and os.path.isfile(cfg.share_path):
            self._log("提示：共享的是单个文件，dufs 会绕过 index.html 模板，皮肤不生效（官方行为）")

        # 皮肤版本与 dufs 版本不一致时，DOM / 数据契约可能变化
        try:
            from core.dufsbin import version as _vfn, webui_dir as _wd3
            _d3 = _wd3()
            if _d3:
                _av = _d3 / "ASSETS_VERSION"
                _skin_v = _av.read_text(encoding="utf-8").strip() if _av.is_file() else ""
                _dv = ""
                if self.dufs_path:
                    _m2 = re.search(r"(\d+\.\d+\.\d+)", _vfn(self.dufs_path) or "")
                    _dv = _m2.group(1) if _m2 else ""
                if _skin_v and _dv and _skin_v != _dv:
                    self._log(f"提示：网页皮肤版本 {_skin_v} 与 dufs {_dv} 不一致，"
                              f"可执行 python tools/fetch_skin.py {_dv} 重新生成")
        except Exception:  # noqa: BLE001
            pass

        # custom_ui 的实际值来自 %APPDATA%\DufsGui\config.json，会覆盖程序默认值
        if not cfg.custom_ui:
            try:
                _cf = str(config_file())
            except Exception:  # noqa: BLE001
                _cf = "config.json"
            self._log("网页皮肤：未启用（配置中 custom_ui=false）；"
                      "勾选「网页美化界面」即可启用\n"
                      "              若想彻底恢复默认，删除配置文件：" + _cf)

        host_check = "127.0.0.1" if cfg.bind in ("0.0.0.0", "::", "[::]") else cfg.bind
        if port_in_use(cfg.port, host_check):
            free = find_free_port(cfg.port, host_check)
            if not messagebox.askyesno("端口被占用",
                                       f"端口 {cfg.port} 已被占用，改用 {free} 启动？"):
                return
            self.v_port.set(str(free))
            cfg.port = free

        if cfg.allow_symlink and not messagebox.askyesno(
                "安全提示", "允许符号链接可能暴露共享目录之外的文件，确定开启？"):
            return

        args = cfg.to_args()
        try:
            self.proc.start(binary, args)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("启动失败", str(e))
            return

        if not self.proc.wait_ready(cfg.port, host_check, timeout=8):
            out = self.proc.recent_output()
            self.proc.stop()

            # 若带了 --assets（自定义网页皮肤），很可能是它导致启动失败：
            # 自动去掉重试一次，保证皮肤永远不会挡住共享本身。
            retried = False
            if "--assets" in args and cfg.custom_ui:
                self._log("首次启动未就绪，尝试不带自定义网页皮肤重新启动…")
                # 只改本次启动用的临时配置，**不能动界面变量**：
                # 界面变量会在 _start() 末尾被 _save() 持久化，一旦改成 False，
                # 就会被当成“用户主动关闭”写进 config.json，下次启动不再自愈。
                cfg.custom_ui = False
                args = cfg.to_args()
                try:
                    self.proc.start(binary, args)
                    retried = self.proc.wait_ready(cfg.port, host_check, timeout=8)
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

        self.v_status.set(f"运行中 · PID {self.proc.pid}")
        self.v_url.set(cfg.url())
        self._set_status_color("run")
        self._set_config_enabled(False)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._add_recent(cfg.share_path)
        self._save()
        self._log(f"已启动：{cfg.url()}")
        if self.adv_win is not None:
            try:
                self._refresh_adv_hint()
            except Exception:
                pass

    def _stop(self, silent: bool = False) -> None:
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
                elif kind == "exit":
                    if self.proc.running is False and self.v_status.get().startswith("运行中"):
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
        self._save()
        self.destroy()


def main() -> None:
    app = DufsGui()
    app.mainloop()


if __name__ == "__main__":
    main()
