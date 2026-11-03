"""自绘圆角控件：9 宫格预渲染角块 + Canvas，避免 ttk 直角外观。

为什么要自绘：ttk 控件不是独立 HWND，``SetWindowRgn`` 无法裁控件；而
Canvas 直接画弧会有锯齿。这里用纯 Python 4x4 超采样渲染**角块**（只依赖
zlib），直边用矩形拼接，任意尺寸都不需要重新光栅化；边缘抗锯齿且不引入
Pillow/GDI+ 依赖。Pillow 的体积/导入实测见 docs/round-report.md。

窗口外框圆角走 DWM ``DWMWA_WINDOW_CORNER_PREFERENCE``（Win11），Win10
调用失败时静默保持直角，不影响功能。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.raster import corner_png, photo, rgb, rounded_png

# 兼容既有测试/旧调用名
_corner_png = corner_png
_rounded_png = rounded_png
from core.theme import DARK, ThemedCombobox

from .common import ui_font

_PHOTO_CACHE: dict[tuple, object] = {}


def _corner_photo(size: int, radius: int, fill, bg, corner: int,
                  border=None, border_w: int = 0, transparent: bool = False):
    key = (size, radius, fill, bg, corner, border, border_w, transparent)
    img = _PHOTO_CACHE.get(key)
    if img is None:
        img = photo(corner_png(size, radius, fill, bg, corner, border,
                               border_w, transparent))
        _PHOTO_CACHE[key] = img
    return img


class _RoundItems:
    """Canvas 上一块圆角矩形的 4 个角块 + 3 个直边矩形。"""

    def __init__(self, canvas: tk.Canvas, radius: int, fill: str, bg: str,
                 border: str | None = None):
        self.canvas = canvas
        self.radius = radius
        self.fill = fill
        self.bg = bg
        self.border = border
        b = border or fill
        self.corners = [
            canvas.create_image(0, 0, anchor="nw", image=_corner_photo(
                radius, radius, fill, bg, i, border, 1 if border else 0))
            for i in range(4)]
        # 描边直边（若没有描边就等于填充色）
        self.outer = [canvas.create_rectangle(0, 0, 1, 1, fill=b, outline="")
                      for _ in range(3)]
        self.inner = [canvas.create_rectangle(0, 0, 1, 1, fill=fill, outline="")
                      for _ in range(3)]

    def place(self, x0: int, y0: int, x1: int, y1: int) -> None:
        r = self.radius
        if x1 - x0 <= 2 or y1 - y0 <= 2:
            return
        c = self.canvas
        bw = 1 if self.border else 0
        for rect, coords in zip(self.outer, [
                (x0 + r, y0, x1 - r, y1), (x0, y0 + r, x0 + r, y1 - r),
                (x1 - r, y0 + r, x1, y1 - r)]):
            c.coords(rect, *coords)
        for rect, coords in zip(self.inner, [
                (x0 + r, y0 + bw, x1 - r, y1 - bw),
                (x0 + bw, y0 + r, x0 + r, y1 - r),
                (x1 - r, y0 + r, x1 - bw, y1 - r)]):
            c.coords(rect, *coords)
        for idx in range(4):
            cx = x0 if idx % 2 == 0 else x1 - r
            cy = y0 if idx < 2 else y1 - r
            c.coords(self.corners[idx], cx, cy)

    def hide(self) -> None:
        for iid in self.corners + self.outer + self.inner:
            try:
                self.canvas.itemconfigure(iid, state="hidden")
            except Exception:
                pass

    def show(self) -> None:
        for iid in self.corners + self.outer + self.inner:
            try:
                self.canvas.itemconfigure(iid, state="normal")
            except Exception:
                pass


class RoundSurface(tk.Canvas):
    """圆角容器：固定/自适应尺寸的 1px 描边 + 内嵌 body Frame。

    控件（Entry/Text/滚动条）放在 ``body`` 里，原生方形四角被 body 的
    内缩和同色底盖住，交互完全保留。
    """

    def __init__(self, master, *, bg: str = DARK["bg"], fill: str = DARK["panel"],
                 border: str | None = DARK["border"], radius: int = 10,
                 height: int | None = None, width: int | None = None,
                 autoheight: bool = False, **kw):
        kw.pop("highlightthickness", None)
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         **({"height": height} if height else {}),
                         **({"width": width} if width else {}), **kw)
        self._radius = r = radius
        self._inset = max(4, r // 2)
        self._fill, self._bg = fill, bg
        self._border = border
        self._round = _RoundItems(self, r, fill, bg, border)
        self.body = tk.Frame(self, bg=fill, bd=0, highlightthickness=0)
        self._win = self.create_window(self._inset, self._inset, anchor="nw",
                                       window=self.body)
        self.bind("<Configure>", self._on_configure)
        if autoheight:
            self.body.bind("<Configure>", self._on_body, add="+")

    def _on_configure(self, event=None):
        w = event.width if event is not None else self.winfo_width()
        h = event.height if event is not None else self.winfo_height()
        if w <= 4 or h <= 4:
            return
        self._round.place(0, 0, w, h)
        i = self._inset
        self.coords(self._win, i, i)
        if w > 2 * i and h > 2 * i:
            self.itemconfigure(self._win, width=w - 2 * i, height=h - 2 * i)

    def _on_body(self, _event=None):
        try:
            need = self.body.winfo_reqheight() + 2 * self._inset
        except Exception:
            return
        if need > 1 and abs(need - self.winfo_height()) > 1:
            tk.Canvas.configure(self, height=need)

    def set_border(self, color: str | None) -> None:
        if color == self._border:
            return
        self._border = color
        b = color or self._fill
        for idx, iid in enumerate(self._round.corners):
            self.itemconfigure(iid, image=_corner_photo(
                self._radius, self._radius, self._fill, self._bg, idx,
                color, 1 if color else 0))
        for iid in self._round.outer:
            self.itemconfigure(iid, fill=b)


class RoundField(RoundSurface):
    """圆角输入框：原生 Entry/Combobox 放在圆角底上，输入法与交互不变。"""

    def __init__(self, master, *, kind: str = "entry", bg: str = DARK["panel"],
                 fill: str = DARK["field"], height: int = 32, radius: int = 8,
                 width: int = 120, **kw):
        super().__init__(master, bg=bg, fill=fill, radius=radius,
                         height=height, width=width)
        self._readonly = kind == "combo"
        self._focus_color = DARK["accent"]
        if kind == "combo":
            self.inner = ThemedCombobox(self.body, style="Field.TCombobox", **kw)
        else:
            self.inner = ttk.Entry(self.body, style="Field.TEntry", **kw)
        self.inner.pack(fill="both", expand=True)
        self.inner.bind("<FocusIn>", self._on_focus, add="+")
        self.inner.bind("<FocusOut>", self._on_blur, add="+")
        super().configure(takefocus=0)

    def _on_focus(self, _e=None):
        self.set_border(self._focus_color)

    def _on_blur(self, _e=None):
        self.set_border(DARK["border"])

    # 代理常用接口，调用方无需知道 inner
    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        if "state" in kw and self._readonly and kw["state"] == "normal":
            kw["state"] = "readonly"
        if kw:
            return self.inner.configure(**kw)
        return None

    config = configure

    def cget(self, key):
        return self.inner.cget(key)

    def get(self, *args):
        return self.inner.get(*args)

    def insert(self, *args, **kw):
        return self.inner.insert(*args, **kw)

    def delete(self, *args):
        return self.inner.delete(*args)

    def set(self, *args, **kw):
        return self.inner.set(*args, **kw)

    def focus_set(self):
        return self.inner.focus_set()

    def __getattr__(self, name):
        try:
            inner = object.__getattribute__(self, "inner")
        except AttributeError:
            raise AttributeError(name) from None
        return getattr(inner, name)


class RoundScrollbar(tk.Canvas):
    """细圆角滚动条：保留 set/command 协议，滑块四角抗锯齿。"""

    def __init__(self, master, *, orient: str = "vertical", command=None,
                 bg: str = DARK["well"], thumb: str = DARK["card"],
                 thickness: int = 12, radius: int = 4, **kw):
        vertical = orient == "vertical"
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, takefocus=0,
                         width=thickness if vertical else 1,
                         height=1 if vertical else thickness, **kw)
        self._vertical = vertical
        self._command = command
        self._first, self._last = 0.0, 1.0
        self._drag = None
        self._round = _RoundItems(self, radius, thumb, bg)
        self._round.hide()
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<MouseWheel>", self._on_wheel)

    def set(self, first, last) -> None:
        try:
            self._first, self._last = float(first), float(last)
        except (TypeError, ValueError):
            return
        self._redraw()

    def _total(self) -> int:
        return max(1, self.winfo_height() if self._vertical
                   else self.winfo_width())

    def _thumb(self):
        total = self._total()
        length = max(24, int((self._last - self._first) * total))
        start = int(self._first * total)
        start = min(start, max(0, total - length))
        return start, length, total

    def _redraw(self) -> None:
        if self.winfo_width() <= 1 or self.winfo_height() <= 1:
            return
        if self._last - self._first >= 0.995:
            self._round.hide()
            return
        self._round.show()
        start, length, _ = self._thumb()
        if self._vertical:
            self._round.place(1, start, max(2, self.winfo_width() - 1), start + length)
        else:
            self._round.place(start, 1, start + length, max(2, self.winfo_height() - 1))

    def _on_press(self, event):
        pos = event.y if self._vertical else event.x
        start, length, total = self._thumb()
        if start <= pos <= start + length:
            self._drag = pos - start
        else:
            self._drag = length // 2
            self._move_to(pos)
        return "break"

    def _on_drag(self, event):
        if self._drag is not None:
            self._move_to(event.y if self._vertical else event.x)
        return "break"

    def _on_release(self, _event):
        self._drag = None
        return "break"

    def _move_to(self, pos: int) -> None:
        _, length, total = self._thumb()
        frac = max(0.0, min(1.0, (pos - self._drag) / max(1, total)))
        if self._command:
            try:
                if self._vertical:
                    self._command("moveto", frac)
                else:
                    self._command("moveto", frac)
            except Exception:
                pass

    def _on_wheel(self, event):
        if not self._command:
            return "break"
        step = -1 if event.delta > 0 else 1
        try:
            self._command("scroll", step, "units")
        except Exception:
            pass
        return "break"


class RoundButton(tk.Canvas):
    """32px 高圆角按钮，支持 hover / pressed / disabled 与键盘触发。"""

    _PALETTES = {
        "accent": {
            "normal": ("#0a84ff", None),
            "hover": ("#2f95ff", None),
            "pressed": ("#0070e0", None),
            "disabled": ("#2c2c2e", None),
        },
        "danger": {
            "normal": ("#ff453a", None),
            "hover": ("#ff5f55", None),
            "pressed": ("#d9342b", None),
            "disabled": ("#2c2c2e", None),
        },
        "outline": {
            "normal": ("#232325", "#3a3a3c"),
            "hover": ("#2c2c2e", "#48484a"),
            "pressed": ("#343437", "#5a5a60"),
            "disabled": ("#1e1e1e", "#2c2c2e"),
        },
    }

    def __init__(self, master, text: str, command=None, *, width: int = 96,
                 height: int = 32, radius: int = 8, kind: str = "accent",
                 bg: str = DARK["bg"], font=None, state: str = "normal", **kw):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, takefocus=1, **kw)
        self._command = command
        self._kind = kind if kind in self._PALETTES else "accent"
        self._state = state
        self._label = text
        self._bg = bg
        self._radius = radius
        self._width, self._height = width, height
        self._images: dict[str, list] = {}
        self._fills: dict[str, tuple] = {}
        for name, (fill, border) in self._PALETTES[self._kind].items():
            self._images[name] = [
                _corner_photo(radius, radius, fill, rgb(bg), i, border,
                              1 if border else 0) for i in range(4)]
            self._fills[name] = (fill, border)
        self._corners = [
            self.create_image(0, 0, anchor="nw",
                              image=self._images["normal"][i]) for i in range(4)]
        self._outer = [self.create_rectangle(0, 0, 1, 1, outline="")
                       for _ in range(3)]
        self._inner = [self.create_rectangle(0, 0, 1, 1, outline="")
                       for _ in range(3)]
        self._place(width, height, "normal")
        self._text = self.create_text(
            width / 2, height / 2, text=text,
            fill="#ffffff" if self._kind != "outline" else DARK["fg"],
            font=font or ui_font(10, "bold"))
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<space>", lambda e: self.invoke())
        self._render()

    def _place(self, w: int, h: int, state_name: str) -> None:
        fill, border = self._fills[state_name]
        b = border or fill
        r = self._radius
        for rect, coords in zip(self._outer, [
                (r, 0, w - r, h), (0, r, r, h - r), (w - r, r, w, h - r)]):
            self.coords(rect, *coords)
            self.itemconfigure(rect, fill=b)
        for rect, coords in zip(self._inner, [
                (r, 1 if border else 0, w - r, h - (1 if border else 0)),
                (1 if border else 0, r, r, h - r),
                (w - r, r, w - (1 if border else 0), h - r)]):
            self.coords(rect, *coords)
            self.itemconfigure(rect, fill=fill)
        for idx in range(4):
            self.coords(self._corners[idx],
                        0 if idx % 2 == 0 else w - r,
                        0 if idx < 2 else h - r)

    def _render(self) -> None:
        state = self._state if self._state in self._images else "disabled"
        self._place(self._width, self._height, state)
        for idx, iid in enumerate(self._corners):
            self.itemconfigure(iid, image=self._images[state][idx])
        self.itemconfigure(
            self._text,
            fill=DARK["muted"] if self._state == "disabled"
            else ("#ffffff" if self._kind != "outline" else DARK["fg"]))
        try:
            self.configure(cursor="hand2" if self._state != "disabled" else "arrow")
        except Exception:
            pass

    def _on_enter(self, _e=None):
        if self._state == "normal":
            self._place(self._width, self._height, "hover")
            for idx, iid in enumerate(self._corners):
                self.itemconfigure(iid, image=self._images["hover"][idx])

    def _on_leave(self, _e=None):
        self._pressed = False
        if self._state == "normal":
            self._render()

    def _on_press(self, _e=None):
        if self._state == "normal":
            self._pressed = True
            self._place(self._width, self._height, "pressed")
            for idx, iid in enumerate(self._corners):
                self.itemconfigure(iid, image=self._images["pressed"][idx])

    def _on_release(self, _e=None):
        if self._state != "normal":
            return
        fire = self._pressed
        self._pressed = False
        self._on_enter()
        if fire and self._command:
            self._command()

    # 兼容 ttk.Button 的 state 用法（app.py / tests 里有 configure(state=...)）
    def set_state(self, state: str) -> None:
        self._state = state
        self._render()

    def invoke(self) -> None:
        if self._state == "normal" and self._command:
            self._command()

    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        if "state" in kw:
            self.set_state(kw.pop("state"))
        if "text" in kw:
            self._label = kw.pop("text")
            self.itemconfigure(self._text, text=self._label)
        if kw:
            return super().configure(**kw)
        return None

    config = configure

    def __getitem__(self, key):
        if key == "state":
            return self._state
        if key == "text":
            return self._label
        return super().__getitem__(key)

    @property
    def text(self) -> str:
        return self._label


class RoundPanel(tk.Canvas):
    """圆角卡片：Canvas 画 1px 描边 + 面板底色，内容放在内嵌 body Frame。"""

    def __init__(self, master, *, bg: str = DARK["bg"], fill: str = DARK["panel"],
                 border: str = DARK["border"], radius: int = 10,
                 padding=(10, 8), expand: bool = False,
                 style: str = "Card.TFrame", **kw):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kw)
        self._radius = r = radius
        self._inset = max(4, radius // 2)
        self._expand = expand
        self._round = _RoundItems(self, r, fill, bg, border)
        self.body = ttk.Frame(self, style=style, padding=padding)
        self._win = self.create_window(self._inset, self._inset,
                                       anchor="nw", window=self.body)
        self.bind("<Configure>", self._on_configure)
        self.body.bind("<Configure>", self._on_body, add="+")
        if expand:
            self.configure(height=180)

    def _on_configure(self, event=None):
        w = event.width if event is not None else self.winfo_width()
        h = event.height if event is not None else self.winfo_height()
        if w <= 4 or h <= 4:
            return
        self._round.place(0, 0, w, h)
        i = self._inset
        self.coords(self._win, i, i)
        if w > 2 * i and h > 2 * i:
            self.itemconfigure(self._win, width=w - 2 * i, height=h - 2 * i)

    def _on_body(self, event=None):
        if self._expand:
            return
        try:
            need = self.body.winfo_reqheight() + 2 * self._inset
        except Exception:
            return
        if need > 1 and abs(need - self.winfo_height()) > 1:
            self.configure(height=need)
