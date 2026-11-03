"""固定深色主题。tkinter 无原生深色，这里用 ttk 的 clam 主题重绘配色。

应用不提供浅色模式，也不保存主题状态：所有窗口、弹窗、下拉列表与滚动条
都只使用 DARK 一套配色。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# 已创建的 Combobox 实例，创建/刷新时需要逐个配置下拉列表
_COMBOS: list[ttk.Combobox] = []

# ---------- 复选框：自绘指示器 ----------
# 为什么不用 indicatorcolor：clam 的对勾是硬编码深色，而 indicatorcolor 在部分
# 平台/版本上根本不生效（静默失效，不报错）。靠配色去"猜"不可靠。
# 这里改为自绘 16x16 位图 + element_create 替换 Checkbutton.indicator，
# 颜色完全由我们决定 —— 任何主题、任何平台下都必然可见。
_ELEMENT_SEQ = [0]
_IMAGE_REFS: list = []

#: 16x16 方框内的对勾像素；再画一行 y+1 让笔画粗一点
_TICK = ((4, 7), (5, 8), (6, 9), (7, 10), (8, 9), (9, 8), (10, 7), (11, 6), (12, 5))


def _make_box_image(fill: str, border: str, tick: str | None) -> "tk.PhotoImage":
    """画一个 16x16 的方框（可选带对勾）。整块不透明，避免透明像素的坑。"""
    img = tk.PhotoImage(width=16, height=16)
    img.put(border, (0, 0, 15, 0))
    img.put(border, (0, 15, 15, 15))
    img.put(border, (0, 1, 0, 14))
    img.put(border, (15, 1, 15, 14))
    img.put(fill, (1, 1, 14, 14))
    if tick:
        for x, y in _TICK:
            img.put(tick, (x, y))
            img.put(tick, (x, y + 1))
    return img


def _install_check_indicator(style: "ttk.Style", c: dict) -> None:
    """用自绘位图替换复选框指示器。每次调用换一个新元素名，便于切换主题。"""
    _ELEMENT_SEQ[0] += 1
    name = f"Chk{_ELEMENT_SEQ[0]}.indicator"
    un = _make_box_image(c["field"], c["border"], None)
    ch = _make_box_image(c["accent"], c["accent"], c["accent_fg"])
    und = _make_box_image(c["panel"], c["border"], None)
    chd = _make_box_image(c["border"], c["border"], c["muted"])
    # 必须长期持有引用，否则被 GC 回收后图片会变空白
    _IMAGE_REFS.extend([un, ch, und, chd])
    style.element_create(name, "image", un,
                         ("selected", ch),
                         ("disabled", "selected", chd),
                         ("disabled", und))
    layout = [("Checkbutton.padding", {"sticky": "nswe", "children": [
        (name, {"side": "left", "sticky": ""}),
        ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
            ("Checkbutton.label", {"sticky": "nswe"})]})]})]
    for s in ("TCheckbutton", "Card.TCheckbutton"):
        style.layout(s, layout)


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
        """直接给已经存在的 popdown Listbox 上色。"""
        if colors is None:
            colors = DARK
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


class ThemedCheckbutton(tk.Checkbutton):
    """复选框：**不用 ttk**。

    为什么不用 ttk.Checkbutton：
      - `indicatorcolor` 在部分平台**静默失效**（不报错，就是没效果）
      - `element_create` + `layout` 替换指示器在主题切换时不稳定，且失败时无声
    改用具经多方验证的做法（Stack Overflow #58559865 已采纳答案 / w3resource 教程 /
    pc-app-development 官方文档）：**tk.Checkbutton + indicatoron=False +
    image/selectimage 自绘图片**。完全绕开 ttk 主题机制，深浅色下都必然可见。
    """

    _INSTANCES: list["ThemedCheckbutton"] = []

    def __init__(self, master=None, bg_key: str = "bg", **kw):
        super().__init__(master, **kw)
        self._bg_key = bg_key
        self._imgs: list = []
        ThemedCheckbutton._INSTANCES.append(self)
        self.configure(
            indicatoron=False,      # 关掉系统指示器，改用我们自己的图片
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            padx=2, pady=2,
            compound="left",        # 图在左、文字在右
            anchor="w",
        )
        self.apply_colors(DARK)

    def apply_colors(self, c: dict) -> None:
        bg = c.get(self._bg_key, c["bg"])
        un = _make_box_image(c["field"], c["check_border"], None)
        ch = _make_box_image(c["check_on"], c["check_on"], c["accent_fg"])
        self._imgs = [un, ch]       # 必须长期持有，否则被 GC 后图片变空白
        self.configure(
            image=un,
            selectimage=ch,
            bg=bg,
            fg=c["fg"],
            activebackground=bg,
            activeforeground=c["fg"],
            selectcolor=bg,
        )

    def destroy(self):
        try:
            ThemedCheckbutton._INSTANCES.remove(self)
        except ValueError:
            pass
        super().destroy()


def refresh_all_checkbuttons(c: dict) -> None:
    """刷新所有复选框图片与配色。"""
    for w in list(ThemedCheckbutton._INSTANCES):
        try:
            w.apply_colors(c)
        except Exception:
            pass


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

#: Apple macOS 深色设计 token（在 ttk 可表达范围内的近似）
#: - 层次用背景色差：#1e1e1e 底 / #232325 面板 / #2c2c2e 控件
#: - 强调色是深色模式系统蓝 #0a84ff；危险操作 #ff453a
#: - 次要文字 #8e8e93；分隔线/边框 #3a3a3c（低对比，不抢层次）
DARK = {
    "bg": "#1e1e1e",
    "panel": "#232325",
    "card": "#2c2c2e",
    "field": "#2c2c2e",
    "well": "#1a1a1c",
    "fg": "#f2f2f7",
    "muted": "#8e8e93",
    "border": "#3a3a3c",
    "sel": "#3a3a3c",
    "accent": "#0a84ff",
    "accent_hover": "#0077ed",
    "accent_press": "#0060df",
    "accent_fg": "#ffffff",
    # 选中态方框填充：白勾与 #0a84ff 对比度 > 3:1
    "check_on": "#0a84ff",
    # 未选中方框描边：与面板 #232325 对比度 > 5:1
    "check_border": "#8e8e93",
    "ok": "#30d158",
    "warn": "#ffd60a",
    "danger": "#ff453a",
    "danger_hover": "#ff6961",
}

#: 8pt 栅格（Tk 以像素计，8 的倍数为统一间距）
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}

#: ttk/clam 没有真正的圆角；这里只作为画布类自绘的预留 token 与文档口径
RADIUS = {"card": 12, "control": 8}

_FAMILY = "Microsoft YaHei UI"


def fonts() -> dict[tuple]:
    return {
        "title": (_FAMILY, 20, "bold"),
        "section": (_FAMILY, 11, "bold"),
        "body": (_FAMILY, 10),
        "caption": (_FAMILY, 9),
        "mono": ("Consolas", 10),
    }


def apply_theme(root: tk.Misc) -> dict[str, str]:
    """把固定深色主题应用到 root 及其所有 ttk 组件，返回 DARK。"""
    c = DARK
    f = fonts()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(bg=c["bg"])

    style.configure(".", background=c["panel"], foreground=c["fg"],
                    fieldbackground=c["field"], bordercolor=c["border"],
                    troughcolor=c["well"], insertcolor=c["fg"],
                    font=f["body"])
    style.configure("TFrame", background=c["bg"])
    style.configure("Card.TFrame", background=c["panel"], relief="flat")
    style.configure("Well.TFrame", background=c["well"], relief="flat")
    style.configure("TLabelframe", background=c["panel"], bordercolor=c["border"])
    style.configure("TLabelframe.Label", background=c["panel"], foreground=c["fg"],
                    font=f["section"])
    style.configure("TLabel", background=c["bg"], foreground=c["fg"])
    style.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"])
    style.configure("Card.TLabel", background=c["panel"], foreground=c["fg"])
    style.configure("MutedCard.TLabel", background=c["panel"], foreground=c["muted"])
    style.configure("Title.TLabel", background=c["bg"], foreground=c["fg"],
                    font=f["title"])
    style.configure("Subtitle.TLabel", background=c["bg"], foreground=c["muted"],
                    font=f["body"])
    style.configure("Section.TLabel", background=c["panel"], foreground=c["fg"],
                    font=f["section"])
    style.configure("CardTitle.TLabel", background=c["panel"], foreground=c["fg"],
                    font=f["section"])
    style.configure("Status.TLabel", background=c["panel"], foreground=c["muted"],
                    font=f["caption"])

    style.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"],
                    bordercolor=c["border"], lightcolor=c["field"],
                    darkcolor=c["field"], insertcolor=c["fg"], padding=(10, 6),
                    relief="flat")
    style.map("TEntry",
              bordercolor=[("focus", c["accent"])],
              lightcolor=[("focus", c["accent"])],
              darkcolor=[("focus", c["accent"])])
    # Combobox：输入框本体 + 下拉箭头。下拉列表本体不能用 style 配，见下方
    style.configure("TCombobox", fieldbackground=c["field"], foreground=c["fg"],
                    background=c["field"], bordercolor=c["border"], padding=(10, 6),
                    arrowcolor=c["muted"], arrowsize=12,
                    lightcolor=c["field"], darkcolor=c["field"],
                    insertcolor=c["fg"])
    style.map("TCombobox",
              fieldbackground=[("readonly", c["field"]), ("disabled", c["panel"])],
              foreground=[("readonly", c["fg"]), ("disabled", c["muted"])],
              background=[("readonly", c["field"]), ("active", c["sel"])],
              arrowcolor=[("disabled", c["muted"]), ("active", c["fg"])],
              selectbackground=[("readonly", c["field"])],
              selectforeground=[("readonly", c["fg"])],
              bordercolor=[("focus", c["accent"])])
    apply_option_db(root, c, f["body"])

    # Checkbutton 已改用 tk.Checkbutton（ThemedCheckbutton），不经过 ttk。
    for name, bg in (("TCheckbutton", c["bg"]), ("Card.TCheckbutton", c["panel"])):
        style.configure(name, background=bg, foreground=c["fg"], padding=(2, 4))
        style.map(name,
                  background=[("active", bg), ("disabled", bg)],
                  foreground=[("disabled", c["muted"]), ("active", c["fg"])])

    style.configure("TRadiobutton", background=c["panel"], foreground=c["fg"],
                    indicatorcolor=c["field"], indicatorbackground=c["field"])
    style.map("TRadiobutton", background=[("active", c["panel"])],
              indicatorcolor=[("selected", c["accent"]), ("!selected", c["field"])])

    # 次按钮：描边式；主按钮：实心系统蓝；危险：实心红
    style.configure("TButton", background=c["card"], foreground=c["fg"],
                    bordercolor=c["border"], lightcolor=c["card"],
                    darkcolor=c["card"], padding=(12, 6), focusthickness=0,
                    relief="flat", font=f["body"])
    style.map("TButton",
              background=[("active", c["sel"]), ("pressed", c["border"]),
                          ("disabled", c["panel"])],
              foreground=[("disabled", c["muted"])],
              bordercolor=[("active", c["border"]), ("disabled", c["border"])])
    style.configure("Ghost.TButton", background=c["panel"], foreground=c["muted"],
                    bordercolor=c["border"], lightcolor=c["panel"],
                    darkcolor=c["panel"], padding=(10, 5))
    style.map("Ghost.TButton",
              background=[("active", c["sel"])],
              foreground=[("active", c["fg"])])
    style.configure("Accent.TButton", background=c["accent"], foreground=c["accent_fg"],
                    bordercolor=c["accent"], lightcolor=c["accent"],
                    darkcolor=c["accent"], padding=(14, 6))
    style.map("Accent.TButton",
              background=[("active", c["accent_hover"]),
                          ("pressed", c["accent_press"]),
                          ("disabled", c["border"])],
              bordercolor=[("active", c["accent_hover"]),
                           ("pressed", c["accent_press"]),
                           ("disabled", c["border"])])
    style.configure("Danger.TButton", background=c["danger"], foreground="#ffffff",
                    bordercolor=c["danger"], lightcolor=c["danger"],
                    darkcolor=c["danger"], padding=(14, 6))
    style.map("Danger.TButton",
              background=[("active", c["danger_hover"]),
                          ("pressed", c["danger"]),
                          ("disabled", c["border"])],
              bordercolor=[("active", c["danger_hover"]),
                           ("disabled", c["border"])])

    style.configure("TProgressbar", background=c["accent"], troughcolor=c["well"],
                    bordercolor=c["border"], lightcolor=c["accent"],
                    darkcolor=c["accent"], thickness=10)
    style.configure("TSeparator", background=c["border"])
    style.configure("TNotebook", background=c["bg"], bordercolor=c["border"])
    style.configure("TNotebook.Tab", background=c["panel"], foreground=c["muted"],
                    padding=(12, 5))
    style.map("TNotebook.Tab", background=[("selected", c["card"])],
              foreground=[("selected", c["fg"])])
    style.configure("Treeview", background=c["panel"], foreground=c["fg"],
                    fieldbackground=c["panel"], bordercolor=c["border"],
                    lightcolor=c["panel"], darkcolor=c["panel"], rowheight=26)
    style.map("Treeview",
              background=[("selected", c["accent"])],
              foreground=[("selected", c["accent_fg"])])
    style.configure("Treeview.Heading", background=c["panel"], foreground=c["muted"],
                    bordercolor=c["border"], font=f["caption"])
    style.map("Treeview.Heading", background=[("active", c["sel"])])

    # 滚动条：垂直/水平、普通/按下/禁用都要显式配色，否则 clam 会露出浅色 trough。
    # 深色（macOS 风格）：细 thumb、无箭头、槽与控件底色同阶。
    for orient in ("Vertical", "Horizontal"):
        name = f"{orient}.TScrollbar"
        style.configure(name,
                        background=c["card"], troughcolor=c["well"],
                        bordercolor=c["well"], arrowcolor=c["muted"],
                        lightcolor=c["card"], darkcolor=c["card"],
                        gripcount=0, arrowsize=12, width=12)
        style.map(name,
                  background=[("active", c["muted"]), ("pressed", c["fg"]),
                              ("disabled", c["well"])],
                  arrowcolor=[("active", c["fg"]), ("pressed", c["fg"]),
                              ("disabled", c["border"])],
                  bordercolor=[("disabled", c["well"])])
    # 未指定 style 时 ttk.Scrollbar 会落到 TScrollbar，补一份兜底
    style.configure("TScrollbar", background=c["card"], troughcolor=c["well"],
                    bordercolor=c["well"], arrowcolor=c["muted"],
                    lightcolor=c["card"], darkcolor=c["card"])

    style.configure("TSpinbox", fieldbackground=c["field"], foreground=c["fg"],
                    background=c["card"], bordercolor=c["border"],
                    arrowcolor=c["muted"], insertcolor=c["fg"],
                    lightcolor=c["field"], darkcolor=c["field"], padding=(10, 6))
    style.map("TSpinbox",
              fieldbackground=[("disabled", c["panel"])],
              foreground=[("disabled", c["muted"])],
              arrowcolor=[("disabled", c["muted"])])
    style.configure("TScale", background=c["panel"], troughcolor=c["well"],
                    bordercolor=c["border"], lightcolor=c["accent"],
                    darkcolor=c["accent"])

    # 任何独立 Listbox（例如下拉弹窗）也走深色，不依赖 option database 是否生效
    root.option_add("*Listbox.background", c["field"])
    root.option_add("*Listbox.foreground", c["fg"])
    root.option_add("*Listbox.selectBackground", c["accent"])
    root.option_add("*Listbox.selectForeground", c["accent_fg"])
    root.option_add("*Listbox.highlightBackground", c["border"])
    root.option_add("*Listbox.highlightColor", c["border"])
    root.option_add("*Listbox.borderWidth", 0)

    # 已存在的 Combobox 下拉列表、复选框统一换色（固定深色，仅初始化时调用）
    refresh_all_popdowns(c)
    refresh_all_checkbuttons(c)
    return c


def enable_windows_dark_titlebar(hwnd: int) -> None:
    """Windows 10/11：让标题栏跟随深色（失败静默忽略）。"""
    try:
        import ctypes
        value = ctypes.c_int(1)
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
