"""自绘深色对话框。

为什么不用 ``tkinter.messagebox`` / ``simpledialog``：它们最终调用 Win32 原生
对话框，完全绕过 ttk 主题，固定深色界面里会突然弹出一个浅色窗口。
这里用 Toplevel + 同一套 DARK token 自绘，并复用 DWM 深色标题栏函数。

仍然保留原生 ``filedialog``：选择目录/文件是系统 Shell 对话框，自绘意味着
重写完整文件浏览器（网络位置、驱动器、快捷方式、权限、输入法都要自己处理），
维护成本远高于收益，而且用户在系统文件对话框里本来就有熟悉的操作习惯。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from core import qr
from core.theme import (DARK, SPACE, apply_theme, enable_windows_dark_titlebar,
                        enable_windows_rounded_corners, fonts)
from core.winpos import center_on_parent, work_area_height

from .common import text_width, ui_font
from .roundrect import RoundButton, RoundField, RoundPanel, RoundSurface


def _new_window(parent: tk.Misc, title: str) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.withdraw()
    win.title(title)
    win.transient(parent)
    win.configure(bg=DARK["bg"])
    apply_theme(win)
    return win


def _card(win: tk.Toplevel) -> ttk.Frame:
    panel = RoundPanel(win, bg=DARK["bg"], radius=10,
                       padding=(SPACE["lg"], SPACE["md"]))
    # 不 expand：卡片按内容高度收口，配合 _modal 的自适应高度，短文案不会
    # 被撑成一大块空白卡片。
    panel.pack(fill="x", padx=SPACE["lg"], pady=(SPACE["lg"], 0))
    return panel.body


def _foot(win: tk.Toplevel) -> ttk.Frame:
    foot = ttk.Frame(win, style="TFrame", padding=(SPACE["lg"], SPACE["md"]))
    foot.pack(fill="x", side="bottom")
    return foot


def _finish(win: tk.Toplevel, result) -> None:
    win._result = result
    try:
        win.grab_release()
    except Exception:
        pass
    win.destroy()


def _modal(win: tk.Toplevel, width: int, height: int | None = None) -> None:
    """居中显示、深色标题栏、模态等待；测试桩没有 wait_window 时直接返回。

    height 为 None 时按内容自适应，避免多行错误提示被固定高度裁掉。
    """
    parent = win.master
    try:
        # 先在屏幕外完成一次布局再量高：withdraw 状态下收不到 <Configure>，
        # 自适应卡片不会收口，量出来的高度会停在 Canvas 默认值。
        win.geometry(f"{width}x{height or 320}+-10000+-10000")
        win.deiconify()
        win.update()          # 真正完成映射并触发 <Configure>
        win.update_idletasks()
        if height is None:
            height = max(win.winfo_reqheight(), 120)
        center_on_parent(win, parent, width, height)
    except Exception:
        win.geometry(f"{width}x{height or 200}")
    try:
        win.update_idletasks()
        enable_windows_dark_titlebar(win.winfo_id())
        enable_windows_rounded_corners(win.winfo_id())
    except Exception:
        pass
    try:
        win.grab_set()
        win.focus_force()
    except Exception:
        pass
    wait = getattr(win, "wait_window", None)
    if callable(wait):
        wait()


def _message_label(body: ttk.Frame, text: str, fg: str | None = None) -> tk.Message:
    msg = tk.Message(body, text=text, width=420, justify="left", anchor="w",
                     bg=DARK["panel"], fg=fg or DARK["fg"], font=fonts()["body"],
                     padx=0, pady=0)
    msg.pack(fill="x", anchor="w")
    return msg


# ---------------- 文本输入 ----------------
def ask_string(parent: tk.Misc, title: str, prompt: str,
               initial: str = "", max_len: int = 80) -> str | None:
    """深色文本输入框；取消返回 None。"""
    win = _new_window(parent, title)
    body = _card(win)
    ttk.Label(body, text=prompt, style="Card.TLabel").pack(anchor="w")
    var = tk.StringVar(value=initial or "")
    entry = RoundField(body, textvariable=var, width=1, height=32)
    entry.pack(fill="x", pady=(SPACE["sm"], SPACE["xs"]))
    hint = ttk.Label(body, text="", style="MutedCard.TLabel", font=fonts()["caption"])
    hint.pack(anchor="w")

    def submit(_event=None) -> str:
        value = var.get().strip()
        if not value:
            hint.configure(text="名称不能为空", foreground=DARK["danger"])
            return "break"
        if len(value) > max_len:
            hint.configure(text=f"名称最长 {max_len} 个字符", foreground=DARK["danger"])
            return "break"
        _finish(win, value)
        return "break"

    foot = _foot(win)
    RoundButton(foot, "取消", command=lambda: _finish(win, None), width=64,
                height=28, radius=8, kind="outline", bg=DARK["bg"],
                font=ui_font(9)).pack(side="right")
    RoundButton(foot, "确定", command=submit, width=64, height=28, radius=8,
                kind="accent", bg=DARK["bg"],
                font=ui_font(9, "bold")).pack(side="right", padx=(0, SPACE["sm"]))

    entry.bind("<Return>", submit)
    win.bind("<Return>", submit)
    win.bind("<Escape>", lambda e: _finish(win, None))
    try:
        entry.focus_set()
        entry.selection_range(0, "end")
        entry.icursor("end")
    except Exception:
        pass
    _modal(win, 420)
    return getattr(win, "_result", None)


# ---------------- 确认 / 提示 ----------------
def _key_results(default_ok: bool) -> dict[str, bool]:
    """确认框按键语义：Esc 永远取消；Enter 默认取 default_ok（危险操作传 False）。"""
    return {"<Escape>": False, "<Return>": bool(default_ok)}


def ask_yes_no(parent: tk.Misc, title: str, message: str,
               ok_text: str = "确定", destructive: bool = False,
               default_ok: bool = True) -> bool:
    win = _new_window(parent, title)
    body = _card(win)
    _message_label(body, message)
    win._result = False

    foot = _foot(win)
    RoundButton(foot, "取消", command=lambda: _finish(win, False), width=64,
                height=28, radius=8, kind="outline", bg=DARK["bg"],
                font=ui_font(9)).pack(side="right")
    RoundButton(foot, ok_text, command=lambda: _finish(win, True), width=64,
                height=28, radius=8,
                kind="danger" if destructive else "accent", bg=DARK["bg"],
                font=ui_font(9, "bold")).pack(side="right", padx=(0, SPACE["sm"]))
    for seq, result in _key_results(default_ok).items():
        win.bind(seq, lambda e, r=result: _finish(win, r))
    _modal(win, 460)
    return bool(getattr(win, "_result", False))


def show_message(parent: tk.Misc, title: str, message: str,
                 kind: str = "info") -> None:
    """深色提示框（info / warning / error）。"""
    win = _new_window(parent, title)
    body = _card(win)
    color = {"info": DARK["accent"], "warning": DARK["warn"],
             "error": DARK["danger"]}.get(kind, DARK["accent"])
    head = ttk.Frame(body, style="Card.TFrame")
    head.pack(fill="x", pady=(0, SPACE["sm"]))
    tk.Label(head, text="●", bg=DARK["panel"], fg=color,
             font=fonts()["section"]).pack(side="left", padx=(0, SPACE["sm"]))
    ttk.Label(head, text={"info": "提示", "warning": "注意",
                          "error": "出错了"}.get(kind, "提示"),
              style="CardTitle.TLabel").pack(side="left")
    _message_label(body, message)

    foot = _foot(win)
    RoundButton(foot, "确定", command=lambda: _finish(win, True), width=64,
                height=28, radius=8, kind="accent", bg=DARK["bg"],
                font=ui_font(9, "bold")).pack(side="right")
    win.bind("<Escape>", lambda e: _finish(win, True))
    win.bind("<Return>", lambda e: _finish(win, True))
    _modal(win, 480)


def show_info(parent: tk.Misc, title: str, message: str) -> None:
    show_message(parent, title, message, "info")


def show_warning(parent: tk.Misc, title: str, message: str) -> None:
    show_message(parent, title, message, "warning")


def show_error(parent: tk.Misc, title: str, message: str) -> None:
    show_message(parent, title, message, "error")


# ---------------- 二维码 ----------------
def _draw_matrix(canvas: tk.Canvas, matrix: list[list[bool]], scale: int,
                 border: int = 4) -> int:
    n = len(matrix)
    side = (n + border * 2) * scale
    try:
        canvas.delete("all")
    except Exception:
        pass
    canvas.configure(width=side, height=side)
    canvas.create_rectangle(0, 0, side, side, fill="#ffffff", outline="")
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if not dark:
                continue
            x0 = (x + border) * scale
            y0 = (y + border) * scale
            canvas.create_rectangle(x0, y0, x0 + scale, y0 + scale,
                                    fill="#000000", outline="")
    return side


def _qr_render(url: str) -> tuple[list[list[bool]], int, int]:
    """(矩阵, 像素缩放, 边长)；同一地址只算一次，切换时直接复用。"""
    matrix = qr.encode(url)
    n = len(matrix)
    scale = max(4, min(8, 320 // (n + 8)))
    return matrix, scale, (n + 8) * scale


def build_qr_window(parent: tk.Misc, url: str,
                    title: str = "共享二维码",
                    urls: list[str] | None = None) -> tk.Toplevel:
    """构建二维码窗口（不进入模态循环，便于测试）。

    urls 为全部可访问地址（首项为主推地址）；多于一个时顶部出现地址选择器，
    只有一个地址时不渲染选择器，避免单选项的冗余。
    """
    choices: list[str] = []
    for candidate in [url] + list(urls or []):
        value = (candidate or "").strip()
        if value and value not in choices:
            choices.append(value)
    if not choices:
        choices = [url]

    # 预生成所有地址的矩阵：切换只是重绘，不会卡在编码上；窗口按最大尺寸固定，
    # 避免切换时窗口跳动。
    primary = choices[0]
    cache = {choice: _qr_render(choice) for choice in choices}
    max_side = max(entry[2] for entry in cache.values())
    width = max(360, max_side + 2 * SPACE["lg"] + SPACE["lg"])
    has_selector = len(choices) > 1

    win = _new_window(parent, title)
    win.qr_payload = primary       # 测试断言：二维码内容必须与链接一致
    win.qr_matrix = cache[primary][0]
    win.qr_choices = choices
    win.qr_cache = cache
    win.qr_selector = None
    body = _card(win)

    var = tk.StringVar(value=primary)
    win.qr_var = var
    if has_selector:
        # 弹窗顶部：网址选择器（切换后立即重绘，链接与保存内容同步）
        ttk.Label(body, text="访问地址", style="MutedCard.TLabel").pack(anchor="w")
        selector = ttk.Combobox(body, textvariable=var, values=choices,
                                state="readonly")
        selector.pack(fill="x", pady=(SPACE["xs"], SPACE["sm"]))
        win.qr_selector = selector

    ttk.Label(body, text="扫码在手机上打开共享目录",
              style="CardTitle.TLabel").pack(anchor="w", pady=(0, SPACE["sm"]))

    qr_surface = RoundSurface(body, fill="#ffffff", radius=8,
                              bg=DARK["panel"], border=None,
                              width=max_side + 8, autoheight=True)
    qr_surface.pack()
    canvas = tk.Canvas(qr_surface.body, bg="#ffffff", highlightthickness=0,
                       bd=0, width=max_side, height=max_side)
    canvas.pack()
    _draw_matrix(canvas, cache[primary][0], cache[primary][1])
    win.qr_canvas = canvas

    link = RoundField(body, width=1, height=32)
    link.insert(0, primary)
    link.configure(state="readonly")
    link.pack(fill="x", pady=(SPACE["sm"], SPACE["xs"]))
    hint = ("手机需与电脑在同一网段；切换地址可换二维码" if has_selector
            else "手机需与电脑在同一网段")
    ttk.Label(body, text=hint,
              style="MutedCard.TLabel", font=fonts()["caption"]).pack(anchor="w")
    win.qr_link = link

    def select_url(_event=None) -> None:
        target = str(var.get() or "")
        if target not in cache:
            return
        matrix, scale, _side = cache[target]
        win.qr_payload = target
        win.qr_matrix = matrix
        _draw_matrix(canvas, matrix, scale)
        try:
            link.configure(state="normal")
            link.delete(0, "end")
            link.insert(0, target)
            link.configure(state="readonly")
        except Exception:
            pass

    win.qr_select = select_url
    if has_selector:
        win.qr_selector.bind("<<ComboboxSelected>>", select_url)

    def copy_link() -> None:
        try:
            win.clipboard_clear()
            win.clipboard_append(win.qr_payload)
        except Exception:
            pass

    def save_png() -> None:
        path = filedialog.asksaveasfilename(
            parent=win, title="保存二维码", defaultextension=".png",
            initialfile="dufs-qr.png", filetypes=[("PNG 图片", "*.png")])
        if not path:
            return
        try:
            Path(path).write_bytes(qr.png_bytes(win.qr_matrix, scale=8))
        except OSError as e:
            show_error(win, "保存失败", f"{e}\n路径：{path}")
            return
        show_info(win, "已保存", f"二维码已保存到：\n{path}")

    foot = _foot(win)
    RoundButton(foot, "关闭", command=lambda: _finish(win, None), width=64,
                height=28, radius=8, kind="outline", bg=DARK["bg"],
                font=ui_font(9)).pack(side="right")
    RoundButton(foot, "保存 PNG…", command=save_png, width=88, height=28,
                radius=8, kind="outline", bg=DARK["bg"],
                font=ui_font(9)).pack(side="right", padx=(0, SPACE["sm"]))
    RoundButton(foot, "复制链接", command=copy_link, width=80, height=28,
                radius=8, kind="outline", bg=DARK["bg"],
                font=ui_font(9)).pack(side="right", padx=(0, SPACE["sm"]))
    win.bind("<Escape>", lambda e: _finish(win, None))
    # 240 为标题/地址行/说明/按钮行与内边距；底部按钮留 12px 下边距，避免被裁切
    win._qr_size = (width, max_side + 240 + (52 if has_selector else 0))
    return win


def show_qr(parent: tk.Misc, url: str, urls: list[str] | None = None) -> None:
    win = build_qr_window(parent, url, urls=urls)
    width, height = win._qr_size
    _modal(win, width, height)


# ---------------- 网卡勾选 ----------------
#: 弹窗固定 chrome（标题/说明/原因/按钮行/内外边距），行高与列表一致
BIND_CHROME_H = 196
BIND_ROW_H = 32
BIND_MAX_ROWS = 20
BIND_MIN_W = 400
BIND_MAX_W = 720


class _RowTip:
    """行内文本超长时的悬停提示（深色，跟随光标）。"""

    def __init__(self, win: tk.Toplevel):
        self.win = win
        self.tip: tk.Toplevel | None = None

    def show(self, text: str, x_root: int, y_root: int) -> None:
        self.hide()
        try:
            tip = tk.Toplevel(self.win)
            tip.overrideredirect(True)
            tip.configure(bg=DARK["border"])
            tk.Label(tip, text=text, bg=DARK["card"], fg=DARK["fg"],
                     font=fonts()["caption"], padx=8, pady=4).pack(padx=1, pady=1)
            tip.geometry(f"+{x_root + 12}+{y_root + 16}")
            self.tip = tip
        except Exception:
            self.tip = None

    def hide(self) -> None:
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


def build_bind_window(parent: tk.Misc, items: list,
                      selected=(), title: str = "选择共享网卡") -> tk.Toplevel:
    """网卡多选弹窗（不进入模态循环，便于测试）。

    IP 是主信息，网卡名只作弱化副文本。确定 = 保存并生效；标题栏 × 与 Esc
    都是取消（丢弃未确认的勾选）。全不选时「确定」置灰并显示原因。
    """
    from .bindlist import COMPACT_ROW_HEIGHT, BindCheckList

    # 只列真正有地址的网卡：断开的/纯占位适配器（地址为空）直接过滤掉
    items = [it for it in items if (it.address or "").strip()]
    empty = not items
    win = _new_window(parent, title)
    win._binds_done = False
    body = _card(win)
    ttk.Label(body, text="选择要共享的网卡", style="CardTitle.TLabel").pack(anchor="w")
    hint = ttk.Label(body, text="可多选；勾选后点「确定」生效",
                     style="MutedCard.TLabel", font=fonts()["caption"])
    hint.pack(anchor="w", pady=(SPACE["xs"], SPACE["sm"]))

    # 高度按数量自适应：全部一次可见；只有 >20 行（或小屏放不下）才滚动
    screen_h = work_area_height(win)
    max_rows_fit = max(1, (screen_h - 80 - BIND_CHROME_H) // BIND_ROW_H)
    rows_visible = max(1, min(len(items), BIND_MAX_ROWS, max_rows_fit))
    scroll = len(items) > rows_visible

    # 宽度按最长一行内容自适应，封顶后超长文本省略 + tooltip
    f = fonts()
    content_w = 0
    for item in items:
        content_w = max(content_w, text_width(item.address, f["mono"]) + 12
                        + text_width(item.name or "", f["caption"]))
    cols = 120 + (14 if scroll else 0)     # 边距 + 勾选框 + IP 起点 + 行内间距
    width = min(BIND_MAX_W, max(BIND_MIN_W, content_w + cols))
    listing = BindCheckList(body, compact=True, visible_rows=rows_visible,
                            text_budget=width - cols)
    if empty:
        rows_visible = 0
        scroll = False
        hint.configure(text="未检测到可用网络地址")
    else:
        listing.pack(fill="both", expand=True)
        listing.canvas.configure(height=COMPACT_ROW_HEIGHT * rows_visible)

    reason = ttk.Label(body, text="", style="MutedCard.TLabel",
                       font=fonts()["caption"])
    reason.pack(anchor="w", pady=(SPACE["xs"], 0))

    def confirm(_event=None):
        chosen = listing.selected()
        if not chosen or win._binds_done:
            return "break"
        win._binds_done = True
        _finish(win, chosen)
        return "break"

    def cancel(_event=None):
        if win._binds_done:
            return "break"
        win._binds_done = True
        _finish(win, None)
        return "break"

    foot = _foot(win)
    RoundButton(foot, "取消", command=cancel, width=64, height=28, radius=8,
                kind="outline", bg=DARK["bg"],
                font=ui_font(9)).pack(side="right")
    ok_btn = RoundButton(foot, "确定", command=confirm, width=64, height=28,
                         radius=8, kind="accent", bg=DARK["bg"],
                         font=ui_font(9, "bold"), state="disabled")
    ok_btn.pack(side="right", padx=(0, SPACE["sm"]))

    def sync_ok(_count=0):
        chosen = listing.selected()
        ok_btn.set_state("normal" if chosen else "disabled")
        if empty:
            reason.configure(text="", foreground=DARK["muted"])
        else:
            reason.configure(
                text="" if chosen else "至少选择一个",
                foreground=DARK["danger"] if not chosen else DARK["muted"])

    listing._on_change = sync_ok
    listing.set_items(items, selected)
    sync_ok()
    # 行文本被省略时，悬停显示完整值（数量少/宽度够时不会触发）
    tip = _RowTip(win)
    for row in listing._rows:
        full = row.get("full_text")
        if not full:
            continue
        row["row"].bind(
            "<Enter>",
            lambda e, t=full: tip.show(t, e.x_root, e.y_root), add="+")
        row["row"].bind("<Leave>", lambda e: tip.hide(), add="+")

    win.bind("<Escape>", cancel)
    win.protocol("WM_DELETE_WINDOW", cancel)
    win.binds_list = listing
    win.binds_ok_button = ok_btn
    win.binds_reason = reason
    win.binds_confirm = confirm
    win.binds_cancel = cancel
    win.binds_esc = cancel
    win._binds_size = (width, rows_visible * COMPACT_ROW_HEIGHT + BIND_CHROME_H)
    win._binds_rows = rows_visible
    win._binds_scroll = scroll
    win._binds_empty = empty
    return win


def select_binds(parent: tk.Misc, items: list, selected=()) -> list[str] | None:
    """模态网卡勾选：确定返回勾选地址，取消/×/Esc 返回 None。"""
    win = build_bind_window(parent, items, selected)
    width, height = win._binds_size
    _modal(win, width, height)
    return getattr(win, "_result", None)
