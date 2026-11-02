"""源码级检查：gui 类里不得出现"用了但从未赋值"的 self 属性。

缘起：皮肤核验里写了 `self.assets_dir`，但类里根本没有这个属性
（实际变量是 `self.v_assets_dir`，一个 tk.StringVar）。
tk.Tk 的 __getattr__ 会转到底层 tkapp 上找，找不到就抛：

    AttributeError: '_tkinter.tkapp' object has no attribute 'assets_dir'

这类错误在打包前完全看不出来，只有运行到那一行才炸，
而且当时被 try/except 吞成一句"核验异常"，极难定位。

本测试用 AST 静态比对"赋值过的 self 属性"与"用到的 self 属性"，
在运行测试时就把这类拼写错误拦下。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "app.py"

#: tk.Tk / ttk.Frame 等基类自带的方法与 Tcl 命令，以及本类的方法名。
#: 它们"用到了但没在本类赋值"是正常的，不应报错。
#: 新增 Tk 方法调用时需补充本列表。
TK_BUILTINS = {
    "after", "after_cancel", "attributes", "bind", "bind_all", "bind_class",
    "bell", "clipboard_append", "clipboard_clear", "clipboard_get",
    "columnconfigure", "config", "configure", "deiconify", "destroy",
    "event_add", "event_delete", "event_generate", "focus", "focus_displayof",
    "focus_force", "focus_get", "focus_lastfor", "focus_set", "forget",
    "geometry", "grab_current", "grab_release", "grab_set", "grab_set_global",
    "grab_status", "iconbitmap", "iconify", "iconphoto", "lift", "lower",
    "mainloop", "minsize", "maxsize", "option_add", "option_clear",
    "option_get", "option_readfile", "protocol", "quit", "register",
    "resizable", "rowconfigure", "selection_get", "selection_handle",
    "selection_own", "selection_own_get", "send", "setvar", "getvar",
    "state", "tkraise", "title", "transient", "unbind", "unbind_all",
    "unbind_class", "update", "update_idletasks", "wait_window",
    "wait_variable", "wait_visibility", "withdraw", "wm_aspect",
    "wm_attributes", "wm_protocol", "wm_title", "wm_geometry",
    "winfo_id", "winfo_x", "winfo_y", "winfo_width", "winfo_height",
    "winfo_children", "winfo_exists", "winfo_ismapped", "winfo_reqwidth",
    "winfo_reqheight", "winfo_screenwidth", "winfo_screenheight",
    "winfo_toplevel", "winfo_viewable", "winfo_fpixels", "winfo_pixels",
    "winfo_rgb", "winfo_visual", "winfo_depth", "winfo_class",
    "winfo_pathname", "winfo_pointerx", "winfo_pointery", "winfo_rootx",
    "winfo_rooty", "winfo_vrootx", "winfo_vrooty", "winfo_containing",
    "winfo_atom", "winfo_atomname", "winfo_cells", "winfo_colormapfull",
    "winfo_interps", "winfo_manager", "winfo_name", "winfo_parent",
    "winfo_server", "winfo_toplevel",
    # tk 内部
    "tk", "master", "children", "report_callback_exception",
}


def _collect(path: Path) -> tuple[set[str], set[str], set[str]]:
    """返回 (赋值的 self 属性, 用到的 self 属性, 本类方法名)。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assigned: set[str] = set()
    used: set[str] = set()
    methods: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            methods.add(item.name)
            for sub in ast.walk(item):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if (isinstance(t, ast.Attribute)
                                and isinstance(t.value, ast.Name)
                                and t.value.id == "self"):
                            assigned.add(t.attr)
                elif isinstance(sub, ast.AnnAssign):
                    t = sub.target
                    if (isinstance(t, ast.Attribute)
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "self"):
                        assigned.add(t.attr)
                if (isinstance(sub, ast.Attribute)
                        and isinstance(sub.value, ast.Name)
                        and sub.value.id == "self"):
                    used.add(sub.attr)
    return assigned, used, methods


class AttrSanityTest(unittest.TestCase):
    def test_no_undefined_self_attrs(self):
        """app.py 里用到的 self 属性必须已赋值，或是 Tk 内置 / 本类方法。"""
        self.assertTrue(APP.is_file(), "缺少 app.py")
        assigned, used, methods = _collect(APP)
        unknown = sorted(used - assigned - methods - TK_BUILTINS)
        self.assertEqual(
            [], unknown,
            "以下 self 属性被使用但从未赋值（多半是拼写错误，"
            "运行时会抛 AttributeError: '_tkinter.tkapp' object has no "
            "attribute ...）：\n  " + "\n  ".join(unknown))

    def test_assets_dir_uses_stringvar(self):
        """皮肤目录要用 StringVar，不能用不存在的 self.assets_dir。

        注意用 AST 判据而不是文本搜索：文档字符串里提到这个错误写法是允许的
        （它正是用来警示后来者的），只有真实的属性访问才该被拦下。
        """
        _assigned, used, _methods = _collect(APP)
        self.assertNotIn("assets_dir", used,
                         "不应访问 self.assets_dir —— 实际变量是 "
                         "self.v_assets_dir(tk.StringVar)")
        src = APP.read_text(encoding="utf-8")
        self.assertIn("self.v_assets_dir = tk.StringVar", src)
