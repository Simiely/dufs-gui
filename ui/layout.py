"""主窗口布局：只负责搭控件，不处理启停、配置或进程。

信息层级（macOS 深色风格）：
  左列：共享目录 → 共享网卡（勾选列表 + 端口）→ 配置方案 → 高级入口
  右列：服务状态（每地址一行）→ 运行日志
  底部：命令预览 + 开启/停止

层次用背景色差表达（#1e1e1e 底 / #232325 卡片 / #2c2c2e 控件），
卡片只保留 1px 低对比描边；间距按 8pt 栅格，组间大于组内。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.theme import DARK, SPACE, ThemedCombobox, fonts

from .bindlist import BindCheckList
from .common import APP_NAME, ui_font


class MainLayoutMixin:
    """主界面骨架。"""

    # ---------------- 界面 ----------------
    def _build_ui(self) -> None:
        f = fonts()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(SPACE["xl"], SPACE["lg"], SPACE["xl"], SPACE["sm"]))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text="固定深色 · 基于 dufs 的轻量文件共享",
                  style="Subtitle.TLabel").grid(row=1, column=0, sticky="w",
                                                pady=(SPACE["xs"], 0))

        body = ttk.Frame(self, padding=(SPACE["lg"], 0, SPACE["lg"], SPACE["sm"]))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=5, uniform="col")
        body.columnconfigure(1, weight=6, uniform="col")
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE["sm"]))
        left.columnconfigure(0, weight=1)
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(SPACE["sm"], 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._build_path_card(left, 0)
        self._build_net_card(left, 1)
        self._build_profile_card(left, 2)
        self._build_advanced_card(left, 3)

        self._build_status_card(right, 0)
        self._build_log_card(right, 1)

        self._build_footer()

    def _card(self, parent: ttk.Frame, row: int, title: str,
              fill: str = "ew", pady_bottom: int = SPACE["md"]) -> ttk.Frame:
        """1px 低对比描边的卡片；内容区统一 16px 内边距。"""
        c = DARK
        outer = tk.Frame(parent, bg=c["panel"], bd=0,
                         highlightbackground=c["border"], highlightthickness=1)
        outer.grid(row=row, column=0, sticky=fill, pady=(0, pady_bottom))
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        content = ttk.Frame(outer, style="Card.TFrame",
                            padding=(SPACE["lg"], SPACE["md"]))
        content.grid(row=0, column=0, sticky="nsew")
        if title:
            ttk.Label(content, text=title, style="CardTitle.TLabel").grid(
                row=0, column=0, columnspan=6, sticky="w", pady=(0, SPACE["sm"]))
        return content

    def _build_profile_card(self, parent: ttk.Frame, row: int) -> None:
        box = self._card(parent, row, "配置方案")
        ttk.Label(box, text="方案", style="MutedCard.TLabel").grid(
            row=1, column=0, sticky="w")
        self.cmb_profile = ThemedCombobox(box, textvariable=self.v_profile,
                                          state="readonly", width=18)
        self.cmb_profile.grid(row=1, column=1, sticky="ew",
                              padx=(SPACE["sm"], SPACE["sm"]))
        self.cmb_profile.bind("<<ComboboxSelected>>", lambda e: self._switch_profile())
        btns = ttk.Frame(box, style="Card.TFrame")
        btns.grid(row=1, column=2, sticky="e")
        ttk.Button(btns, text="保存", width=6,
                   command=self._save_profile).pack(side="left", padx=(0, SPACE["xs"]))
        ttk.Button(btns, text="删除", width=6,
                   command=self._delete_profile).pack(side="left")
        self.config_widgets += [self.cmb_profile]

    def _build_path_card(self, parent: ttk.Frame, row: int) -> None:
        box = self._card(parent, row, "共享目录")
        box.columnconfigure(1, weight=1)
        self.ent_path = ttk.Entry(box, textvariable=self.v_path)
        self.ent_path.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.btn_browse = ttk.Button(box, text="选择…", width=7,
                                     command=self._browse_dir)
        self.btn_browse.grid(row=1, column=2, padx=(SPACE["sm"], 0))
        ttk.Label(box, text="最近", style="MutedCard.TLabel").grid(
            row=2, column=0, sticky="w", pady=(SPACE["sm"], 0))
        self.cmb_recent = ThemedCombobox(box, state="readonly", values=[])
        self.cmb_recent.grid(row=2, column=1, columnspan=2, sticky="ew",
                             padx=(SPACE["sm"], 0), pady=(SPACE["sm"], 0))
        self.cmb_recent.bind("<<ComboboxSelected>>", self._use_recent)
        ttk.Label(box, text="也可以直接填写单个文件的完整路径",
                  style="MutedCard.TLabel", font=f_small()).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(SPACE["xs"], 0))
        self.config_widgets += [self.ent_path, self.btn_browse, self.cmb_recent]

    def _build_net_card(self, parent: ttk.Frame, row: int) -> None:
        box = self._card(parent, row, "")
        box.columnconfigure(0, weight=1)

        self.lbl_binds = ttk.Label(box, text="共享网卡（已选 0 个）", style="CardTitle.TLabel")
        self.lbl_binds.grid(row=0, column=0, sticky="w", pady=(0, SPACE["sm"]))

        self.bindlist = BindCheckList(box, on_change=self._on_binds_change)
        self.bindlist.grid(row=1, column=0, sticky="nsew")
        self.bindlist.canvas.configure(bg=DARK["panel"])

        port_row = ttk.Frame(box, style="Card.TFrame")
        port_row.grid(row=2, column=0, sticky="ew", pady=(SPACE["sm"], 0))
        ttk.Label(port_row, text="端口", style="MutedCard.TLabel").pack(
            side="left", padx=(0, SPACE["sm"]))
        self.ent_port = ttk.Entry(port_row, textvariable=self.v_port, width=7)
        self.ent_port.pack(side="left")
        self.btn_port = ttk.Button(port_row, text="检测", style="Ghost.TButton",
                                   command=self._check_port)
        self.btn_port.pack(side="left", padx=(SPACE["sm"], 0))
        ttk.Label(port_row, text="多个网卡共用同一端口", style="MutedCard.TLabel",
                  font=f_small()).pack(side="left", padx=(SPACE["md"], 0))

        self.config_widgets += [self.bindlist, self.ent_port, self.btn_port]

    def _build_advanced_card(self, parent: ttk.Frame, row: int) -> None:
        """高级设置只保留一个入口，内容全部收进弹窗。"""
        box = self._card(parent, row, "", pady_bottom=0)
        box.columnconfigure(1, weight=1)
        self.btn_adv = ttk.Button(box, text="高级设置…", width=11,
                                  command=self._open_advanced)
        self.btn_adv.grid(row=0, column=0, sticky="w")
        ttk.Label(box, text="路径前缀、网页能力、口令、皮肤、dufs 程序",
                  style="MutedCard.TLabel", font=f_small()).grid(
            row=0, column=1, sticky="w", padx=(SPACE["md"], 0))

    def _build_status_card(self, parent: ttk.Frame, row: int) -> None:
        box = self._card(parent, row, "服务状态", pady_bottom=SPACE["md"])
        box.columnconfigure(1, weight=1)

        self.dot = tk.Label(box, text="●", font=ui_font(12),
                            bg=DARK["panel"], fg=DARK["muted"])
        self.dot.grid(row=1, column=0, sticky="nw", padx=(0, SPACE["sm"]))
        self.lbl_status = ttk.Label(box, textvariable=self.v_status,
                                    style="Card.TLabel", font=ui_font(11, "bold"))
        self.lbl_status.grid(row=1, column=1, sticky="w")
        self.lbl_url = ttk.Label(box, textvariable=self.v_url, style="Status.TLabel",
                                 font=ui_font(9), anchor="w")
        self.lbl_url.grid(row=2, column=1, sticky="ew", pady=(0, SPACE["sm"]))

        self.status_rows_host = tk.Frame(box, bg=DARK["panel"])
        self.status_rows_host.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.status_rows_host.columnconfigure(0, weight=1)

        ops = ttk.Frame(box, style="Card.TFrame")
        ops.grid(row=4, column=0, columnspan=3, sticky="w", pady=(SPACE["sm"], 0))
        self.btn_open = ttk.Button(ops, text="打开网页", width=9,
                                   command=self._open_browser)
        self.btn_open.pack(side="left", padx=(0, SPACE["sm"]))
        self.btn_copy = ttk.Button(ops, text="复制地址", width=9,
                                   command=self._copy_url)
        self.btn_copy.pack(side="left", padx=(0, SPACE["sm"]))
        self.btn_detail = ttk.Button(ops, text="失败详情…", style="Ghost.TButton",
                                     command=self._show_failures, state="disabled")
        self.btn_detail.pack(side="left")

    def _build_log_card(self, parent: ttk.Frame, row: int) -> None:
        box = self._card(parent, row, "", fill="nsew", pady_bottom=0)
        box.rowconfigure(1, weight=1)
        box.columnconfigure(0, weight=1)

        head = ttk.Frame(box, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["sm"]))
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="运行日志", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 0))
        ttk.Button(head, text="清空", style="Ghost.TButton",
                   command=self._clear_log).grid(row=0, column=1, padx=(0, SPACE["xs"]))
        # 导出按钮放在卡片标题行，避免被窗口右边缘裁切
        ttk.Button(head, text="导出…", style="Ghost.TButton",
                   command=self._export_log).grid(row=0, column=2)

        logbox = tk.Frame(box, bg=DARK["well"], highlightthickness=0, bd=0)
        logbox.grid(row=1, column=0, sticky="nsew")
        logbox.columnconfigure(0, weight=1)
        logbox.rowconfigure(0, weight=1)
        self.log_text = tk.Text(logbox, height=10, width=1, wrap="none", relief="flat",
                                font=fonts()["mono"], borderwidth=0,
                                bg=DARK["well"], fg="#e5e5e7",
                                insertbackground=DARK["fg"],
                                selectbackground=DARK["accent"],
                                selectforeground=DARK["accent_fg"],
                                padx=SPACE["sm"], pady=SPACE["xs"])
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_vsb = ttk.Scrollbar(logbox, orient="vertical",
                                     command=self.log_text.yview)
        self.log_vsb.grid(row=0, column=1, sticky="ns")
        self.log_hsb = ttk.Scrollbar(logbox, orient="horizontal",
                                     command=self.log_text.xview)
        self.log_hsb.grid(row=1, column=0, sticky="ew")
        self.log_text.configure(yscrollcommand=self.log_vsb.set,
                                xscrollcommand=self.log_hsb.set)
        self.log_scrollbars = (self.log_vsb, self.log_hsb)
        self.log_text.configure(state="disabled")

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, padding=(SPACE["lg"], SPACE["sm"],
                                          SPACE["lg"], SPACE["md"]))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        footer.rowconfigure(0, minsize=48)
        # 用 Message 自动按宽度换行：避免写死 wraplength 后与实际宽度不符，
        # 命令被截断或换行位置错乱。
        self.lbl_cmd = tk.Message(footer, text="", width=520, justify="left",
                                  anchor="w", bg=DARK["bg"], fg=DARK["muted"],
                                  font=("Consolas", 9), padx=0, pady=0)
        self.lbl_cmd.grid(row=0, column=0, sticky="w")
        actions = ttk.Frame(footer)
        actions.grid(row=0, column=1, sticky="e", padx=(SPACE["md"], 0))
        self.btn_start = ttk.Button(actions, text="开启共享", width=10,
                                    style="Accent.TButton", command=self._start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(actions, text="停止", width=7,
                                   style="Danger.TButton", command=self._stop,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=(SPACE["sm"], 0))


def f_small():
    return fonts()["caption"]
