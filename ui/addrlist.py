"""共享地址列表：网址优先、无滚动条、能显示几行就显示几行。

网址用 10pt 加粗高对比，网卡名降为右侧 8.5pt 弱化信息；每行是一块
圆角 6px 的浅色底，hover 变亮，点击复制。超出高度的地址用一行
「还有 N 个」提示，而不是加滚动条。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Iterable

from core.theme import DARK

from .common import ui_font
from .roundrect import _RoundItems

ROW_HEIGHT = 28
GAP = 3


class AddressList(tk.Canvas):
    def __init__(self, master, *, bg: str = DARK["panel"],
                 on_copy: Callable[[str], None] | None = None,
                 on_overflow: Callable[[int], None] | None = None, **kw):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kw)
        self._bg = bg
        self._on_copy = on_copy
        self._on_overflow = on_overflow
        self._rows: list[dict] = []
        self._pills: list[dict] = []
        self.hidden = 0
        self._hover = -1
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Leave>", self._on_leave)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Button-1>", self._on_click)

    def set_rows(self, rows: Iterable[tuple[str, str, str]]) -> None:
        self._rows = list(rows)
        self._redraw()

    # ---------------- 绘制 ----------------
    def _redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            pass
        self._hover = -1
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 20 or h <= 10:
            return
        self._pills = []
        if not self._rows:
            self.hidden = 0
            self.create_text(12, 10, anchor="nw", text="尚未选择共享地址",
                             fill=DARK["muted"], font=ui_font(9))
            self._notify_overflow()
            return
        capacity = max(1, (h + GAP) // (ROW_HEIGHT + GAP))
        shown = self._rows[:capacity]
        y = 0
        for url, label, status in shown:
            self._draw_row(y, w, url, label, status)
            y += ROW_HEIGHT + GAP
        self.hidden = len(self._rows) - len(shown)
        self._notify_overflow()

    def _notify_overflow(self) -> None:
        if self._on_overflow:
            try:
                self._on_overflow(self.hidden)
            except Exception:
                pass

    def _draw_row(self, y: int, w: int, url: str, label: str, status: str) -> None:
        normal = _RoundItems(self, 6, DARK["field"], self._bg)
        hover = _RoundItems(self, 6, DARK["sel"], self._bg)
        normal.place(1, y, w - 1, y + ROW_HEIGHT)
        hover.place(1, y, w - 1, y + ROW_HEIGHT)
        hover.hide()
        color = {"运行中": DARK["ok"], "启动中": DARK["warn"],
                 "失败": DARK["danger"], "无响应": DARK["warn"],
                 "已停止": DARK["muted"]}.get(status, DARK["accent"])
        dot = self.create_text(12, y + ROW_HEIGHT / 2, text="●", anchor="w",
                               fill=color, font=ui_font(8))
        url_item = self.create_text(26, y + ROW_HEIGHT / 2, text=url, anchor="w",
                                    fill=DARK["fg"], font=ui_font(10, "bold"))
        sub_w = 0
        sub = ""
        sub_item = self.create_text(w - 12, y + ROW_HEIGHT / 2, text=sub,
                                    anchor="e", fill=DARK["muted"],
                                    font=ui_font(9))
        if w >= 300 and label:
            sub = label if len(label) <= 10 else label[:9] + "…"
            self.itemconfigure(sub_item, text=sub)
            x0, _, x1, _ = self.bbox(sub_item)
            sub_w = x1 - x0
        avail = w - 26 - 12 - (sub_w + 12 if sub_w else 0)
        if sub_w and avail < 80:            # 太窄就放弃右侧次要标签
            sub_w = 0
            self.itemconfigure(sub_item, text="")
            avail = w - 26 - 12
        self._fit_middle(url_item, url, max(avail, 24))
        self._pills.append({"y": y, "normal": normal, "hover": hover,
                            "items": (dot, url_item, sub_item)})

    def _fit_middle(self, item: int, text: str, max_w: int) -> None:
        """超出可用宽度时在中间省略，保住协议头与端口。"""
        self.itemconfigure(item, text=text)
        x0, _, x1, _ = self.bbox(item)
        if x1 - x0 <= max_w:
            return
        best = "…"
        lo, hi = 0, len(text)
        while lo <= hi:
            keep = (lo + hi) // 2
            head = (keep + 1) // 2
            tail = keep // 2
            cand = text[:head] + "…" + text[-tail:] if tail else text[:head] + "…"
            self.itemconfigure(item, text=cand)
            x0, _, x1, _ = self.bbox(item)
            if x1 - x0 <= max_w:
                best = cand
                lo = keep + 1
            else:
                hi = keep - 1
        self.itemconfigure(item, text=best)

    # ---------------- 交互 ----------------
    def _row_at(self, y: int) -> int:
        for idx, row in enumerate(self._pills):
            if row["y"] <= y < row["y"] + ROW_HEIGHT:
                return idx
        return -1

    def _on_motion(self, event) -> None:
        idx = self._row_at(event.y)
        if idx == self._hover:
            return
        if 0 <= self._hover < len(self._pills):
            self._pills[self._hover]["hover"].hide()
            self._pills[self._hover]["normal"].show()
        self._hover = idx
        if idx >= 0:
            self._pills[idx]["normal"].hide()
            self._pills[idx]["hover"].show()
        try:
            self.configure(cursor="hand2" if idx >= 0 else "arrow")
        except Exception:
            pass

    def _on_leave(self, _event=None) -> None:
        if 0 <= self._hover < len(self._pills):
            self._pills[self._hover]["hover"].hide()
            self._pills[self._hover]["normal"].show()
        self._hover = -1

    def _on_click(self, event) -> None:
        idx = self._row_at(event.y)
        if idx < 0:
            return
        row = self._pills[idx]
        url = self._rows[idx][0]
        if self._on_copy:
            self._on_copy(url)
