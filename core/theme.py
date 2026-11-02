"""深色 / 浅色主题。tkinter 无原生深色，这里用 ttk 的 clam 主题重绘配色。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# 已创建的 Combobox 实例，主题切换时需要逐个刷新下拉列表
_COMBOS: list[ttk.Combobox] = []


class ThemedCombobox(ttk.Combobox):
    """下拉列表配色可控的 Combobox。

    ttk.Combobox 的下拉部分是**原生 tk.Listbox，不是 ttk 控件**：
      - ttk::style 对它完全无效
      - 只能用 option database，且大小写敏感
        （selectBackground / selectForeground 的 B、F 必须大写，
         写成 selectbackground 会静默失效）
      - option_add 要在创建 widget **之前**才可靠生效，而运行中切换主题
        属于"之后"，所以额外提供 refresh_popdown() 用 tk.eval 直接改
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _COMBOS.append(self)
        # 点击后 popdown 才被创建，稍等一拍再配置
        self.bind("<ButtonPress-1>", self._schedule_refresh, add="+")

    def _schedule_refresh(self, _event=None) -> None:
        try:
            self.after(50, self.refresh_popdown)
        except Exception:
            pass

    def refresh_popdown(self, colors: dict | None = None) -> None:
        """直接给已经存在的 popdown Listbox 上色（切换主题时用）。"""
        if colors is None:
            colors = palette(_current_dark())
        try:
            opts = self._options(
                background=colors["field"],
                foreground=colors["fg"],
                selectbackground=colors["accent"],
                selectforeground=colors["accent_fg"],
                borderwidth=0,
                highlightthickness=0,
                relief="flat",
            )
            self.tk.eval(
                "[ttk::combobox::PopdownWindow %s].f.l configure %s"
                % (self, " ".join(opts))
            )
        except Exception:
            pass  # popdown 还没创建，忽略；option_add 会兜底


def _current_dark() -> bool:
    try:
        from .app_state import DARK  # 避免循环导入

        return DARK
    except Exception:
        return True


def apply_option_db(root: tk.Misc, c: dict[str, str], font) -> None:
    """设置 option database。必须在创建任何 Combobox 之前调用才可靠。"""
    for opt, val in (
        ("background", c["field"]),
        ("foreground", c["fg"]),
        ("selectBackground", c["accent"]),
        ("selectForeground", c["accent_fg"]),
        ("borderWidth", "0"),
        ("highlightThickness", "0"),
        ("relief", "flat"),
        ("font", font),
    ):
        root.option_add(f"*TCombobox*Listbox.{opt}", val)
    # 弹出框本身的边框
    root.option_add("*ComboboxPopdownFrame.borderWidth", "1")
    root.option_add("*ComboboxPopdownFrame.relief", "solid")


def refresh_all_popdowns(c: dict[str, str]) -> None:
    """主题切换后，刷新所有已存在 Combobox 的下拉列表配色。"""
    for w in list(_COMBOS):
        try:
            w.refresh_popdown(c)  # type: ignore[attr-defined]
        except Exception:
            pass

DARK = {
    "bg": "#1b1e23",
    "panel": "#23272e",
    "card": "#2a2f3a",
    "field": "#161a1f",
    "fg": "#e6e8ec",
    "muted": "#9aa4b2",
    "border": "#333a45",
    "accent": "#4f9cf9",
    "accent_fg": "#ffffff",
    "ok": "#3fb950",
    "warn": "#d9a441",
    "danger": "#e05c5c",
}

LIGHT = {
    "bg": "#f4f6f9",
    "panel": "#ffffff",
    "card": "#ffffff",
    "field": "#ffffff",
    "fg": "#1f2328",
    "muted": "#5b6572",
    "border": "#d3d9e0",
    "accent": "#2f6fdb",
    "accent_fg": "#ffffff",
    "ok": "#1f8f3d",
    "warn": "#a86a00",
    "danger": "#c92a2a",
}


def palette(dark: bool) -> dict[str, str]:
    return DARK if dark else LIGHT


