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
from core.winpos import center_on_parent

from .common import ui_font
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


def build_qr_window(parent: tk.Misc, url: str,
                    title: str = "共享二维码") -> tk.Toplevel:
    """构建二维码窗口（不进入模态循环，便于测试）。"""
    matrix = qr.encode(url)
    n = len(matrix)
    scale = max(4, min(8, 320 // (n + 8)))
    side = (n + 8) * scale
    width = max(360, side + 2 * SPACE["lg"] + SPACE["lg"])

    win = _new_window(parent, title)
    win.qr_payload = url            # 测试断言：二维码内容必须与链接一致
    win.qr_matrix = matrix
    body = _card(win)
    ttk.Label(body, text="扫码在手机上打开共享目录",
              style="CardTitle.TLabel").pack(anchor="w", pady=(0, SPACE["sm"]))

    qr_surface = RoundSurface(body, fill="#ffffff", radius=8,
                              bg=DARK["panel"], border=None,
                              width=side + 8, autoheight=True)
    qr_surface.pack()
    canvas = tk.Canvas(qr_surface.body, bg="#ffffff", highlightthickness=0,
                       bd=0, width=side, height=side)
    canvas.pack()
    _draw_matrix(canvas, matrix, scale)
    win.qr_canvas = canvas

    link = RoundField(body, width=1, height=32)
    link.insert(0, url)
    link.configure(state="readonly")
    link.pack(fill="x", pady=(SPACE["sm"], SPACE["xs"]))
    ttk.Label(body, text="手机需与电脑在同一网段；地址以当前共享链接为准",
              style="MutedCard.TLabel", font=fonts()["caption"]).pack(anchor="w")
    win.qr_link = link

    def copy_link() -> None:
        try:
            win.clipboard_clear()
            win.clipboard_append(url)
        except Exception:
            pass

    def save_png() -> None:
        path = filedialog.asksaveasfilename(
            parent=win, title="保存二维码", defaultextension=".png",
            initialfile="dufs-qr.png", filetypes=[("PNG 图片", "*.png")])
        if not path:
            return
        try:
            Path(path).write_bytes(qr.png_bytes(matrix, scale=8))
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
    win._qr_size = (width, side + 220)
    return win


def show_qr(parent: tk.Misc, url: str) -> None:
    win = build_qr_window(parent, url)
    width, height = win._qr_size
    _modal(win, width, height)
