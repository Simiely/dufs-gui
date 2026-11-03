"""固定高度的网卡勾选列表。

为什么不用下拉：多选下拉在不同平台上的键盘/焦点行为差异很大，而且展开时会
遮挡其他控件。这里用 Canvas + 内嵌 Frame 固定显示 5 行，超出用深色滚动条，
窗口高度不随网卡数量变化。

键盘：Tab 进入列表，↑/↓ 移动当前行，空格/回车切换勾选，再按 Tab 离开。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from core.netif import NetIf
from core.theme import DARK, SPACE, fonts

ROW_HEIGHT = 30
VISIBLE_ROWS = 5


class BindCheckList(ttk.Frame):
    """网卡多选列表：勾选框 + 名称 + IP + 状态。"""

    def __init__(self, master, on_change: Callable[[int], None] | None = None):
        c = DARK
        super().__init__(master, style="TFrame")
        self._on_change = on_change
        self.items: list[NetIf] = []
        self._vars: list[tk.BooleanVar] = []
        self._rows: list[dict] = []
        self._focus_index = 0
        self._enabled = True

        height = ROW_HEIGHT * VISIBLE_ROWS
        self.canvas = tk.Canvas(self, bg=c["panel"], highlightthickness=0,
                                borderwidth=0, height=height,
                                takefocus=True, cursor="hand2")
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
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
        row = tk.Frame(self.inner, bg=c["panel"], height=ROW_HEIGHT)
        row.grid(row=index, column=0, sticky="ew")
        row.grid_propagate(False)
        self.inner.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)

        from core.theme import ThemedCheckbutton
        cb = ThemedCheckbutton(row, variable=var, bg_key="panel",
                               takefocus=False, onvalue=True, offvalue=False)
        cb.grid(row=0, column=0, padx=(2, SPACE["sm"]), pady=SPACE["xs"], sticky="w")

        name = tk.Label(row, text=item.display_name, bg=c["panel"],
                        fg=c["fg"] if item.bindable else c["muted"],
                        font=f["body"], anchor="w", width=13)
        name.grid(row=0, column=1, sticky="ew")

        address = item.address or "无地址"
        addr = tk.Label(row, text=address, bg=c["panel"],
                        fg=c["fg"] if item.bindable else c["muted"],
                        font=f["mono"], anchor="w", width=15)
        addr.grid(row=0, column=2, sticky="w", padx=(SPACE["sm"], SPACE["sm"]))

        status = tk.Label(row, text=item.status_text, bg=c["panel"],
                          fg=c["muted"] if item.bindable else c["border"],
                          font=f["caption"], anchor="e", width=14)
        status.grid(row=0, column=3, sticky="e", padx=(0, SPACE["sm"]))

        widgets = (row, name, addr, status)
        for widget in widgets:
            widget.bind("<Button-1>", lambda e, i=index: self._click_row(i))
            widget.bind("<Enter>", lambda e, i=index: self._hover_row(i, True))
            widget.bind("<Leave>", lambda e, i=index: self._hover_row(i, False))
            widget.bind("<MouseWheel>", self._on_wheel)
        cb.bind("<Button-1>", lambda e, i=index: self._click_check(i))
        if not item.bindable or not self._enabled:
            cb.configure(state="disabled")
        return {"row": row, "cb": cb, "labels": (name, addr, status),
                "item": item, "row_index": index}

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
        if index == self._focus_index:
            return
        if not (0 <= index < len(self._rows)):
            return
        bg = DARK["sel"] if entering else DARK["panel"]
        self._set_row_bg(index, bg)

    def _set_row_bg(self, index: int, bg: str) -> None:
        row = self._rows[index]
        try:
            row["row"].configure(bg=bg)
            for label in row["labels"]:
                label.configure(bg=bg)
            row["cb"].configure(bg=bg, activebackground=bg)
        except Exception:
            pass

    def _paint_rows(self) -> None:
        for index, row in enumerate(self._rows):
            bg = DARK["sel"] if index == self._focus_index else DARK["panel"]
            self._set_row_bg(index, bg)
            try:
                row["cb"].configure(bg=bg)
            except Exception:
                pass

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
            row_top = index * ROW_HEIGHT
            row_bottom = row_top + ROW_HEIGHT
            if row_top < top:
                self.canvas.yview_moveto(row_top / max(1, len(self.items) * ROW_HEIGHT))
            elif row_bottom > top + view_h:
                offset = row_bottom - view_h
                self.canvas.yview_moveto(offset / max(1, len(self.items) * ROW_HEIGHT))
        except Exception:
            pass

    def _on_wheel(self, event) -> str:
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
