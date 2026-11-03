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
                        fonts)
from core.winpos import center_on_parent


def _new_window(parent: tk.Misc, title: str) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.withdraw()
    win.title(title)
    win.transient(parent)
    win.configure(bg=DARK["bg"])
    apply_theme(win)
    return win


def _card(win: tk.Toplevel) -> ttk.Frame:
    holder = tk.Frame(win, bg=DARK["panel"], highlightbackground=DARK["border"],
                      highlightthickness=1, bd=0)
    holder.pack(fill="both", expand=True, padx=SPACE["lg"], pady=(SPACE["lg"], 0))
    body = ttk.Frame(holder, style="Card.TFrame", padding=(SPACE["lg"], SPACE["md"]))
    body.pack(fill="both", expand=True)
    return body


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
        win.update_idletasks()
        if height is None:
            height = max(win.winfo_reqheight(), 120)
        center_on_parent(win, parent, width, height)
    except Exception:
        win.geometry(f"{width}x{height or 200}")
    win.deiconify()
    try:
        win.update_idletasks()
        enable_windows_dark_titlebar(win.winfo_id())
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
    entry = ttk.Entry(body, textvariable=var)
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
    ttk.Button(foot, text="取消", width=8,
               command=lambda: _finish(win, None)).pack(side="right")
    ttk.Button(foot, text="确定", width=8, style="Accent.TButton",
               command=submit).pack(side="right", padx=(0, SPACE["sm"]))

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
def ask_yes_no(parent: tk.Misc, title: str, message: str,
               ok_text: str = "确定", destructive: bool = False) -> bool:
    win = _new_window(parent, title)
    body = _card(win)
    _message_label(body, message)
    win._result = False

    foot = _foot(win)
    ttk.Button(foot, text="取消", width=8,
               command=lambda: _finish(win, False)).pack(side="right")
    ttk.Button(foot, text=ok_text, width=8,
               style="Danger.TButton" if destructive else "Accent.TButton",
               command=lambda: _finish(win, True)).pack(
        side="right", padx=(0, SPACE["sm"]))
    win.bind("<Escape>", lambda e: _finish(win, False))
    win.bind("<Return>", lambda e: _finish(win, True))
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
    ttk.Button(foot, text="确定", width=8, style="Accent.TButton",
               command=lambda: _finish(win, True)).pack(side="right")
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

    frame = tk.Frame(body, bg="#ffffff", bd=0, highlightthickness=0)
    frame.pack()
    canvas = tk.Canvas(frame, bg="#ffffff", highlightthickness=0, bd=0,
                       width=side, height=side)
    canvas.pack(padx=SPACE["md"], pady=SPACE["md"])
    _draw_matrix(canvas, matrix, scale)
    win.qr_canvas = canvas

    link = ttk.Entry(body)
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
    ttk.Button(foot, text="关闭", width=8,
               command=lambda: _finish(win, None)).pack(side="right")
    ttk.Button(foot, text="保存 PNG…", style="Ghost.TButton",
               command=save_png).pack(side="right", padx=(0, SPACE["sm"]))
    ttk.Button(foot, text="复制链接", style="Ghost.TButton",
               command=copy_link).pack(side="right", padx=(0, SPACE["sm"]))
    win.bind("<Escape>", lambda e: _finish(win, None))
    win._qr_size = (width, side + 220)
    return win


def show_qr(parent: tk.Misc, url: str) -> None:
    win = build_qr_window(parent, url)
    width, height = win._qr_size
    _modal(win, width, height)