def apply_theme(root: tk.Misc, dark: bool = True) -> dict[str, str]:
    """应用主题到 root 及其所有 ttk 组件，返回所用配色。"""
    c = palette(dark)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(bg=c["bg"])

    style.configure(".", background=c["panel"], foreground=c["fg"],
                    fieldbackground=c["field"], bordercolor=c["border"],
                    troughcolor=c["field"], insertcolor=c["fg"])
    style.configure("TFrame", background=c["bg"])
    style.configure("Card.TFrame", background=c["panel"], relief="flat")
    style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"])
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["accent"])
    style.configure("TLabel", background=c["bg"], foreground=c["fg"])
    style.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"])
    style.configure("Card.TLabel", background=c["panel"], foreground=c["fg"])
    style.configure("MutedCard.TLabel", background=c["panel"], foreground=c["muted"])
    style.configure("Title.TLabel", background=c["bg"], foreground=c["fg"],
                    font=("Segoe UI", 15, "bold"))
    style.configure("Status.TLabel", background=c["bg"], foreground=c["muted"],
                    font=("Segoe UI", 10))

    style.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"],
                    bordercolor=c["border"], lightcolor=c["field"],
                    darkcolor=c["field"], insertcolor=c["fg"], padding=4)
    # Combobox：输入框本体 + 下拉箭头。下拉列表本体不能用 style 配，见下方
    style.configure("TCombobox", fieldbackground=c["field"], foreground=c["fg"],
                    background=c["field"], bordercolor=c["border"], padding=4,
                    arrowcolor=c["fg"], arrowsize=14,
                    lightcolor=c["field"], darkcolor=c["field"],
                    insertcolor=c["fg"])
    style.map("TCombobox",
              fieldbackground=[("readonly", c["field"]), ("disabled", c["panel"])],
              foreground=[("readonly", c["fg"]), ("disabled", c["muted"])],
              background=[("readonly", c["field"]), ("active", c["card"])],
              arrowcolor=[("disabled", c["muted"]), ("active", c["accent"])],
              selectbackground=[("readonly", c["field"])],
              selectforeground=[("readonly", c["fg"])])
    apply_option_db(root, c, ("Microsoft YaHei UI", 10))

    # Checkbutton：clam 主题下对勾（checkmark）是**硬编码深色**的，改不了颜色。
    # 所以不能让选中态也是深色底，否则深底 + 深勾 = 完全看不见。
    # 做法：选中时把方框填成高亮的 accent 色，深色对勾落在亮底上就清晰了；
    # 未选中时方框用 field 色并靠 bordercolor 勾出轮廓。
    for name, bg in (("TCheckbutton", c["bg"]), ("Card.TCheckbutton", c["panel"])):
        style.configure(
            name,
            background=bg,
            foreground=c["fg"],
            indicatorcolor=c["field"],          # 未选中：深色框
            indicatorbackground=bg,
            bordercolor=c["border"],
            indicatordiameter=16,               # 放大，勾更易辨认
            indicatormargin=(2, 2, 6, 2),
            indicatorrelief="flat",
            padding=(2, 3),
        )
        style.map(
            name,
            background=[("active", bg), ("disabled", bg)],
            foreground=[("disabled", c["muted"]), ("active", c["fg"])],
            indicatorcolor=[
                ("selected", "disabled", c["muted"]),
                ("selected", c["accent"]),      # 选中：亮蓝底 + 深色勾
                ("!selected", "disabled", c["panel"]),
                ("!selected", "active", c["border"]),
                ("!selected", c["field"]),
            ],
        )

    style.configure("TRadiobutton", background=c["bg"], foreground=c["fg"],
                    indicatorcolor=c["field"], indicatorbackground=c["field"])
    style.map("TRadiobutton", background=[("active", c["bg"])],
              indicatorcolor=[("selected", c["accent"]), ("!selected", c["field"])])

    style.configure("TButton", background=c["card"], foreground=c["fg"],
                    bordercolor=c["border"], padding=(10, 5), focusthickness=0)
    style.map("TButton",
              background=[("active", c["border"]), ("disabled", c["panel"])],
              foreground=[("disabled", c["muted"])])
    style.configure("Accent.TButton", background=c["accent"], foreground=c["accent_fg"],
                    bordercolor=c["accent"], padding=(14, 7))
    style.map("Accent.TButton",
              background=[("active", c["accent"]), ("disabled", c["border"])])
    style.configure("Danger.TButton", background=c["danger"], foreground="#ffffff",
                    bordercolor=c["danger"], padding=(14, 7))
    style.map("Danger.TButton", background=[("active", c["danger"]),
                                            ("disabled", c["border"])])

    style.configure("TProgressbar", background=c["accent"], troughcolor=c["field"],
                    bordercolor=c["border"], thickness=14)
    style.configure("TSeparator", background=c["border"])
    style.configure("TNotebook", background=c["bg"], bordercolor=c["border"])
    style.configure("TNotebook.Tab", background=c["panel"], foreground=c["muted"],
                    padding=(12, 5))
    style.map("TNotebook.Tab", background=[("selected", c["card"])],
              foreground=[("selected", c["fg"])])
    style.configure("Treeview", background=c["field"], foreground=c["fg"],
                    fieldbackground=c["field"], bordercolor=c["border"])
    style.configure("Vertical.TScrollbar", background=c["card"],
                    troughcolor=c["field"], bordercolor=c["border"])

    # 主题切换时把已存在 Combobox 的下拉列表也一起换色
    refresh_all_popdowns(c)
    return c


def enable_windows_dark_titlebar(hwnd: int, dark: bool = True) -> None:
    """Windows 10/11：让标题栏跟随深色（失败静默忽略）。"""
    try:
        import ctypes
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(  # type: ignore[attr-defined]
            hwnd, 20 if _win11_dark_attr_supported() else 19,
            ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def _win11_dark_attr_supported() -> bool:
    try:
        import sys
        return sys.getwindowsversion().build >= 18362  # type: ignore[attr-defined]
    except Exception:
        return True
