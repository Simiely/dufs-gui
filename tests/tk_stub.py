"""tkinter 桩：让 GUI 构建流程能在无显示环境（CI / Linux 沙盒）里冒烟测试。

只实现 app.py 实际用到的 API 表面；未知属性会抛 AttributeError，
因此能捕获 widget 变量名拼错、方法调用顺序错等低级错误。
"""

from __future__ import annotations

import sys
import types


class Var:
    def __init__(self, value=None):
        self._v = value

    def set(self, v):
        self._v = v

    def get(self):
        return self._v

    def trace_add(self, *_a, **_kw):
        pass


class StringVar(Var):
    pass


class IntVar(Var):
    def __init__(self, value=0):
        super().__init__(value)


class BooleanVar(Var):
    def __init__(self, value=False):
        super().__init__(value)


class Widget:
    def __init__(self, *args, **kw):
        self.args = args
        self.kw = dict(kw)
        self._mapped = False

    # tkinter 通用 API
    def configure(self, **kw):
        self.kw.update(kw)
        return self.kw

    config = configure

    def cget(self, key):
        return self.kw.get(key)

    def __getitem__(self, key):
        return self.kw.get(key)

    def __setitem__(self, key, value):
        self.kw[key] = value

    def grid(self, **kw):
        self._mapped = True

    def pack(self, **kw):
        self._mapped = True

    def place(self, **kw):
        self._mapped = True

    def grid_forget(self):
        self._mapped = False

    def columnconfigure(self, *_a, **_kw):
        pass

    def rowconfigure(self, *_a, **_kw):
        pass

    def bind(self, *_a, **_kw):
        pass

    def winfo_ismapped(self):
        return self._mapped

    def winfo_id(self):
        return 0

    def update_idletasks(self):
        pass

    def option_add(self, *_a, **_kw):
        pass

    def set(self, *_a, **_kw):
        pass

    def get(self):
        return (0.0, 1.0)

    def winfo_rootx(self):
        return 0

    def winfo_rooty(self):
        return 0

    def winfo_width(self):
        return 1020

    def winfo_height(self):
        return 760

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def winfo_reqheight(self):
        return 720

    def winfo_reqwidth(self):
        return 640

    def winfo_children(self):
        return list(getattr(self, "_children", []))

    def after(self, *_a, **_kw):
        return "t"

    def invoke(self):
        cmd = self.kw.get("command")
        if cmd:
            cmd()


class Toplevel(Widget):
    def __init__(self, master=None, *a, **kw):
        super().__init__(*a, **kw)
        self.master = master
        self._alive = True
        self._title = ""
        self._geometry = ""
        self._protocol = {}

    def title(self, t=""):
        self._title = t

    def geometry(self, g=""):
        self._geometry = g

    def minsize(self, *_a):
        pass

    def transient(self, *_a):
        pass

    def grab_set(self):
        pass

    def grab_release(self):
        pass

    def lift(self):
        pass

    def withdraw(self):
        pass

    def deiconify(self):
        pass

    def focus_force(self):
        pass

    def protocol(self, name, func=None):
        self._protocol[name] = func

    def destroy(self):
        if not self._alive:
            return
        self._alive = False
        cb = self._protocol.pop("WM_DELETE_WINDOW", None)
        if cb:
            cb()

    def winfo_exists(self):
        return self._alive


class PhotoImage:
    """桩：自绘复选框位图用。"""

    def __init__(self, *a, **kw):
        pass

    def put(self, *a, **kw):
        pass


class Checkbutton(Widget):
    """tk.Checkbutton 桩。"""

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self.kw = kw

    def select(self):
        pass

    def deselect(self):
        pass

    def toggle(self):
        pass


