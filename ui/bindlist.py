"""固定高度的网卡勾选列表（模态弹窗里的紧凑模式 + 主窗口选择模型）。

弹窗里用 Canvas + 内嵌 Frame 显示固定行数，超出用圆角滚动条，窗口高度随
网卡数量自适应并封顶。主窗口不再显示这个列表，只借它保存勾选状态与排序。

键盘：Tab 进入列表，↑/↓ 移动当前行，空格/回车切换勾选，再按 Tab 离开。
每行的 hover/焦点底色是 6px 圆角块，文字用 Canvas 绘制（无背景方块）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from core.netif import NetIf
from core.theme import DARK, SPACE, fonts

from .common import ellipsize, emoji_font, text_width
from .roundrect import RoundScrollbar, _RoundItems

ROW_HEIGHT = 30
COMPACT_ROW_HEIGHT = 32
VISIBLE_ROWS = 3


class BindCheckList(ttk.Frame):
    """网卡多选列表：普通模式含名称/IP/状态；紧凑模式以 IP 为主信息。"""

    def __init__(self, master, on_change: Callable[[int], None] | None = None,
                 *, compact: bool = False, visible_rows: int = VISIBLE_ROWS,
                 text_budget: int = 0):
        c = DARK
        super().__init__(master, style="TFrame")
        self._on_change = on_change
        self._compact = compact
        self._row_height = COMPACT_ROW_HEIGHT if compact else ROW_HEIGHT
        self._visible_rows = max(1, visible_rows)
        self._text_budget = text_budget       # 紧凑模式 IP+名称的像素预算，0=不限
        self._scrollable = False
        self.items: list[NetIf] = []
        self._vars: list[tk.BooleanVar] = []
        self._rows: list[dict] = []
        self._focus_index = 0
        self._enabled = True

        height = self._row_height * visible_rows
        self.canvas = tk.Canvas(self, bg=c["panel"], highlightthickness=0,
                                borderwidth=0, height=height,
                                takefocus=True, cursor="hand2")
        self.vsb = RoundScrollbar(self, orient="vertical", command=self.canvas.yview,
                                  thickness=10)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns", padx=(SPACE["xs"], 0))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.inner = tk.Frame(self.canvas, bg=c["panel"])
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)
        self._bind_keys()
        self.canvas.bind("<MouseWheel>", self._on_wheel)

    # ---------- 对外 ----------
    def set_items(self, items: Iterable[NetIf],
                  selected: Iterable[str] = ()) -> None:
        selected_set = {s for s in selected}
        self._destroy_rows()
        self.items = list(items)
        self._focus_index = 0
        for index, item in enumerate(self.items):
            var = tk.BooleanVar(value=item.bindable and item.address in selected_set)
            self._vars.append(var)
            self._rows.append(self._make_row(index, item, var))
        self._sync_scrollregion()
        self._sync_width()
        # 行数不超出可视区时收起滚动条，不占右侧宽度
        self._scrollable = len(self.items) > self._visible_rows
        try:
            if self._scrollable:
                self.vsb.grid()
            else:
                self.vsb.grid_remove()
        except Exception:
            pass
        self._paint_rows()
        self._notify()

    def selected(self) -> list[str]:
        out = []
        for item, var in zip(self.items, self._vars):
            if item.bindable and var.get() and item.address:
                out.append(item.address)
        return out

    def set_selection(self, addresses: Iterable[str]) -> None:
        chosen = set(addresses)
        # 通配地址独占：恢复旧配置时若同时含 0.0.0.0 与具体 IP，只保留通配
        wildcard = [item.address for item in self.items
                    if item.is_wildcard and item.address in chosen]
        if wildcard:
            chosen = set(wildcard)
        for item, var in zip(self.items, self._vars):
            var.set(bool(item.bindable and item.address in chosen))
        self._paint_rows()
        self._notify()

    def select_defaults(self) -> None:
        from core.netif import default_binds
        self.set_selection(default_binds(self.items))

    def select_all(self) -> None:
        """「全部」：优先勾选所有具体网卡；没有具体网卡时退化为通配地址。"""
        addresses = [item.address for item in self.items
                     if item.bindable and item.address and not item.is_wildcard]
        if not addresses:
            addresses = [item.address for item in self.items
                         if item.bindable and item.address]
        self.set_selection(addresses)

    def focus_list(self) -> None:
        try:
            self.canvas.focus_set()
        except Exception:
            pass

    def set_enabled(self, enabled: bool) -> None:
        """运行中禁用勾选与键盘操作，但保留深色外观。"""
        self._enabled = bool(enabled)
        try:
            self.canvas.configure(takefocus=bool(enabled),
                                  cursor="hand2" if enabled else "arrow")
        except Exception:
            pass
        for row in self._rows:
            try:
                row["cb"].configure(
                    state="normal" if enabled and row["item"].bindable else "disabled")
            except Exception:
                pass

    # ---------- 行构建 ----------
    def _make_row(self, index: int, item: NetIf, var: tk.BooleanVar) -> dict:
        c = DARK
        f = fonts()
        h = self._row_height
        row = tk.Canvas(self.inner, bg=c["panel"], height=h, bd=0,
                        highlightthickness=0)
        row.grid(row=index, column=0, sticky="ew")
        self.inner.columnconfigure(0, weight=1)

        hover_pill = _RoundItems(row, 6, c["card"], c["panel"])
        focus_pill = _RoundItems(row, 6, c["sel"], c["panel"])
        for pill in (hover_pill, focus_pill):
            pill.hide()

        from core.theme import ThemedCheckbutton
        cb = ThemedCheckbutton(row, variable=var, bg_key="panel",
                               takefocus=False, onvalue=True, offvalue=False)
        row.create_window(9, h / 2, anchor="w", window=cb)

        color = c["fg"] if item.bindable else c["muted"]
        full_text = ""
        if self._compact:
            # IP 主信息；网卡名只作弱化副文本，用于同 IP / 同名场景区分。
            # 默认不截断；只有整行超过最大宽度时才省略，并保留完整值给 tooltip。
            addr_text = item.address or ""
            name_text = item.name or ""
            budget = self._text_budget
            if budget > 0:
                addr_w = text_width(addr_text, f["mono"])
                name_w = text_width(name_text, f["caption"])
                if addr_w + 12 + name_w > budget:
                    name_text, cut_name = ellipsize(
                        name_text, max(0, budget - addr_w - 12), f["caption"])
                    if budget - addr_w - 12 < 30:
                        addr_text, cut_addr = ellipsize(
                            addr_text, max(40, budget - 42), f["mono"])
                        if cut_addr:
                            full_text = (item.address or "") + (
                                " · " + item.name if item.name else "")
                    if not full_text and cut_name and item.name:
                        full_text = item.name
            addr = row.create_text(34, h / 2, anchor="w", text=addr_text,
                                   fill=color, font=f["mono"])
            name = row.create_text(0, h / 2, anchor="e", text=name_text,
                                   fill=c["muted"], font=f["caption"])
            labels = (addr, name)
        else:
            icon = row.create_text(34, h / 2, anchor="w", text=item.icon,
                                   fill=color, font=emoji_font(11))
            name_text = (item.display_name or "")[:11]
            name_item = row.create_text(52, h / 2, anchor="w", text=name_text,
                                        fill=color, font=f["body"])
            addr = row.create_text(158, h / 2, anchor="w",
                                   text=item.address or "无地址",
                                   fill=color, font=f["mono"])
            status = row.create_text(10, h / 2, anchor="e",
                                     text=item.status_text,
                                     fill=c["muted"] if item.bindable else c["border"],
                                     font=f["caption"])
            labels = (icon, name_item, addr, status)

        if self._compact:
            row.bind("<Configure>",
                     lambda e, r=row, n=name, hp=hover_pill, fp=focus_pill:
                     self._place_row(r, None, hp, fp, n))
        else:
            row.bind("<Configure>",
                     lambda e, r=row, s=status, hp=hover_pill, fp=focus_pill:
                     self._place_row(r, s, hp, fp))
        widget = row
        widget.bind("<Button-1>", lambda e, i=index: self._click_row(i))
        widget.bind("<Enter>", lambda e, i=index: self._hover_row(i, True))
        widget.bind("<Leave>", lambda e, i=index: self._hover_row(i, False))
        widget.bind("<MouseWheel>", self._on_wheel)
        cb.bind("<Button-1>", lambda e, i=index: self._click_check(i))
        if not item.bindable or not self._enabled:
            cb.configure(state="disabled")
        return {"row": row, "cb": cb, "labels": labels,
                "item": item, "row_index": index, "hover": hover_pill,
                "focus": focus_pill, "hovered": False,
                "full_text": full_text}

    def _place_row(self, row, status, hover_pill, focus_pill, name=None) -> None:
        w = row.winfo_width()
        if w <= 10:
            return
        for pill in (hover_pill, focus_pill):
            pill.place(2, 1, w - 2, self._row_height - 1)
        try:
            if name is not None:
                row.coords(name, w - 10, self._row_height / 2)
            elif status is not None:
                row.coords(status, w - 10, self._row_height / 2)
        except Exception:
            pass

    def _destroy_rows(self) -> None:
        for row in self._rows:
            try:
                row["row"].destroy()
            except Exception:
                pass
        self._rows.clear()
        self._vars.clear()

    # ---------- 交互 ----------
    def _click_row(self, index: int) -> None:
        if not self._enabled:
            return
        self._focus_index = index
        self._toggle(index)
        self.focus_list()

    def _click_check(self, index: int) -> None:
        # 指示器本身由 tk.Checkbutton 处理变量翻转，这里只同步焦点与互斥
        if not self._enabled:
            return
        self._focus_index = index
        self.focus_list()
        self.after(1, lambda: self._after_check(index))

    def _after_check(self, index: int) -> None:
        self._normalize(index)
        self._paint_rows()
        self._notify()

    def _toggle(self, index: int) -> None:
        if not self._enabled:
            return
        if not (0 <= index < len(self.items)):
            return
        item = self.items[index]
        if not item.bindable:
            return
        var = self._vars[index]
        var.set(not var.get())
        self._normalize(index)
        self._paint_rows()
        self._notify()

    def _normalize(self, index: int) -> None:
        """0.0.0.0 独占：选通配就清空其他，选其他就取消通配。"""
        if not (0 <= index < len(self.items)) or not self._vars[index].get():
            return
        item = self.items[index]
        if item.is_wildcard:
            for i, var in enumerate(self._vars):
                if i != index:
                    var.set(False)
        else:
            for i, other in enumerate(self.items):
                if other.is_wildcard:
                    self._vars[i].set(False)
        self._paint_rows()

    def _hover_row(self, index: int, entering: bool) -> None:
        if not (0 <= index < len(self._rows)):
            return
        self._rows[index]["hovered"] = entering
        self._paint_row(index)

    def _paint_row(self, index: int) -> None:
        row = self._rows[index]
        try:
            if index == self._focus_index:
                row["hover"].hide()
                row["focus"].show()
            elif row["hovered"]:
                row["focus"].hide()
                row["hover"].show()
            else:
                row["hover"].hide()
                row["focus"].hide()
        except Exception:
            pass

    def _paint_rows(self) -> None:
        for index in range(len(self._rows)):
            self._paint_row(index)

    def _notify(self) -> None:
        if self._on_change:
            try:
                self._on_change(len(self.selected()))
            except Exception:
                pass

    # ---------- 键盘/滚动 ----------
    def _bind_keys(self) -> None:
        self.canvas.bind("<Up>", lambda e: self._move(-1))
        self.canvas.bind("<Down>", lambda e: self._move(1))
        self.canvas.bind("<space>", lambda e: self._toggle(self._focus_index))
        self.canvas.bind("<Return>", lambda e: self._toggle(self._focus_index))
        self.canvas.bind("<FocusIn>", lambda e: self._paint_rows())
        self.canvas.bind("<FocusOut>", lambda e: self._paint_rows())

    def _move(self, delta: int) -> str:
        if not self._enabled or not self.items:
            return "break"
        index = max(0, min(len(self.items) - 1, self._focus_index + delta))
        self._focus_index = index
        self._paint_rows()
        self._ensure_visible(index)
        return "break"

    def _ensure_visible(self, index: int) -> None:
        try:
            top = self.canvas.canvasy(0)
            view_h = max(1, self.canvas.winfo_height())
            row_top = index * self._row_height
            row_bottom = row_top + self._row_height
            total = max(1, len(self.items) * self._row_height)
            if row_top < top:
                self.canvas.yview_moveto(row_top / total)
            elif row_bottom > top + view_h:
                offset = row_bottom - view_h
                self.canvas.yview_moveto(offset / total)
        except Exception:
            pass

    def _on_wheel(self, event) -> str:
        if not self._scrollable:
            return "break"
        try:
            steps = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(steps, "units")
        except Exception:
            pass
        return "break"

    def _sync_scrollregion(self, _event=None) -> None:
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    def _sync_width(self, event=None) -> None:
        try:
            width = event.width if event is not None else self.canvas.winfo_width()
            self.canvas.itemconfigure(self._window, width=max(1, width))
        except Exception:
            pass
