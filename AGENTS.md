# AGENTS.md · 项目规则

> 📌 **代码基线**：2026-11-02 v1.5.0（commit `7e5f8a8`，加入 Windows CI 的提交）
> 后续更新请追加新提交并在 CHANGELOG 记录；**不要引用已不在仓库历史中的 commit**。

## 技术栈

- Python **3.9+**（打包推荐官方 CPython **3.12.x**），仅标准库：tkinter / ttk
- 打包：PyInstaller（onefile 为主，支持 onedir）
- 被封装对象：**dufs**（Rust 编写的单文件服务器，以子进程方式拉起）
- 网页皮肤：dufs 官方 assets v0.47.0 + CSS 覆盖层，零框架零 CDN

## 关键坑（改代码前必读）

1. **spec 里没有 `OS` 全局变量**。PyInstaller 的全局变量只有 `DISTPATH / HOMEPATH / SPEC / SPECPATH / specnm / workpath / WARNFILE`。判断系统必须 `import os` 后用 `os.name`。写 `OS == "nt"` 会 NameError 中断打包。
2. **`.bat` 必须存成 GBK 或纯 ASCII**。Windows 中文 cmd 按 GBK 读批处理，UTF-8 中文会被解成乱码并被当成命令执行（满屏"不是内部或外部命令"）。本项目所有 bat 用**纯 ASCII 英文**。
3. **`--assets` 目录必须含 `index.html`**。dufs `src/args.rs` 的 `sanitize_assets_path` 会 `bail!`。只放 CSS 会让 dufs 拒绝启动。
4. **Windows 上必须清理子进程的 DLL 搜索路径**。bootloader 用 `SetDllDirectoryW` 指向 `_MEIPASS`，该设置**被子进程继承**，外部 dufs.exe 可能加载到不兼容 DLL。`Popen` 前调 `SetDllDirectoryW(None)` 并从 PATH 剔除 `_MEIPASS`。
5. **ttk.Combobox 的下拉列表是原生 tk.Listbox，不是 ttk 控件**。`ttk.Style` 无效，只能用 option database，且大小写敏感（`selectBackground` 的 B 必须大写）。运行时切主题还得用 `tk.eval` 直接刷。
6. **clam 主题的对勾是硬编码深色，且 `indicatorcolor` 会静默失效**（不报错，就是没效果）。
   不要靠配色去调，直接**自绘 16x16 位图 + `element_create` 替换指示器**
   （见 `core/theme.py` 的 `_install_check_indicator`）。自绘图片必须长期持有引用，否则被 GC 后变空白。
7. **网页皮肤必须用官方 assets，不要自造前端**。曾手写过整套 index.html/index.js，
   等于猜测 dufs 内部契约（数据节点是 `<template id="index-data">`、IndexData 字段、
   DOM class、权限判定），结果是上传/下载/预览全失效且 dufs 端不报错。
   正确做法：完整搬运官方 assets，只覆盖 `index.css` 的 CSS 变量。
   升级 dufs 后执行 `python tools/fetch_skin.py <版本>` 重新生成。
8. **`ttk.Label` 不要写死 `wraplength`**。窗口宽度和可用宽度不一致时换行位置会错乱，
   长文本被截得看不懂（等效命令曾显示成 `--e`）。改为 `<Configure>` 里按真实宽度自适应。

## 约定

- UI 文案中文；代码注释中文；docstring 中文
- 除 PyInstaller 外**不引入第三方运行时依赖**（保持打包体积小、可靠性高）
- `bin/dufs.exe` 不入库（体积大 + 平台相关），用 `tools/fetch_dufs.py` 获取
- 所有 bat 纯 ASCII；README 等 Markdown 用 UTF-8
- `console=False` 时异常会静默消失，任何崩溃都要能被 `core/crashlog.py` 捕获落盘

## 版本管理

版本号**唯一定义在 `core/__init__.py` 的 `APP_VERSION`**，界面标题与打包产物名
（`dist\DufsGui-vX.Y.Z.exe`）都从它派生。**改版本只改这一处**，
不要去改 app.py 或 spec 里的字面量。

## 常用命令

```bat
build.bat              :: 打正式单文件 exe（dist\DufsGui-v1.5.0.exe）
build_debug.bat        :: 诊断版：环境体检 + 控制台 + 抓输出（排错先跑它）
run_debug.bat          :: 只运行已有 exe 并抓取全部输出
python main.py         :: 源码直接跑
python -m unittest discover -s tests   :: 跑全部测试（127 项，1 项 jsdom 跳过）
```

Windows CI：`.github/workflows/windows-ci.yml`，Python 3.9 / 3.12 矩阵。

打包开关（环境变量）：`DUFS_GUI_MODE=onefile|onedir`、`DUFS_GUI_CONSOLE=1`、`DUFS_GUI_COLLECT_TK=1`。

## 详细规则（按需 @引用）

- @docs/问题记录/ 目录（一坑一篇，含根因与修法）

## 平台限制

Windows CI 已覆盖 127 项单测（Python 3.9 / 3.12；1 项 jsdom 皮肤 E2E 自动跳过），
并在本机验证过真实 Tk 窗口构造与端口输入。**GUI 的视觉观感、网页皮肤的实际效果
仍需在真实 Windows 桌面上确认**，涉及视觉的判断一律以实机结果为准。
