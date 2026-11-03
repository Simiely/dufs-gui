"""高级设置弹窗：内容多且可滚动，单独拆出避免主窗口继续膨胀。

视觉：与主界面同一套 macOS 深色 token，用卡片分组 + 8pt 栅格，
而不是每个字段都画框。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core import webtweak
from core.config import RENDER_MODES
from core.theme import (DARK, SPACE, ThemedCheckbutton, apply_theme,
                        enable_windows_dark_titlebar,
                        enable_windows_rounded_corners, fonts)
from core.winpos import center_on_parent

from .common import ui_font
from .roundrect import RoundButton, RoundField, RoundPanel, RoundScrollbar


class AdvancedDialogMixin:
    """高级设置弹窗的构建与提示刷新。"""

    # ---------------- 高级设置 ----------------
    def _open_advanced(self) -> None:
        """打开高级设置弹窗。已打开则直接置顶。"""
        if self.adv_win is not None and self.adv_win.winfo_exists():
            self.adv_win.lift()
            self.adv_win.focus_force()
            return

        c = DARK
        f = fonts()
        win = tk.Toplevel(self)
        win.title("高级设置")
        win.transient(self)
        # 先 withdraw，等尺寸算完再显示：否则会先闪一下默认位置（多屏时尤其明显）
        win.withdraw()
        self.adv_win = win
        apply_theme(win)
        win.configure(bg=c["bg"])
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)

        # 可滚动容器：内容超过窗口高度时不会裁切，屏幕矮也能完整操作
        wrap = ttk.Frame(win)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        canvas = tk.Canvas(wrap, highlightthickness=0, borderwidth=0, bg=c["bg"])
        canvas.grid(row=0, column=0, sticky="nsew")
        self._adv_canvas = canvas
        sb = RoundScrollbar(wrap, orient="vertical", command=canvas.yview,
                            bg=c["bg"], thickness=10)
        sb.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=sb.set)

        outer = ttk.Frame(canvas, padding=(SPACE["lg"], SPACE["lg"]))
        outer.columnconfigure(0, weight=1)
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

        cards: list[ttk.Frame] = []

        def card(title: str) -> ttk.Frame:
            panel = RoundPanel(outer, bg=c["bg"], radius=10)
            panel.grid(row=len(cards), column=0, sticky="ew", pady=(0, SPACE["md"]))
            inner = panel.body
            inner.columnconfigure(1, weight=1)
            ttk.Label(inner, text=title, style="CardTitle.TLabel").grid(
                row=0, column=0, columnspan=3, sticky="w", pady=(0, SPACE["sm"]))
            cards.append(inner)
            return inner

        def field(box: ttk.Frame, row: int, text: str, var, browse=None,
                  show: str | None = None) -> RoundField:
            ttk.Label(box, text=text, style="MutedCard.TLabel").grid(
                row=row, column=0, sticky="w", pady=(SPACE["xs"], 0))
            entry = RoundField(box, textvariable=var, show=show, width=1,
                               height=32, bg=c["panel"])
            entry.grid(row=row, column=1, sticky="ew", padx=(SPACE["sm"], 0),
                       pady=(SPACE["xs"], 0))
            if browse is not None:
                RoundButton(box, "选择…", command=browse, width=64, height=28,
                            radius=8, kind="outline", bg=c["panel"],
                            font=ui_font(9)).grid(row=row, column=2,
                                                  padx=(SPACE["sm"], 0),
                                                  pady=(SPACE["xs"], 0))
            return entry

        def hint(box: ttk.Frame, row: int, text: str) -> None:
            ttk.Label(box, text=text, style="MutedCard.TLabel",
                      font=f["caption"], justify="left").grid(
                row=row, column=1, columnspan=2, sticky="w",
                padx=(SPACE["sm"], 0), pady=(SPACE["xs"], 0))

        # ---- 网页外观（浏览器标签页标题 / 图标）----
        box = card("网页外观（浏览器标签页）")
        ttk.Label(box, text="网页标题", style="MutedCard.TLabel").grid(
            row=1, column=0, sticky="w", pady=(SPACE["xs"], 0))
        self.ent_web_title = RoundField(box, textvariable=self.v_web_title,
                                        width=1, height=32, bg=c["panel"])
        self.ent_web_title.grid(row=1, column=1, sticky="ew",
                                padx=(SPACE["sm"], 0), pady=(SPACE["xs"], 0))
        RoundButton(box, "应用", command=self._apply_web_meta, width=56, height=28,
                    radius=8, kind="accent", bg=c["panel"],
                    font=ui_font(9, "bold")).grid(
            row=1, column=2, padx=(SPACE["sm"], 0), pady=(SPACE["xs"], 0))
        ttk.Label(box, text="留空使用 dufs 官方标题；最长 48 字符。"
                            "只改浏览器标签，不改 GUI 窗口标题",
                  style="MutedCard.TLabel", font=f["caption"],
                  justify="left").grid(row=2, column=1, columnspan=2, sticky="w",
                                       padx=(SPACE["sm"], 0), pady=(SPACE["xs"], 0))

        ttk.Label(box, text="站点图标", style="MutedCard.TLabel").grid(
            row=3, column=0, sticky="w", pady=(SPACE["sm"], 0))
        RoundField(box, textvariable=self.v_favicon_path, state="readonly",
                   width=1, height=32, bg=c["panel"]).grid(
            row=3, column=1, sticky="ew", padx=(SPACE["sm"], 0),
            pady=(SPACE["sm"], 0))
        fav_btns = ttk.Frame(box, style="Card.TFrame")
        fav_btns.grid(row=3, column=2, sticky="e", padx=(SPACE["sm"], 0),
                      pady=(SPACE["sm"], 0))
        RoundButton(fav_btns, "选择…", command=self._pick_favicon, width=60,
                    height=28, radius=8, kind="outline", bg=c["panel"],
                    font=ui_font(9)).pack(side="left")
        RoundButton(fav_btns, "默认", command=self._reset_favicon, width=48,
                    height=28, radius=8, kind="outline", bg=c["panel"],
                    font=ui_font(9)).pack(side="left", padx=(SPACE["xs"], 0))
        ttk.Label(box, text="选择 .ico 文件；留空使用 dufs 官方图标。"
                            "需勾选「网页美化界面」并在下次开启共享后生效",
                  style="MutedCard.TLabel", font=f["caption"],
                  justify="left").grid(row=4, column=1, columnspan=2, sticky="w",
                                       padx=(SPACE["sm"], 0), pady=(SPACE["xs"], 0))
        self.lbl_web_hint = ttk.Label(box, text="", style="MutedCard.TLabel",
                                      font=f["caption"])
        self.lbl_web_hint.grid(row=5, column=1, columnspan=2, sticky="w",
                               padx=(SPACE["sm"], 0), pady=(SPACE["xs"], 0))
        self.ent_web_title.bind("<Return>", lambda e: self._apply_web_meta())

        # ---- 路径前缀 ----
        box = card("路径前缀")
        field(box, 1, "URL 前缀", self.v_prefix)
        hint(box, 2, "留空用 /；填 files 会变成 http://ip:端口/files/")

        # ---- 网页端能力 ----
        box = card("网页端能力")
        items = [
            (self.v_upload, "允许上传", "网页端可拖拽上传；关闭后为纯只读分享"),
            (self.v_delete, "允许删除", "网页端显示删除按钮并可删除文件/文件夹"),
            (self.v_search, "允许搜索", "网页端显示搜索框"),
            (self.v_archive, "打包下载", "文件夹可下载为 zip"),
            (self.v_symlink, "允许符号链接", "可访问指向共享目录之外的链接（有越权风险）"),
            (self.v_cors, "启用 CORS", "允许跨域访问，前端直连时需要"),
            (self.v_custom_ui, "网页美化界面", "替换 dufs 默认页面样式（不影响功能）"),
        ]
        for i, (var, text, desc) in enumerate(items):
            r = i + 1
            cb = ThemedCheckbutton(box, text=text, variable=var, bg_key="panel",
                                   command=lambda v=var: self._on_perm_change(v, ""))
            cb.grid(row=r, column=0, sticky="w", pady=(SPACE["xs"], 0))
            ttk.Label(box, text=desc, style="MutedCard.TLabel", font=f["caption"]).grid(
                row=r, column=1, columnspan=2, sticky="w",
                padx=(SPACE["sm"], 0), pady=(SPACE["xs"], 0))
            self.config_widgets.append(cb)

        # ---- 文件与渲染 ----
        box = card("文件与渲染")
        field(box, 1, "隐藏规则", self.v_hidden)
        hint(box, 2, "逗号分隔，支持通配，如 .git,*.log,tmp")
        ttk.Label(box, text="渲染模式", style="MutedCard.TLabel").grid(
            row=3, column=0, sticky="w", pady=(SPACE["sm"], 0))
        RoundField(box, kind="combo", textvariable=self.v_render,
                   state="readonly", values=list(RENDER_MODES), width=180,
                   height=32, bg=c["panel"]).grid(
            row=3, column=1, sticky="w", padx=(SPACE["sm"], 0),
            pady=(SPACE["sm"], 0))

        # ---- 运行日志 ----
        box = card("运行日志")
        cblog = ThemedCheckbutton(box, text="同时保存日志到文件", bg_key="panel",
                                  variable=self.v_savelog,
                                  command=self._on_savelog_change)
        cblog.grid(row=1, column=0, columnspan=3, sticky="w", pady=(SPACE["xs"], 0))
        ttk.Label(box, text="日志文件", style="MutedCard.TLabel").grid(
            row=2, column=0, sticky="w", pady=(SPACE["sm"], 0))
        RoundField(box, textvariable=self.v_logpath, width=1, height=32,
                   bg=c["panel"]).grid(
            row=2, column=1, sticky="ew", padx=(SPACE["sm"], 0), pady=(SPACE["sm"], 0))
        RoundButton(box, "选择…", command=self._pick_log, width=64, height=28,
                    radius=8, kind="outline", bg=c["panel"],
                    font=ui_font(9)).grid(
            row=2, column=2, padx=(SPACE["sm"], 0), pady=(SPACE["sm"], 0))

        # ---- HTTPS ----
        box = card("HTTPS")
        field(box, 1, "证书", self.v_cert, self._pick_cert)
        field(box, 2, "私钥", self.v_key, self._pick_key)
        hint(box, 3, "两项都填才会启用 HTTPS；证书与私钥需匹配")

        # ---- 访问口令（可选）----
        box = card("访问口令（可选）")
        field(box, 1, "用户名", self.v_auth_user)
        self.ent_auth_pass = field(box, 2, "密码", self.v_auth_pass,
                                   show="*")
        hint(box, 3, "留空即为匿名访问（不鉴权）；填了就生效。"
                     "口令明文保存在配置文件中，跨公网共享请自行启用 HTTPS")

        # ---- 网页皮肤 ----
        box = card("网页皮肤")
        field(box, 1, "皮肤目录", self.v_assets_dir, self._pick_assets)
        hint(box, 2, "留空用内置皮肤；也可指向第三方皮肤包（须含 index.html）")

        # ---- dufs 程序 ----
        box = card("dufs 程序")
        ttk.Label(box, text="程序路径", style="MutedCard.TLabel").grid(
            row=1, column=0, sticky="w", pady=(SPACE["xs"], 0))
        RoundField(box, textvariable=self.v_dufs, state="readonly", width=1,
                   height=32, bg=c["panel"]).grid(
            row=1, column=1, sticky="ew", padx=(SPACE["sm"], 0),
            pady=(SPACE["xs"], 0))
        RoundButton(box, "更换…", command=self._pick_dufs, width=64, height=28,
                    radius=8, kind="outline", bg=c["panel"],
                    font=ui_font(9)).grid(
            row=1, column=2, padx=(SPACE["sm"], 0), pady=(SPACE["xs"], 0))

        # 底部固定条：关闭按钮始终可见，不用滚到最底下才能退出
        ttk.Separator(win, orient="horizontal").grid(row=1, column=0, sticky="ew")
        foot = ttk.Frame(win, padding=(SPACE["lg"], SPACE["sm"],
                                       SPACE["lg"], SPACE["md"]))
        foot.grid(row=2, column=0, sticky="ew")
        foot.columnconfigure(0, weight=1)
        self.lbl_adv_hint = ttk.Label(foot, text="", style="Muted.TLabel",
                                      font=ui_font(9))
        self.lbl_adv_hint.grid(row=0, column=0, sticky="w")
        RoundButton(foot, "关闭", command=win.destroy, width=72, height=28,
                    radius=8, kind="outline", bg=c["bg"],
                    font=ui_font(9)).grid(row=0, column=1)
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
                for child in w.winfo_children():
                    _bind_wheel(child)
            except Exception:
                pass

        _bind_wheel(outer)
        canvas.bind("<MouseWheel>", _wheel)

        # 固定一个足够大的尺寸，再用滚动兜底。
        try:
            sh = win.winfo_screenheight()
            sw = win.winfo_screenwidth()
        except Exception:
            sh, sw = 1080, 1920
        h = max(560, min(780, sh - 120))
        w = max(700, min(780, sw - 80))
        win.minsize(min(700, w), min(520, h))
        win.geometry(f"{w}x{h}")
        center_on_parent(win, self, w, h)
        _sync_scroll()

        win.deiconify()
        try:
            win.update_idletasks()
            enable_windows_dark_titlebar(win.winfo_id())
            enable_windows_rounded_corners(win.winfo_id())
        except Exception:
            pass
        win.grab_set()
        win.focus_force()

    def _refresh_adv_hint(self) -> None:
        if self.manager.running:
            self.lbl_adv_hint.configure(
                text="服务运行中，此处修改将在停止后重新开启才生效")
        else:
            self.lbl_adv_hint.configure(text="修改会在下次开启共享时生效")