class Canvas(Widget):
    """够用的 Canvas 桩：只支持 create_window / itemconfigure / bbox / yview。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._items = {}

    def create_window(self, pos, window=None, anchor="nw"):
        self._items[1] = window
        return 1

    def itemconfigure(self, iid, **kw):
        return None

    def bbox(self, *_a):
        return (0, 0, 640, 720)

    def yview(self, *_a):
        return None

    def yview_scroll(self, *_a):
        return None


class Tk(Widget):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._after = []

    def title(self, *_a):
        pass

    def geometry(self, *_a):
        pass

    def minsize(self, *_a):
        pass

    def columnconfigure(self, *_a, **_kw):
        pass

    def rowconfigure(self, *_a, **_kw):
        pass

    def protocol(self, *_a, **_kw):
        pass

    def option_add(self, *_a, **_kw):
        pass

    def set(self, *_a, **_kw):
        pass

    def get(self):
        return (0.0, 1.0)

    def winfo_rootx(self):
        return 0

    def winfo_rooty(self):
        return 0

    def winfo_width(self):
        return 1020

    def winfo_height(self):
        return 760

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def winfo_reqheight(self):
        return 720

    def winfo_reqwidth(self):
        return 640

    def winfo_children(self):
        return list(getattr(self, "_children", []))

    def after(self, _ms, cb=None, *_a):
        self._after.append(cb)  # 不真正循环，避免无限递归
        return "t"

    def mainloop(self, *_a):
        pass

    def update_idletasks(self):
        pass

    def clipboard_clear(self):
        pass

    def clipboard_append(self, *_a):
        pass

    def destroy(self):
        pass


class Text(Widget):
    def insert(self, *_a, **_kw):
        pass

    def see(self, *_a):
        pass

    def get(self, *_a):
        return ""

    def delete(self, *_a):
        pass


class ScrolledText(Text):
    pass


class Style:
    def __init__(self, root=None):
        self.root = root

    def theme_names(self):
        return ("clam", "default")

    def theme_use(self, name):
        pass

    def configure(self, *_a, **_kw):
        pass

    def map(self, *_a, **_kw):
        pass


def _dialog(*_a, **_kw):
    return None


class _NoWindow:
    pass


def install() -> None:
    """把桩装进 sys.modules，必须在 import app 之前调用。"""
    tk = types.ModuleType("tkinter")
    tk.Tk = Tk
    tk.Toplevel = Toplevel
    tk.Canvas = Canvas
    tk.Checkbutton = Checkbutton
    tk.PhotoImage = PhotoImage
    tk.Frame = Widget
    tk.Label = Widget
    tk.Button = Widget
    tk.Entry = Widget
    tk.Text = Text
    tk.StringVar = StringVar
    tk.IntVar = IntVar
    tk.BooleanVar = BooleanVar
    tk.TclError = RuntimeError
    tk.Misc = Widget
    tk.constants = types.SimpleNamespace()

    ttk = types.ModuleType("tkinter.ttk")
    for name in ("Frame", "Label", "Button", "Entry", "Combobox", "Checkbutton",
                 "Radiobutton", "LabelFrame", "Progressbar", "Separator", "Notebook",
                 "Treeview", "Scrollbar"):
        setattr(ttk, name, Widget)
    ttk.Style = Style

    scrolled = types.ModuleType("tkinter.scrolledtext")
    scrolled.ScrolledText = ScrolledText

    for mod_name, answers in (
        ("tkinter.filedialog", {"askdirectory": None, "askopenfilename": None,
                                "askopenfilenames": (), "asksaveasfilename": None}),
        ("tkinter.messagebox", {"askyesno": True, "askokcancel": True, "showerror": None,
                                "showinfo": None, "showwarning": None}),
        ("tkinter.simpledialog", {"askstring": None}),
    ):
        m = types.ModuleType(mod_name)
        for fn, val in answers.items():
            setattr(m, fn, (lambda v=val, *_a, **_kw: v))
        sys.modules[mod_name] = m

    sys.modules["tkinter"] = tk
    sys.modules["tkinter.ttk"] = ttk
    sys.modules["tkinter.scrolledtext"] = scrolled
    tk.ttk = ttk
