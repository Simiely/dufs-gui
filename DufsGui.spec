# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：python -m PyInstaller DufsGui.spec

两种模式（由环境变量 DUFS_GUI_MODE 控制）：
    onefile（默认）→ 单个 DufsGui.exe
    onedir         → dist\\DufsGui\\ 目录，启动更快、杀软误报更低

可选开关：
    DUFS_GUI_CONSOLE=1    控制台版（诊断闪退用，产物名带 -debug）
    DUFS_GUI_COLLECT_TK=1 强制 --collect-all tkinter（Tcl/Tk 缺失时才需要）

注意：spec 文件可用的全局变量只有 DISTPATH / HOMEPATH / SPEC / SPECPATH /
specnm / workpath / WARNFILE 以及 PyInstaller 定义的类。
**没有 OS / platform 这种变量**，要用就自己 import os / sys。
（曾在这里踩过 NameError: name 'OS' is not defined）
"""

import os
import sys

ROOT = os.path.abspath(SPECPATH)  # noqa: F821
IS_WIN = os.name == "nt"

DEBUG = os.environ.get("DUFS_GUI_CONSOLE") == "1"
COLLECT_TK = os.environ.get("DUFS_GUI_COLLECT_TK") == "1"
MODE = os.environ.get("DUFS_GUI_MODE", "onefile").lower()
ONEDIR = MODE == "onedir"

# 版本号从 core/__init__.py 读，避免两处不同步
def _read_version() -> str:
    import re
    src = os.path.join(ROOT, "core", "__init__.py")
    try:
        with open(src, encoding="utf-8") as f:
            m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', f.read())
        return m.group(1) if m else "0.0.0"
    except OSError:
        return "0.0.0"


VER = _read_version()
NAME = f"DufsGui-v{VER}" + ("-debug" if DEBUG else "")

DUFS_NAME = "dufs.exe" if IS_WIN else "dufs"
DUFS = os.path.join(ROOT, "bin", DUFS_NAME)

# 用 binaries 而不是 datas：PyInstaller 保证 binaries 保留可执行权限位
binaries = []
if os.path.isfile(DUFS):
    binaries.append((DUFS, "bin"))
    print(f"[spec] 内置 dufs：{DUFS}")
else:
    print(f"[spec] 警告：没找到 {DUFS}，将打出不带 dufs 的产物")
    print("[spec] 启动后可在「高级设置 → dufs 程序 → 更换…」手动指定")

datas = []
# 网页皮肤：CSS/JS 已内联进 index.html，故只需保证 index.html 存在
# —— dufs 启动时硬性校验 --assets 目录里必须有 index.html，缺了直接 bail 拒绝启动
#
# 目录命名：这里必须打成 "assets"（与源码 core/dufsbin.py 的 webui_dir() 一致）。
# 若打成别的名字（如 "webui"），运行时 resource_dir()/"assets"/index.html 就找不到，
# --assets 静默失效、页面退回默认样式——这是 v1.2.1 之前"皮肤不生效"的直接原因。
# 打包成目录整体（而不是逐文件平铺），可保留目录结构、便于将来增加 favicon.ico 等文件。
# 官方方案：完整搬运 dufs 官方 assets，只覆盖 index.css 里的 CSS 变量。
# index.html / index.js / favicon.ico 必须与 dufs 同版本，因此一并随包提供。
UI_FILES = ["index.html", "index.css", "index.js", "favicon.ico", "ASSETS_VERSION"]
WEBUI = os.path.join(ROOT, "assets")
if os.path.isdir(WEBUI):
    missing = [f for f in UI_FILES if not os.path.isfile(os.path.join(WEBUI, f))]
    if missing:
        print(f"[spec] 错误：缺少 {missing}，网页皮肤不完整，--assets 将无法生效")
    else:
        # (源目录, 目标目录名) —— 目标必须是 "assets"
        datas.append((WEBUI, "assets"))
        print(f"[spec] 内置网页皮肤：{WEBUI} -> assets/")
else:
    print(f"[spec] 警告：{WEBUI} 目录不存在，将不带网页皮肤打包")

# 上游 dufs 的双许可证原文 + 来源说明，随包分发以满足 MIT/Apache-2.0 的再分发要求
LICENSES = os.path.join(ROOT, "licenses")
if os.path.isdir(LICENSES):
    datas.append((LICENSES, "licenses"))
    print(f"[spec] 内置上游许可证：{LICENSES} -> licenses/")
else:
    print(f"[spec] 警告：{LICENSES} 不存在，产物将缺少 dufs 上游许可证")

hiddenimports = [
    "core", "core.config", "core.dufsbin", "core.netutil", "core.server",
    "core.theme", "core.crashlog", "core.app_state", "core.winpos",
    # 批次 2 拆分出的模块：显式声明，避免冻结环境漏收集
    "core.launch", "core.runtime",
    "ui", "ui.common", "ui.form", "ui.layout", "ui.advanced",
]

# tkinter 子模块：显式声明比依赖自动分析更保险，但只在构建机真有 tkinter 时声明，
# 否则 PyInstaller 会刷一屏 "Hidden import 'tkinter.xxx' not found" 掩盖真正的错误。
try:
    import tkinter  # noqa: F401

    hiddenimports += [
        "tkinter", "tkinter.ttk", "tkinter.constants", "tkinter.font",
        "tkinter.scrolledtext", "tkinter.filedialog", "tkinter.messagebox",
        "tkinter.simpledialog", "tkinter.commondialog", "tkinter.colorchooser",
    ]
    print(f"[spec] tkinter 可用（Tk {tkinter.TkVersion}），已声明子模块")
except ImportError:
    print("[spec] 警告：构建环境没有 tkinter，打出来的东西大概率起不来")
    print("[spec] 请换用 python.org 官方 CPython（不要 conda / 嵌入式版）")

# 仅在有证据表明 Tcl/Tk 收集不足时启用。PyInstaller 官方不推荐滥用 --collect-all，
# 因为它会无差别拉入整个包（见 discussions #7899）；这里做成开关，默认关闭。
if COLLECT_TK:
    try:
        from PyInstaller.utils.hooks import collect_all

        d, b, h = collect_all("tkinter")
        datas += d
        binaries += b
        hiddenimports += h
        print(f"[spec] --collect-all tkinter：+{len(d)} 数据 / +{len(b)} 二进制 / +{len(h)} 模块")
    except Exception as e:  # noqa: BLE001
        print(f"[spec] collect_all('tkinter') 失败，忽略：{type(e).__name__}: {e}")

block_cipher = None

a = Analysis(  # noqa: F821
    ["main.py"],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6", "PyQt5", "PyQt6", "PIL", "numpy", "pandas",
              "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

if ONEDIR:
    # onedir：exe + _internal 目录。启动快、不往 TEMP 释放、杀软误报显著更低
    exe = EXE(  # noqa: F821
        pyz,
        a.scripts,
        exclude_binaries=True,
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=DEBUG,
        disable_windowed_traceback=False,
    )
    coll = COLLECT(  # noqa: F821
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name=NAME,
    )
else:
    exe = EXE(  # noqa: F821
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,          # 关掉 UPX：压缩壳容易被杀软误报
        runtime_tmpdir=None,
        console=DEBUG,      # 诊断版保留控制台，正式版隐藏
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
