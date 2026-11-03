"""高级设置弹窗：内容多且可滚动，单独拆出避免主窗口继续膨胀。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.config import RENDER_MODES
from core.theme import ThemedCheckbutton, ThemedCombobox, apply_theme
from core.winpos import center_on_parent

from .common import ui_font


class AdvancedDialogMixin:
    """高级设置弹窗的构建与提示刷新。"""

    # ---------------- 高级设置 ----------------
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

        # 访问口令（dufs -a user:pass@/:rw）
        row_label("访问口令（用户名）", 7)
        e_auth_user = ttk.Entry(outer, textvariable=self.v_auth_user)
        e_auth_user.grid(row=7, column=1, sticky="ew", padx=8, pady=(10, 0))
        row_label("密码", 8)
        self.ent_auth_pass = ttk.Entry(outer, textvariable=self.v_auth_pass,
                                       show="*")
        self.ent_auth_pass.grid(row=8, column=1, sticky="ew", padx=8, pady=(4, 0))
        ttk.Label(outer,
                  text="留空表示不鉴权；非回环监听必须设置口令；口令明文保存在配置文件中",
                  style="Muted.TLabel").grid(row=9, column=1, columnspan=2,
                                             sticky="w", padx=8, pady=(2, 0))

        # 网页皮肤目录
        row_label("网页皮肤目录", 10)
        ttk.Entry(outer, textvariable=self.v_assets_dir).grid(
            row=10, column=1, sticky="ew", padx=8, pady=(10, 0))
        ttk.Button(outer, text="选择…", width=8, command=self._pick_assets).grid(
            row=10, column=2, padx=(6, 0), pady=(10, 0))
        ttk.Label(outer, text="留空用内置皮肤；也可指向第三方皮肤包（须含 index.html）",
                  style="Muted.TLabel").grid(row=11, column=1, columnspan=2,
                                             sticky="w", padx=8, pady=(2, 0))

        # dufs 程序
        row_label("dufs 程序", 12)
        e5 = ttk.Entry(outer, textvariable=self.v_dufs, state="readonly")
        e5.grid(row=12, column=1, sticky="ew", padx=8, pady=(10, 0))
        ttk.Button(outer, text="更换…", width=8, command=self._pick_dufs).grid(
            row=12, column=2, padx=(6, 0), pady=(10, 0))

        # 底部提示 + 关闭
        hint = ttk.Frame(outer)
        hint.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(18, 0))
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
        if self.runtime.running:
            self.lbl_adv_hint.configure(
                text="服务运行中，此处修改将在停止后重新开启才生效")
        else:
            self.lbl_adv_hint.configure(text="修改会在下次开启共享时生效")
