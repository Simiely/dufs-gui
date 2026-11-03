"""主窗口布局：只负责搭控件，不处理启停、配置或进程。

信息层级（macOS 深色风格）：
  顶部：标题 + 右侧「开启共享 / 停止」
  左列：共享目录 → 共享地址（网址优先 + 网卡折叠）→ 配置方案 → 高级入口
  右列：服务状态（状态与操作，不再重复网址）→ 运行日志

层次用背景色差表达（#1e1e1e 底 / #232325 卡片 / #2c2c2e 控件），
卡片圆角 10px，间距按 8pt 栅格；地址列表占据左列剩余高度，不加滚动条。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.theme import DARK, SPACE, fonts

from .addrlist import AddressList
from .bindlist import BindCheckList
from .common import ui_font
from .roundrect import RoundButton, RoundField, RoundPanel, RoundScrollbar, RoundSurface


class MainLayoutMixin:
    """主界面骨架。"""

    # ---------------- 界面 ----------------
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(SPACE["xl"], SPACE["lg"], SPACE["xl"], SPACE["sm"]))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Dufs GUI", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text="固定深色 · 基于 dufs 的轻量文件共享",
                  style="Subtitle.TLabel").grid(row=1, column=0, sticky="w",
                                                pady=(SPACE["xs"], 0))
        actions = ttk.Frame(header)
        actions.grid(row=0, column=1, rowspan=2, sticky="e", padx=(SPACE["md"], 0))
        self.btn_start = RoundButton(actions, "开启共享", command=self._start,
                                     width=98, kind="accent")
        self.btn_start.pack(side="left")
        self.btn_stop = RoundButton(actions, "停止", command=self._stop,
                                    width=72, kind="danger", state="disabled")
        self.btn_stop.pack(side="left", padx=(SPACE["sm"], 0))

        body = ttk.Frame(self, padding=(SPACE["lg"], 0, SPACE["lg"], SPACE["md"]))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=5, uniform="col")
        body.columnconfigure(1, weight=6, uniform="col")
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE["sm"]))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)          # 网卡/地址卡片吃掉左列闲置高度
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

    def _card(self, parent: ttk.Frame, row: int, title: str,
              fill: str = "ew", pady_bottom: int = SPACE["md"],
              expand: bool = False) -> ttk.Frame:
        """10px 圆角卡片；内容区由 RoundPanel.body 提供统一内边距。"""
        panel = RoundPanel(parent, bg=DARK["bg"], radius=10, expand=expand,
                           padding=(SPACE["md"], SPACE["sm"]))
        panel.grid(row=row, column=0, sticky=fill, pady=(0, pady_bottom))
        content = panel.body
        if title:
            ttk.Label(content, text=title, style="CardTitle.TLabel").grid(
                row=0, column=0, columnspan=6, sticky="w", pady=(0, SPACE["sm"]))
        return content

    def _build_profile_card(self, parent: ttk.Frame, row: int) -> None:
        box = self._card(parent, row, "配置方案")
        ttk.Label(box, text="方案", style="MutedCard.TLabel").grid(
            row=1, column=0, sticky="w")
        self.cmb_profile = RoundField(box, kind="combo", width=160, height=32,
                                      bg=DARK["panel"], textvariable=self.v_profile,
                                      state="readonly")
        self.cmb_profile.grid(row=1, column=1, sticky="ew",
                              padx=(SPACE["sm"], SPACE["sm"]))
        self.cmb_profile.bind("<<ComboboxSelected>>", lambda e: self._switch_profile())
        btns = ttk.Frame(box, style="Card.TFrame")
        btns.grid(row=1, column=2, sticky="e")
        RoundButton(btns, "保存", command=self._save_profile, width=56, height=28,
                    radius=8, kind="outline", bg=DARK["panel"],
                    font=ui_font(9)).pack(side="left", padx=(0, SPACE["xs"]))
        RoundButton(btns, "删除", command=self._delete_profile, width=56, height=28,
                    radius=8, kind="outline", bg=DARK["panel"],
                    font=ui_font(9)).pack(side="left")
        self.config_widgets += [self.cmb_profile]

    def _build_path_card(self, parent: ttk.Frame, row: int) -> None:
        box = self._card(parent, row, "共享目录")
        box.columnconfigure(1, weight=1)
        self.ent_path = RoundField(box, textvariable=self.v_path, width=1)
        self.ent_path.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.btn_browse = RoundButton(box, "选择…", command=self._browse_dir,
                                      width=64, height=32, radius=8,
                                      kind="outline", bg=DARK["panel"],
                                      font=ui_font(9, "bold"))
        self.btn_browse.grid(row=1, column=2, padx=(SPACE["sm"], 0))
        self.lbl_recent = ttk.Label(box, text="最近", style="MutedCard.TLabel")
        self.lbl_recent.grid(row=2, column=0, sticky="w",
                             pady=(SPACE["sm"], 0))
        self.cmb_recent = RoundField(box, kind="combo", width=1, height=32,
                                     bg=DARK["panel"], state="readonly", values=[])
        self.cmb_recent.grid(row=2, column=1, columnspan=2, sticky="ew",
                             padx=(SPACE["sm"], 0), pady=(SPACE["sm"], 0))
        self.cmb_recent.bind("<<ComboboxSelected>>", self._use_recent)
        self.lbl_recent.grid_remove()
        self.cmb_recent.grid_remove()
        self.config_widgets += [self.ent_path, self.btn_browse, self.cmb_recent]

    def _build_net_card(self, parent: ttk.Frame, row: int) -> None:
        """共享地址卡片：网址优先；网卡明细默认折叠，状态在会话内记住。"""
        box = self._card(parent, row, "", fill="nsew", expand=True,
                         pady_bottom=SPACE["md"])
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)

        head = ttk.Frame(box, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["sm"]))
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="共享地址", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w")
        self.lbl_addr_count = ttk.Label(head, text="", style="MutedCard.TLabel",
                                        font=f_small())
        self.lbl_addr_count.grid(row=0, column=1, sticky="e")

        self.addr_list = AddressList(box, on_copy=self._copy_one_url,
                                     on_overflow=self._on_addr_overflow)
        self.addr_list.grid(row=1, column=0, sticky="nsew")

        self.lbl_binds_toggle = ttk.Label(box, text="", style="MutedCard.TLabel",
                                          font=f_small(), cursor="hand2")
        self.lbl_binds_toggle.grid(row=2, column=0, sticky="w",
                                   pady=(SPACE["sm"], 0))
        self.lbl_binds_toggle.bind("<Button-1>", lambda e: self._toggle_binds())

        self.binds_holder = tk.Frame(box, bg=DARK["panel"])
        self.binds_holder.grid(row=3, column=0, sticky="ew",
                               pady=(SPACE["xs"], 0))
        self.binds_holder.columnconfigure(0, weight=1)
        dhead = tk.Frame(self.binds_holder, bg=DARK["panel"])
        dhead.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["xs"]))
        dhead.columnconfigure(0, weight=1)
        tk.Label(dhead, text="网卡明细 · 勾选要监听的地址", bg=DARK["panel"],
                 fg=DARK["muted"], font=f_small(), anchor="w").grid(
            row=0, column=0, sticky="w")
        RoundButton(dhead, "全部", command=self._select_all_binds, width=48,
                    height=24, radius=6, kind="outline", bg=DARK["panel"],
                    font=ui_font(8)).grid(row=0, column=1, sticky="e")

        self.bindlist = BindCheckList(self.binds_holder,
                                      on_change=self._on_binds_change)
        self.bindlist.grid(row=1, column=0, sticky="nsew")
        self.bindlist.canvas.configure(bg=DARK["panel"])
        self.binds_holder.rowconfigure(1, weight=1)

        port_row = ttk.Frame(box, style="Card.TFrame")
        port_row.grid(row=4, column=0, sticky="ew", pady=(SPACE["sm"], 0))
        ttk.Label(port_row, text="端口", style="MutedCard.TLabel").pack(
            side="left", padx=(0, SPACE["sm"]))
        self.ent_port = RoundField(port_row, textvariable=self.v_port, width=64,
                                   height=28)
        self.ent_port.pack(side="left")
        self.btn_port = RoundButton(port_row, "检测", command=self._check_port,
                                    width=52, height=28, radius=8, kind="outline",
                                    bg=DARK["panel"], font=ui_font(9))
        self.btn_port.pack(side="left", padx=(SPACE["sm"], 0))
        ttk.Label(port_row, text="多个网卡共用同一端口", style="MutedCard.TLabel",
                  font=f_small()).pack(side="left", padx=(SPACE["md"], 0))

        self.config_widgets += [self.bindlist, self.ent_port, self.btn_port]
        self._binds_expanded = False
        self._apply_binds_expanded()

    def _build_advanced_card(self, parent: ttk.Frame, row: int) -> None:
        """高级设置只保留一个入口，内容全部收进弹窗。"""
        box = self._card(parent, row, "", pady_bottom=0)
        box.columnconfigure(1, weight=1)
        self.btn_adv = RoundButton(box, "高级设置…", command=self._open_advanced,
                                   width=96, height=28, radius=8, kind="outline",
                                   bg=DARK["panel"], font=ui_font(9))
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
        # 网址只在左栏展示；这里保留状态与操作，避免同屏重复表达
        # 文字 + 1px 描边的二维码入口；圆角 8px，hover/pressed 有状态
        self.btn_qr = RoundButton(box, "二维码", command=self._open_qr,
                                  width=74, height=32, radius=8, kind="outline",
                                  bg=DARK["panel"], font=ui_font(9, "bold"))
        self.btn_qr.grid(row=1, column=2, sticky="e", padx=(SPACE["sm"], 0))

        self.status_rows_host = tk.Frame(box, bg=DARK["panel"])
        self.status_rows_host.grid(row=2, column=0, columnspan=3, sticky="ew",
                                   pady=(SPACE["xs"], 0))
        self.status_rows_host.columnconfigure(0, weight=1)

        ops = ttk.Frame(box, style="Card.TFrame")
        ops.grid(row=3, column=0, columnspan=3, sticky="w", pady=(SPACE["sm"], 0))
        self.btn_open = RoundButton(ops, "打开网页", command=self._open_browser,
                                    width=80, height=28, radius=8, kind="outline",
                                    bg=DARK["panel"], font=ui_font(9))
        self.btn_open.pack(side="left", padx=(0, SPACE["sm"]))
        self.btn_copy = RoundButton(ops, "复制地址", command=self._copy_url,
                                    width=80, height=28, radius=8, kind="outline",
                                    bg=DARK["panel"], font=ui_font(9))
        self.btn_copy.pack(side="left")

        # 失败详情：没有失败时整块 grid_remove（不占空白），有失败才出现
        self.detail_holder = tk.Frame(box, bg=DARK["panel"])
        self.detail_holder.grid(row=4, column=0, columnspan=3, sticky="ew",
                                pady=(SPACE["sm"], 0))
        self.detail_holder.columnconfigure(0, weight=1)
        dhead = tk.Frame(self.detail_holder, bg=DARK["panel"])
        dhead.grid(row=0, column=0, sticky="ew")
        dhead.columnconfigure(0, weight=1)
        self.lbl_detail_title = tk.Label(dhead, text="启动失败详情", bg=DARK["panel"],
                                         fg=DARK["danger"], font=ui_font(9, "bold"),
                                         anchor="w")
        self.lbl_detail_title.grid(row=0, column=0, sticky="w")
        self.btn_detail_toggle = RoundButton(dhead, "展开", width=48, height=24,
                                             radius=6, kind="outline",
                                             bg=DARK["panel"], font=ui_font(8),
                                             command=self._toggle_detail)
        self.btn_detail_toggle.grid(row=0, column=1, sticky="e")
        self.detail_body = tk.Frame(self.detail_holder, bg=DARK["panel"])
        self.detail_body.grid(row=1, column=0, sticky="ew", pady=(SPACE["xs"], 0))
        self.detail_body.columnconfigure(0, weight=1)
        detail_surface = RoundSurface(self.detail_body, bg=DARK["panel"],
                                      fill=DARK["well"], border=None, radius=8,
                                      autoheight=True)
        detail_surface.grid(row=0, column=0, sticky="ew")
        self.detail_text = tk.Text(detail_surface.body, height=3, width=1,
                                   wrap="word", relief="flat", borderwidth=0,
                                   font=fonts()["caption"],
                                   bg=DARK["well"], fg="#e5e5e7",
                                   insertbackground=DARK["fg"],
                                   selectbackground=DARK["accent"],
                                   selectforeground=DARK["accent_fg"],
                                   padx=SPACE["sm"], pady=SPACE["xs"])
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.configure(state="disabled")
        self.detail_holder.grid_remove()
        self.detail_expanded = True

    def _build_log_card(self, parent: ttk.Frame, row: int) -> None:
        box = self._card(parent, row, "", fill="nsew", pady_bottom=0, expand=True)
        box.rowconfigure(1, weight=1)
        box.columnconfigure(0, weight=1)

        head = ttk.Frame(box, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["sm"]))
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="运行日志", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 0))
        RoundButton(head, "清空", command=self._clear_log, width=48, height=24,
                    radius=6, kind="outline", bg=DARK["panel"],
                    font=ui_font(8)).grid(row=0, column=1, padx=(0, SPACE["xs"]))
        # 导出按钮放在卡片标题行，避免被窗口右边缘裁切
        RoundButton(head, "导出…", command=self._export_log, width=56, height=24,
                    radius=6, kind="outline", bg=DARK["panel"],
                    font=ui_font(8)).grid(row=0, column=2)

        # 日志区：圆角 well 包裹原生 Text；滚动条滑块自身也圆角
        well = RoundSurface(box, bg=DARK["panel"], fill=DARK["well"],
                            border=None, radius=8)
        well.grid(row=1, column=0, sticky="nsew")
        logbox = well.body
        logbox.columnconfigure(0, weight=1)
        logbox.rowconfigure(0, weight=1)
        self.log_text = tk.Text(logbox, height=10, width=1, wrap="none", relief="flat",
                                font=fonts()["mono"], borderwidth=0,
                                bg=DARK["well"], fg="#e5e5e7",
                                insertbackground=DARK["fg"],
                                selectbackground=DARK["accent"],
                                selectforeground=DARK["accent_fg"],
                                padx=SPACE["xs"], pady=SPACE["xs"])
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_vsb = RoundScrollbar(logbox, orient="vertical",
                                      command=self.log_text.yview, thickness=10)
        self.log_vsb.grid(row=0, column=1, sticky="ns")
        self.log_hsb = RoundScrollbar(logbox, orient="horizontal",
                                      command=self.log_text.xview, thickness=10)
        self.log_hsb.grid(row=1, column=0, sticky="ew")
        self.log_text.configure(yscrollcommand=self.log_vsb.set,
                                xscrollcommand=self.log_hsb.set)
        self.log_scrollbars = (self.log_vsb, self.log_hsb)
        self.log_text.configure(state="disabled")


def f_small():
    return fonts()["caption"]
