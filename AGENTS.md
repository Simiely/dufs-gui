# AGENTS.md · dufs-gui 项目规则

> 📌 **文档基线**：2026-11-16（`f8ac311`）—— 按单项目规范 2.1.1 完成迁移 + README 门面化
> 更新文档/代码后请更新此行（日期 + 新 commit hash），并在 CHANGELOG 追加版本
>
> 本文件由 `tools/repo-kit/generate.py` 从 [`schema/agents.template.md`](schema/agents.template.md)
> 生成，**不要直接改这里**；改规则请改模板后跑 `python tools/repo-kit/generate.py --root . --write`。

本仓库是 **Dufs GUI**：给命令行工具 dufs 套一个 Windows 桌面外壳。回答相关问题前先读这份，
再读 [docs/index.md](docs/index.md)。

## 技术栈

- Python **3.9+**（打包推荐官方 CPython **3.12.x**；本机验证 **3.14.6**），仅标准库：tkinter / ttk
- 打包：PyInstaller **6.22.3**（钉在 `requirements.txt`，不要自动升级）
- 被封装对象：**dufs**（Rust 单文件服务器，以子进程方式拉起），版本固定 `v0.47.0`
- 网卡枚举：ctypes 调 Windows `GetAdaptersAddresses`，零第三方依赖，不解析本地化 `ipconfig`
- 网页皮肤：dufs 官方 assets v0.47.0 + CSS 覆盖层，零框架零 CDN

## 关键坑（改代码前必读）

1. **spec 里没有 `OS` 全局变量**。PyInstaller 只注入 `DISTPATH / HOMEPATH / SPEC / SPECPATH /
   specnm / workpath / WARNFILE`；判断系统必须 `import os` 后用 `os.name`。
   → [详情](docs/问题记录/问题：spec文件里OS变量未定义导致打包中断.md)
2. **`.bat` 必须存 GBK 或纯 ASCII**。中文 cmd 按 GBK 读批处理，UTF-8 中文会被当命令执行。
   → [详情](docs/问题记录/问题：UTF-8编码的中文bat被cmd当成命令执行.md)
3. **`--assets` 目录必须含 `index.html`**。dufs `sanitize_assets_path` 会 `bail!`；缺 css/js 可回退，缺 html 不行。
   → [详情](docs/问题记录/问题：dufs因assets目录缺少index.html拒绝启动.md)
4. **Windows 上必须清理子进程的 DLL 搜索路径**。bootloader 的 `SetDllDirectoryW` 会被子进程继承；
   `Popen` 前调 `SetDllDirectoryW(None)` 并从 PATH 剔除 `_MEIPASS`。
   → [详情](docs/问题记录/问题：子进程继承DLL搜索路径导致dufs无法启动.md)
5. **`ttk.Combobox` 的下拉列表是原生 `tk.Listbox`**。`ttk.Style` 无效，只能 option database，
   且大小写敏感（`selectBackground` 的 B 必须大写）。→ [详情](docs/问题记录/问题：ttk下拉列表与复选框在深色下不可见.md)
6. **勾选框不要再用 `element_create` 替换 indicator**。`core/theme.py` 的 `_install_check_indicator`
   已无调用点，现行实现是 `ThemedCheckbutton`（`tk.Checkbutton` + `indicatoron=False` + 自绘 16×16 图片）；
   自绘图片必须长期持有引用，否则被 GC 后变空白。
7. **网页皮肤必须用官方 assets，不要自造前端**。手写 html/js 等于猜 dufs 内部契约，结果是全功能失效且不报错。
   升级 dufs 后跑 `python tools/fetch_skin.py <版本>`。
8. **`ttk.Label` 不要写死 `wraplength`**。窗口宽度与可用宽度不一致时换行错乱；改为 `<Configure>` 按真实宽度自适应。
9. **网卡多选不要改回下拉单选**。UI 定稿是「查看网卡」模态弹窗（`ui/bindlist.py` 紧凑模式），
   ≤20 行一次显示、超出滚动，方向键/空格/Tab 可操作。
