"""主窗口布局：只负责搭控件，不处理启停、配置或进程。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from core.theme import ThemedCheckbutton, ThemedCombobox

from .common import APP_NAME, ui_font


class MainLayoutMixin:
    """主界面骨架。

    曾把这些构建代码和业务逻辑混在一个 1000+ 行的类里；拆开后布局改动
    不会再顺带碰到启停流程，测试也能更容易定位界面回归。
    """

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
        ttk.Label(holder, text="隐藏规则 / 渲染模式 / 日志 / HTTPS / 访问口令 / dufs 程序",
                  style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=12)

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
