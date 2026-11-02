# AGENTS.md · 项目规则

> 📌 **文档基线**：2026-11-02（commit 待推送后回填）v1.1.0 版本号收归单一真源
> **更新文档/代码后，请更新此行**（日期 + 新 commit hash），并在 CHANGELOG 追加版本

## 技术栈

- Python **3.9+**（打包推荐官方 CPython **3.12.x**），仅标准库：tkinter / ttk
- 打包：PyInstaller（onefile 为主，支持 onedir）
- 被封装对象：**dufs**（Rust 编写的单文件服务器，以子进程方式拉起）
- 网页皮肤：`assets/` 下自研原生 HTML/CSS/JS，零框架零 CDN

## 关键坑（改代码前必读）

1. **spec 里没有 `OS` 全局变量**。PyInstaller 的全局变量只有 `DISTPATH / HOMEPATH / SPEC / SPECPATH / specnm / workpath / WARNFILE`。判断系统必须 `import os` 后用 `os.name`。写 `OS == "nt"` 会 NameError 中断打包。
2. **`.bat` 必须存成 GBK 或纯 ASCII**。Windows 中文 cmd 按 GBK 读批处理，UTF-8 中文会被解成乱码并被当成命令执行（满屏"不是内部或外部命令"）。本项目所有 bat 用**纯 ASCII 英文**。
3. **`--assets` 目录必须含 `index.html`**。dufs `src/args.rs` 的 `sanitize_assets_path` 会 `bail!`。只放 CSS 会让 dufs 拒绝启动。
4. **Windows 上必须清理子进程的 DLL 搜索路径**。bootloader 用 `SetDllDirectoryW` 指向 `_MEIPASS`，该设置**被子进程继承**，外部 dufs.exe 可能加载到不兼容 DLL。`Popen` 前调 `SetDllDirectoryW(None)` 并从 PATH 剔除 `_MEIPASS`。
5. **ttk.Combobox 的下拉列表是原生 tk.Listbox，不是 ttk 控件**。`ttk.Style` 无效，只能用 option database，且大小写敏感（`selectBackground` 的 B 必须大写）。运行时切主题还得用 `tk.eval` 直接刷。
6. **clam 主题的对勾是硬编码深色**，改不了。深色背景上让选中态也是深色 = 完全看不见；必须让选中时方框填高亮色。

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
build.bat              :: 打正式单文件 exe（dist\DufsGui.exe）
build_debug.bat        :: 诊断版：环境体检 + 控制台 + 抓输出（排错先跑它）
run_debug.bat          :: 只运行已有 exe 并抓取全部输出
python main.py         :: 源码直接跑
python -m unittest discover -s tests   :: 跑全部测试
```

打包开关（环境变量）：`DUFS_GUI_MODE=onefile|onedir`、`DUFS_GUI_CONSOLE=1`、`DUFS_GUI_COLLECT_TK=1`。

## 详细规则（按需 @引用）

- @docs/问题记录/ 目录（一坑一篇，含根因与修法）

## 平台限制

沙盒环境为 Linux 且**装不上 tkinter**，因此 GUI 的实际渲染、网页皮肤的实际观感**均未做过端到端验证**。已实证的是：打包流程、二进制释放与权限、命令行生成、崩溃落盘、自检输出。涉及视觉的判断一律以用户在 Windows 上的实测为准。
