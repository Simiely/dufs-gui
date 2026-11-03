# AGENTS.md · 项目规则

> 📌 **代码基线**：2026-11-03 v1.6.1（批次 8：辅助状态只显 IP + 网卡勾选模态弹窗）
> 后续更新请追加新提交并在 CHANGELOG 记录；**不要引用已不在仓库历史中的 commit**。

## 技术栈

- Python **3.9+**（打包推荐官方 CPython **3.12.x**；本机验证 **3.14.6**），仅标准库：tkinter / ttk
- 打包：PyInstaller **6.22.3**（版本钉在 `requirements.txt`，不要自动升级）
- 被封装对象：**dufs**（Rust 编写的单文件服务器，以子进程方式拉起）
- 网卡枚举：ctypes 调 Windows `GetAdaptersAddresses`（iphlpapi），**零第三方依赖**，
  不解析本地化的 `ipconfig` 文本
- 多地址共享：每个绑定地址一个 dufs 进程，共用端口/目录/参数，全部加入同一个 Job Object
- 网页皮肤：dufs 官方 assets v0.47.0 + CSS 覆盖层，零框架零 CDN

## 关键坑（改代码前必读）

1. **spec 里没有 `OS` 全局变量**。PyInstaller 的全局变量只有 `DISTPATH / HOMEPATH / SPEC / SPECPATH / specnm / workpath / WARNFILE`。判断系统必须 `import os` 后用 `os.name`。写 `OS == "nt"` 会 NameError 中断打包。
2. **`.bat` 必须存成 GBK 或纯 ASCII**。Windows 中文 cmd 按 GBK 读批处理，UTF-8 中文会被解成乱码并被当成命令执行（满屏"不是内部或外部命令"）。本项目所有 bat 用**纯 ASCII 英文**。
3. **`--assets` 目录必须含 `index.html`**。dufs `src/args.rs` 的 `sanitize_assets_path` 会 `bail!`。只放 CSS 会让 dufs 拒绝启动。
4. **Windows 上必须清理子进程的 DLL 搜索路径**。bootloader 用 `SetDllDirectoryW` 指向 `_MEIPASS`，该设置**被子进程继承**，外部 dufs.exe 可能加载到不兼容 DLL。`Popen` 前调 `SetDllDirectoryW(None)` 并从 PATH 剔除 `_MEIPASS`。
5. **ttk.Combobox 的下拉列表是原生 tk.Listbox，不是 ttk 控件**。`ttk.Style` 无效，只能用 option database，且大小写敏感（`selectBackground` 的 B 必须大写）。本应用固定深色，初始化时用 `tk.eval` 直接刷一次已存在列表即可。
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
9. **网卡多选不要改回下拉单选**。UI 定稿是「查看网卡」模态弹窗（`ui/bindlist.py` 紧凑模式），
   ≤20 行一次显示、>20 行封顶 20 行滚动（小屏按工作区高度兜底），无地址网卡过滤掉，
   方向键/空格/Tab 可操作；确定生效，标题栏 × 与 Esc = 取消；
   下拉单选框会让"同时共享多块网卡"不可见。
10. **不要把多地址改回单进程 `-b a,b`**。dufs 0.47 支持多绑定，但任一地址端口被占会让
    整个进程失败，无法做到单地址失败隔离；现方案是每地址一个进程 + 同一 Job Object。
11. **网卡排序只改 `core/netif.py`**。顺序为物理网卡 IPv4（有线优先、私有网段优先）→
    其他 IPv4（虚拟/VPN）→ IPv6 → 不可用 → `0.0.0.0` → 回环；`127.0.0.1` 永远最后，
    默认选中第一块已连接非回环网卡（只有回环可用时才默认回环）。
12. **网页标题/favicon 只能改运行时副本**。`assets/` 由 `tools/fetch_skin.py` 覆盖生成，
    直接改会被下次拉取冲掉。标题来自 `index.js` 的 3 处 ``document.title = `... - Dufs` ``，
    图标来自 `index.html` 引用的 `favicon.ico`；启动时复制到 `%APPDATA%\DufsGui\webui`
    再注入（`core/webtweak.py`），`--assets` 指向副本。GUI 窗口标题固定「Dufs GUI」，
    不要和网页标题混为一谈。

## 约定

- UI 文案中文；代码注释中文；docstring 中文
- 界面**固定深色**（`core/theme.py`），不要新增浅色分支、主题开关或隐藏状态；
  滚动条、下拉列表、Spinbox、Text 等原生/半原生控件必须显式配色，禁止残留白色部件
- 视觉按 macOS 深色 token（`DARK` / `SPACE` / `RADIUS` / `fonts()`）：背景色差分层次、
  8pt 栅格、控件高约 32px、三级字号；**不引入第三方 UI 库，不用 emoji 当图标**。
  Tk 控件本身没有圆角：需要时用 `ui/roundrect.py` 的预渲染角块（纯标准库，控件 8px /
  容器 12px，圆角外与底层同色），窗口/对话框圆角走 DWM（Win11 生效，Win10 降级直角）；
  不要用 `SetWindowRgn`（无抗锯齿，spike 已否决），也不要给做不到的控件加假边框
- 无口令共享是**合法路径且完全静默**：不弹窗、不写状态栏、不打警告日志；只在文档描述
  "不填口令即为匿名访问"，不要在任何地方加运行时提醒
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
python -m pip install -r requirements.txt   :: 构建依赖（PyInstaller 6.22.3）
build.bat              :: 打正式单文件 exe（dist\DufsGui-v1.6.1.exe）
build_debug.bat        :: 诊断版：环境体检 + 控制台 + 抓输出（排错先跑它）
run_debug.bat          :: 只运行已有 exe 并抓取全部输出
python main.py         :: 源码直接跑
python -m unittest discover -s tests   :: 跑全部测试（数量以输出为准，jsdom E2E 缺依赖时跳过）
```

Windows CI：`.github/workflows/windows-ci.yml`，单测矩阵 Python 3.9 / 3.12，
另有 `build-check` job（Python 3.14，锁定依赖 → onefile → `--selftest` → 校验 SHA256SUMS）。
CI 不发布；runner 无桌面，build-check 不启动 GUI。

打包开关（环境变量）：`DUFS_GUI_MODE=onefile|onedir`、`DUFS_GUI_CONSOLE=1`、`DUFS_GUI_COLLECT_TK=1`。

## 详细规则（按需 @引用）

- @docs/问题记录/ 目录（一坑一篇，含根因与修法）

## 平台限制

Windows CI 已覆盖单测（Python 3.9 / 3.12；jsdom 皮肤 E2E 自动跳过）与冻结产物
`--selftest` / SHA256SUMS 校验，并在本机验证过真实 Tk 窗口构造与端口输入。
**GUI 的视觉观感、网页皮肤的实际效果仍需在真实 Windows 桌面上确认**，
涉及视觉的判断一律以实机结果为准。