10. **不要把多地址改回单进程 `-b a,b`**。任一地址端口被占会让整进程失败；现方案是每地址一个进程 +
    同一 Job Object，实现单地址失败隔离。
11. **网卡排序只改 `core/netif.py`**。顺序：物理 IPv4（有线优先、私有网段优先）→ 其他 IPv4 →
    IPv6 → 不可用 → `0.0.0.0` → 回环（永远最后）。
12. **网页标题/favicon 只能改运行时副本**。`assets/` 由 `tools/fetch_skin.py` 覆盖生成，直接改会被冲掉；
    启动时复制到 `%APPDATA%\DufsGui\webui` 再注入（`core/webtweak.py`）。GUI 窗口标题固定「Dufs GUI」。
13. **网页顶栏是满宽 sticky bar，不要加 `max-width`**。要与 `.main` 的 1280px 容器共用左边线，
    只能改 `.head` 的左右 padding；≤640px 必须显式补 12px。
14. **主窗默认尺寸 = `minsize` 960×720**，不要改回 1040×780；先 `minsize` 后 `geometry`。
    改小前先量底线：最下缘「高级设置」695px、最右缘二维码按钮 927px。

## 约定

- UI 文案、代码注释、docstring 一律中文
- 界面**固定深色**（`core/theme.py`），不新增浅色分支或主题开关；原生控件必须显式配色
- 视觉按 macOS 深色 token（`DARK` / `SPACE` / `RADIUS` / `fonts()`）：8pt 栅格、控件高约 32px；
  **不引入第三方 UI 库，不用 emoji 当图标**
- 无口令共享是**合法路径且完全静默**：不弹窗、不写状态栏、不打警告；只在文档里说明
- 除 PyInstaller 外**不引入第三方运行时依赖**
- `bin/dufs.exe` 不入库，用 `tools/fetch_dufs.py` 获取
- `console=False` 时异常会静默消失，任何崩溃都要被 `core/crashlog.py` 捕获落盘
- 改 `core/__init__.py` 的 `APP_VERSION` 时，**同一个 PR** 要带上 README / 本文件 / 使用指南的版本表述

## 版本管理

版本号**唯一定义在 `core/__init__.py` 的 `APP_VERSION`**，界面标题与打包产物名从它派生。
**改版本只改这一处**；文档里不要写死具体版本号（用 `dist\DufsGui-v<版本>.exe` 这类占位写法）。

## 常用命令

```bat
python -m pip install -r requirements.txt   :: 构建依赖（PyInstaller 6.22.3）
build.bat              :: 打正式单文件 exe（dist\DufsGui-v<版本>.exe）
build_debug.bat        :: 诊断版：环境体检 + 控制台 + 抓输出
run_debug.bat          :: 只运行已有 exe 并抓取全部输出
python main.py         :: 源码直接跑
python -m unittest discover -s tests   :: 跑全部测试
```

文档检查（与 CI 同一套）：

```bash
python tools/repo-kit/check_repo.py --root .
python tools/repo-kit/generate.py --root . --check
pwsh tools/update-repo-kit.ps1 -Check
```

打包开关（环境变量）：`DUFS_GUI_MODE=onefile|onedir`、`DUFS_GUI_CONSOLE=1`、`DUFS_GUI_COLLECT_TK=1`。

## 当前规模

- 页面：12（critical=0）
- 按 type：explanation=9, how-to=2, reference=1
- 词表版本：2.5.2

## 边界

- 机器层只保结构、链接、生成物与真源联动；**语义真假靠人审**。
- 单实例只能挂一个共享目录（dufs 限制）；多网卡共享时每地址一个进程。
- **GUI 的视觉观感与网页皮肤的实际效果必须在真实 Windows 桌面上确认**，涉及视觉的判断以实机为准。
