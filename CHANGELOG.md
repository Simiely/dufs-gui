# CHANGELOG

本项目版本格式：`主版本.次版本.修订`，按版本倒序分节。
版本号唯一定义在 [`core/__init__.py`](core/__init__.py) 的 `APP_VERSION`，界面标题与打包产物名均从它派生，不要在多处改。

## [1.6.0] - 2026-11-03

### 修复：子进程控制台与删除确认（批次 6b）

- **dufs 不再留控制台窗口**：`core/server.py` 启动子进程时在 Windows 下固定
  `creationflags=CREATE_NO_WINDOW`，并补 `STARTUPINFO`（`STARTF_USESHOWWINDOW` +
  `SW_HIDE`）作为第二层保险；stdout/stderr 继续走 `PIPE` / `STDOUT` 并照旧写入运行日志。
  非 Windows 分支不变。新增 `tests/test_popen_flags.py` 断言上述参数。
- **「删除方案」改为模态确认框**：沿用自绘深色对话框（DWM 深色标题栏、圆角、危险色按钮），
  文案「删除方案「X」？」+「此操作不可撤销」，按钮「删除」（危险色）/「取消」；
  Esc 取消、Enter 默认落在「取消」；对话框为 grab 模态。保存/应用仍不弹确认。
  新增 `_key_results()` 与两条 UI 测试（取消不删、确认删除）。
- 对话框卡片不再 `expand`，并在屏幕外完成布局后再量高，短文案不再出现大片空白
  （删除确认框由 460×333 收口到 460×142）。

### 网页外观与圆角（批次 6）

- **网页标题可自定义（纠正批次 5 的误解）**：批次 5 误把「窗口标题」实现成了 GUI 窗口/
  任务栏标题，本轮已整项移除（GUI 窗口固定「Dufs GUI」，旧配置的 `window_title`
  载入时忽略）。真正可改的是**浏览器标签页标题**：标题来自皮肤 `index.js` 的 3 处
  ``document.title = `... - Dufs` ``，启动时把官方皮肤复制到 `%APPDATA%\DufsGui\webui`
  再注入标题常量，`--assets` 指向副本，**不修改 `tools/fetch_skin.py` 拉取的资产**。
  空值回落官方标题，最长 48 字。
- **浏览器标签页图标（favicon）**：皮肤 `index.html` 引用 `__ASSETS_PREFIX__favicon.ico`，
  dufs 从 `--assets` 目录返回该文件。高级设置可选本地 `.ico`（校验 ICO 头、≤2MB），
  写入同一运行时副本；「默认」恢复官方图标。两者都需勾选「网页美化界面」，下次开启共享生效。
- **二维码按钮改为文字 + 描边**：74×32 文字按钮「二维码」，hover/active/disabled 三态，
  与 32px 控件同高，不再使用不明显的图标。
- **圆角（先 spike 后落地）**：顶层窗口与对话框用 DWM `DWMWA_WINDOW_CORNER_PREFERENCE`
  （Win11 生效，Win10 静默保持直角、功能不受影响）；主按钮（开始/停止/二维码）与
  卡片/面板用纯标准库 4×4 超采样预渲染 PNG 角块（`ui/roundrect.py`，控件 8px /
  容器 12px，抗锯齿、圆角外与窗口背景同色）。输入框/下拉/滚动条/Treeview 保持直角，
  原因与 spike 失败证据见 `docs/round-report.md`。

### 界面与交互（批次 5）

- **深色自绘对话框**：新增 `ui/dialog.py`，保存方案、删除确认、端口/皮肤/导出提示、
  错误提示、二维码窗全部改为自绘 `tk.Toplevel`，套用固定深色 token 与 DWM 深色标题栏；
  仅「选择目录 / 选择 dufs.exe / 保存 PNG」保留原生 `filedialog`（系统 Shell 能力成本过高）。
- **失败详情按需显示**：无失败时整块隐藏（`grid_remove`，不占空白），有失败才出现并可
  展开/收起；成功启动或停止后自动收起。状态栏只保留「N 个中 M 个已启动 · K 个失败」摘要，
  逐地址失败长文案统一放在详情区，避免重复。
- **窗口标题自定义已移除**：见批次 6「网页标题可自定义（纠正批次 5 的误解）」，
  本轮不再提供 GUI 窗口/任务栏标题设置。
- **启停按钮移到标题行右侧**：「开启共享」实心蓝、运行中「停止」危险红，尺寸与 32px
  控件一致；原底部按钮区移除，最小窗口宽度下不挤压布局。
- **命令行改为日志**：删除界面上的等效命令文本框；启动时把每个地址的命令行以
  `[命令]` 前缀写入运行日志，口令保持 `user:***@/:rw` 脱敏，可直接复制。
- **共享链接二维码**：链接右侧新增按钮，打开深色二维码窗；内容取当前运行地址
  （未运行取配置地址），白底黑码，可复制链接或保存 PNG。新增 `core/qr.py`：
  纯标准库实现（QR Model 2、字节模式、L 级纠错、8 掩码惩罚选择、手写 PNG），
  不新增运行时依赖，冻结体积不受影响；矩阵已与 `qrcode` 参考实现逐位比对。
- **网卡 emoji 图标**：以太网 🔌 / Wi-Fi 📶 / VPN 🔒 / 虚拟 🧩 / 回环 🔁 / 通配 🌐，
  勾选列表与状态行统一使用；固定宽度图标列，避免双宽字符错位。

### 界面与构建调整（批次 4）

- **固定深色**：移除浅色主题、主题切换入口与 `dark_mode` 配置字段（旧配置中的该字段
  载入时忽略且不再回写）。垂直/水平 `ttk.Scrollbar`、下拉列表、Spinbox、Text、
  进度条、Treeview 与滚动区域统一按深色配色；日志区改为 `tk.Text + ttk.Scrollbar`，
  不再出现白色 trough/thumb/箭头。删除不再使用的 `core/app_state.py`。
- **主界面重排**：常用项（配置方案、共享目录、监听/端口、启停）集中在左列；
  路径前缀、网页端能力、隐藏规则、渲染、日志、HTTPS、口令、皮肤、dufs 程序
  全部收进「高级设置」弹窗。分组改为标题 + 分隔线，按钮宽度统一，
  底部命令预览与启停区留足高度，默认窗口尺寸下完整可见。
- **访问口令改为可选**：非回环监听 + 无口令不再拒绝启动，且**不产生任何提示**
  （无弹窗、状态栏、日志或提醒条），与设口令路径完全一致；口令填了就生效，
  不填即为匿名访问。仅文档客观描述该行为。
- **构建一条命令**：`build.bat` 精简为 5 步（环境检查 → 自动下载 dufs →
  PyInstaller 检查 → 打包 → selftest + SHA256SUMS），缺依赖时打印一行可复制的
  安装命令，不再需要手动准备二进制；README「快速开始」压缩为最短路径。
- **界面改为 macOS 深色设计语言**：`core/theme.py` 引入设计 token（背景 `#1e1e1e`、
  面板 `#232325`、控件 `#2c2c2e`、边框 `#3a3a3c`、次要文字 `#8e8e93`、强调蓝 `#0a84ff`、
  危险红 `#ff453a`），8pt 栅格、约 32px 控件高、标题/正文/次要三级字号；卡片用
  1px 低对比描边 + 背景色差分层，高级设置改为卡片分组 + 可滚动内容区 + 固定底部操作条。
  Tk 无法实现真实圆角/毛玻璃/SF 字体/连续动画，未为此堆自绘或引入第三方 UI 库。
- **监听地址排序与默认值**：新增 `core/netif.py`，用 ctypes 调 Windows
  `GetAdaptersAddresses` 枚举（不解析本地化 `ipconfig`）。顺序为物理网卡 IPv4
  （有线优先、私有网段优先）→ 其他 IPv4（虚拟/VPN）→ IPv6 → 不可用 → `0.0.0.0` → 回环；
  `127.0.0.1` 永远最后，文案「仅本机 · 127.0.0.1」。默认选第一块已连接非回环网卡
  （只有回环可用时才默认回环）；已保存且仍存在的选择保持不变，失效地址提示并跳过。
- **多网卡同时共享**：主界面监听地址由下拉单选改为**固定高度勾选列表**
  （逐行「勾选框 + 网卡名 + IP + 状态」，5 行可见、超出滚动、方向键/空格/Tab 可操作）。
  每个地址一个 dufs 进程，共用同一端口/目录/参数，并全部加入同一个 Job Object；
  状态区按地址显示运行状态与 URL，部分失败汇总为「N 个中 M 个已启动」并可展开详情；
  端口占用只影响该地址。配置新增 `binds`（旧 `bind` 载入时自动升级），
  `all_loopback()` 仅在全部地址均为回环时为真。
- 测试同步：主题用例改为断言固定深色与滚动条配色；无口令共享用例改为断言
  启动成功且无任何提示输出。

### 构建发布与文档（批次 3）

- `requirements.txt` 把 PyInstaller 钉到 **6.22.3**；`build.bat` / `build_debug.bat` /
  `build.sh` 缺包时不再自动 `pip install -U`，改为提示按 requirements 安装。
- 新增 `tools/build_info.py`：打包后生成 `dist/BUILD-INFO.txt`（Python / PyInstaller /
  Tk / dufs / 皮肤 / Git 状态）与 `dist/SHA256SUMS`（exe + 关键构建输入）。
- 新增 `licenses/`：dufs v0.47.0 上游 MIT / Apache-2.0 许可原文与来源说明，
  由 spec 打进包内；`--selftest` 会列出 `licenses/` 内容。
- CI 保留单测 job，新增 `build-check` job：锁定依赖 → onefile → `--selftest`
  → 断言产物非空 → 校验 SHA256SUMS；不上传、不发布。
- README 补安装方式、首次启动预期、SmartScreen / 杀软 / 启动慢 / 端口占用 FAQ、
  配置与日志位置，并修正 `%APPDATA%` 与 `%LOCALAPPDATA%` 的混淆。
- 文档不再硬编码测试数量，改为以测试输出 / CI 日志为准。

### 重构：拆分界面与启动决策，配置 schema 版本化

- `app.py` 从 1070 行降到约 540 行：主窗口布局、表单映射、高级设置弹窗拆到 `ui/`；
  启动决策抽为 `core/launch.py` 的 `build_launch_plan(cfg)`（不弹窗、不启动进程）。
- 新增 `core/runtime.py`：统一 dufs 二进制定位、版本探测与进程状态，
  消除 `app.py` 中分散的 `dufs_path` / `proc` 双状态。
- 配置新增 `config_version`（当前 v2）：无版本号的旧配置载入即迁移；
  解析失败或版本过新时备份为 `config.bad.json` 并在日志明确提示；
  保存改为临时文件 + `os.replace` 原子写；`from_dict` 逐字段类型校验。
- 新增 10 项测试（启动计划表驱动、配置迁移、坏配置恢复、原子写），
  全量 127 项（126 通过、1 项 jsdom E2E 跳过）。
- PyInstaller onefile + `--selftest` 冒烟通过，冻结环境 GUI 启动验证通过。

## [1.5.0] - 2026-11-02

### 改进：网页皮肤不再"只是官方默认换色"

用户反馈："主题加载了，但看起来还是默认主题" —— 这个观察完全正确。
v1.3.0 起为修复功能失效改用官方 assets，但只覆盖了 CSS 颜色变量，
布局、间距、控件形态全是官方原样，视觉上与 dufs 默认界面几乎无差别。

现追加**视觉增强层**：仍然只改 CSS，不动 HTML / JS，
因此上传 / 下载 / 预览 / 编辑 / 搜索 / 权限等交互继续由官方 JS 保证。

改造内容：

- 顶部渐变装饰条 + 毛玻璃吸顶栏
- 面包屑胶囊化（hover 高亮）
- 工具按钮圆形化 + hover 背景
- 文件表格卡片化（行间距、圆角、边框、hover 抬升）
- 搜索框胶囊化 + 聚焦发光
- 空文件夹大图标提示
- 编辑器圆角等宽字体
- 自定义滚动条与选区配色
- 窄屏适配

### 其他

- `tools/fetch_skin.py` 同步纳入视觉增强，重新抓取可复现同样结果（实测 diff 仅差一个空行）
- 新增测试：视觉增强必须真实存在（卡片化 / 圆角 / 渐变 / 毛玻璃），
  且官方 `index.js` 必须原样未改
- 测试 68 -> 70 项

## [1.4.0] - 2026-11-02

### 修复：真正的根因 —— 历史污染的配置让 --assets 从未入参

现象是"目录核验通过，但皮肤不生效"。排查方向一度以为是占位符缺失，
但核验确认官方 index.html 里 `__ASSETS_PREFIX__` ×3、`__INDEX_DATA__` ×1
全部齐备，占位符不是原因。

真正原因：**`--assets` 只在 `custom_ui` 为真时才加入命令行**
（`core/config.py` 的 `to_args()`），而用户 config.json 里存着 `custom_ui: false`。

那个 false 是 v1.2.1 的"皮肤启动失败自动降级"写进盘的。
v1.2.2 已让降级不再写盘，但**已经存在的旧值不会自己消失** ——
于是出现了"代码修好了、打包也修好了，皮肤却始终不生效"。

同时暴露一个设计缺陷：v1.3.1 加的"网页皮肤：核验通过"只验证**目录是否存在**，
完全没检查 `--assets` 有没有真的进命令行，日志因此自相矛盾，严重误导定位。

### 改动

- **日志拆成两步，不再混淆**：
  - `网页皮肤：目录核验通过 <路径>（N 个文件）` —— 只说文件在不在
  - `网页皮肤：已加入 --assets → <路径>` —— 说真的会生效
  - 或 `网页皮肤：本次未传 --assets，网页将是 dufs 默认界面` + 原因与配置文件路径
- **载入时自愈**：`ServerConfig.from_dict()` 把无标记的历史 `false` 恢复为 `True`
- **尊重用户选择**：主动取消勾选时写入 `_user_set_custom_ui` 标记，
  带标记的值不会被自愈覆盖（重新勾选后标记自动消失）

### 测试

- 新增：污染值被自愈 / 用户关闭被尊重 / 关闭写标记 / `--assets` 随 custom_ui 入参
- 修正 `test_persisted_false_overrides_default`：它断言的正是旧的污染行为，已反转
- 测试 65 -> 68 项

## [1.3.2] - 2026-11-02

### 修复：`AttributeError: '_tkinter.tkapp' object has no attribute 'assets_dir'`

皮肤核验里写了 `self.assets_dir`，但这个类里**根本没有这个属性** ——
实际的皮肤目录变量是 `self.v_assets_dir`（一个 `tk.StringVar`）。

`tk.Tk.__getattr__` 会转到底层 `tkapp` 上找，找不到就抛上述异常；
而它被 `try/except` 吞成一句"核验异常"，看起来像环境问题，实际是拼写错误。

- 改走统一入口 `skin_dir()`：外部目录优先，否则内置皮肤目录
- 异常日志带出出错文件与行号，不再只留一句 `AttributeError`
- 新增 `tests/test_attr_sanity.py`：AST 静态比对"用到的 self 属性"与
  "赋值过的 self 属性"，把这类拼写错误在测试阶段拦下

验证：把 bug 注入回去后该测试立刻失败（报出 `['assets_dir']`），还原后通过。

### 测试

- 新增 `AttrSanityTest`（含 Tk 内置方法白名单，避免误报）
- 测试 63 -> 65 项

## [1.3.1] - 2026-11-02

### 修复：onedir 模式下皮肤路径算错

`resource_dir()` 在 `frozen` 为真但没有 `_MEIPASS` 时（onedir 的典型情形）
回退到了**源码目录**，而不是 exe 所在目录 —— 皮肤必然找不到。

按官方手册 §3.4 的二级回退修正：

```python
if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
```

### 改进：不再静默回退

手册 §3.3 强调：若不显式核验 `index.html`，dufs 会**静默回退内置界面**，
表现为"皮肤没生效"且日志毫无线索 —— 这正是本项目反复踩坑的根源。

- 新增 `dufsbin.verify_assets_dir()`：核验目录并给出可读结论
  （缺 index.html 时会同时列出目录内现有文件）
- 启动日志改为：`网页皮肤：核验通过 <路径>（N 个文件：…）`
  或 `网页皮肤：不可用 —— <原因>`
- 官方限制提示：serve-path 传单个文件时 index.html 模板被绕过、皮肤不生效
- `--selftest` 新增 `resource_dir` / `验证结果` / `目录内容` 三行，
  可直接看到 dufs 实际会拿到哪个目录、里面有什么

### 测试

- 新增 `ResourceDirTest`（onedir / onefile / 开发三种环境）与 `AssetsVerifyTest`
- 测试 56 -> 63 项

## [1.3.0] - 2026-11-02

### 重构：网页皮肤改用官方方案，彻底解决"无法上传 / 下载 / 预览"

**此前一直在用错误方案**：手写了一整套 index.html + index.js + index.css，
等于在猜 dufs 的内部契约 —— 数据节点写法、IndexData 字段、DOM class、权限判定。
任何一处对不上就表现为"上传下载预览全部失效"，而 dufs 端不报错，极难定位。

**官方方案**（dufs README "Customize UI"）：

> If you only need to make slight adjustments to the current UI, you copy
> dufs's assets directory and modify it accordingly.

现改为：完整搬运官方 assets，**只覆盖 index.css 里的 CSS 变量**。
所有交互逻辑（上传 / 下载 / 预览 / 编辑 / 搜索 / 权限显隐）全部由官方 JS 提供。

### 关键发现

1. 官方数据节点是 `<template id="index-data">`，**不是** div —— 之前结构完全不同
2. 官方 CSS 已用 CSS 变量（`--bg-primary` 等），且**自带 `@media (prefers-color-scheme: dark)`
   完整暗色配色**。所以只需要改变量，不需要另写布局
3. 官方 assets 中 index.css / index.js / favicon.ico 缺失会自动回退内置版本，
   但 index.html 必须存在；因此 HTML 与 JS 必须**同版本**随包提供，不能只提供其一

### 改动

- `assets/`：官方 v0.47.0 的 index.html / index.js / favicon.ico（原样）+ index.css（官方 + 变量覆盖）+ ASSETS_VERSION
- 新增 `tools/fetch_skin.py`：按版本号重新抓取官方 assets 并生成皮肤，便于随 dufs 升级
- 启动时若皮肤版本与 dufs 版本不一致会提示重新生成
- `DufsGui.spec` 打包清单补齐为 5 个文件

### 验证（jsdom 真实执行官方 index.js，13 项全绿）

```
✅ 使用官方结构 template#index-data
✅ 文件列表已渲染
✅ 链接指向正确文件
✅ 下载控件已启用（无 hidden）
✅ 上传控件已启用（无 hidden）
✅ 上传发出 PUT 请求
✅ 编辑器元素存在（支撑预览/编辑）
```

### 测试

- 替换旧的自包含断言（与官方方案冲突）为官方结构断言
- 测试 55 -> 56 项

## [1.2.3] - 2026-11-02

### 修复：网页上传 / 下载全部失效（表格空白）

用 jsdom 真实执行皮肤脚本后定位到的根因：**`__INDEX_DATA__` 在文件里出现了 3 次，
真正的数据节点排在第 3 位**（前两处都在注释里）。

只要替换实现只处理第一次出现，div 里就剩下字面量 `__INDEX_DATA__`，
`atob()` 抛 "invalid characters" → 脚本 return → 表格空白、
下载链接和上传按钮全部不绑定。这与"上传下载都失败"的现象完全吻合。

修复后实测（jsdom，单一替换与全局替换两种情形均通过）：

```
✅ 单次替换即可正常渲染      行数=2  下载链接=1
✅ 全局替换正常渲染
✅ kind=index / kind=Weird 时仍渲染
✅ 上传发出 PUT 且 URL 正确  /%E6%88%91%E7%9A%84%20%E6%8A%A5%E5%91%8A.pdf
```

### 改动

- `index.html`：占位符全文唯一，且就在 `#index-data` 节点内
- 数据解析加固：`kind` 大小写不敏感；只要带 `paths` 数组就按目录列表渲染，不再硬性 fatal
- 失败提示可读化：未拿到数据时明确说明，并打印收到的原始片段（原先只有 "invalid characters"）
- 用 `<link rel="icon" href="data:,">` 消除 `GET /favicon.ico` 404
- 新增 `tools/check_skin.js`（jsdom 端到端验证）+ `tests/test_skin.py`，10 项断言

### 测试

- 测试 53 -> 55 项

## [1.2.2] - 2026-11-02

### 修复：真正的原因 —— 持久化配置污染

前几轮改了内联、改了打包路径，都不是根因。真正原因是：

`%APPDATA%\DufsGui\config.json` 里存着 `custom_ui: false`，
而 `ServerConfig.from_dict()` 会用配置里的值**覆盖** dataclass 的默认值 `True`。
所以代码改对了、打包也对了，启动时仍从配置读回 false，`--assets` 永远不加。

那个 false 从哪来：旧版在"皮肤启动失败自动降级"时执行了
`v_custom_ui.set(False)` + `_save()`，**一次失败 = 永久关闭**。

**改动：**

- 自动降级改为**只改内存、不写盘**，一次启动失败不再永久关闭皮肤
- 启动时日志明确区分三种状态：
  `未启用（配置中 custom_ui=false）` / `已勾选但找不到内置皮肤` / `内置皮肤就绪`
  并在未启用时提示恢复手段（勾选开关，或删除 config.json）
- `webui_dir()` 移除无用的 `webui/` fallback 分支（打包从未产出该目录）

### 测试

- 新增 `SkinConfigTest`：配置 false 覆盖默认值 / 降级不得写盘 / 只认 assets 目录
- 测试 50 -> 53 项

## [1.2.1] - 2026-11-02

### 修复：打包后网页皮肤不生效（页面仍是 dufs 默认样式）

根因在打包配置，不在代码逻辑：`assets/` 目录被按文件名平铺进归档的 `webui/` 前缀下，
而运行时 `webui_dir()` 只查找 `assets/` 前缀，路径对不上，导致 `--assets` 静默失效。

dufs 对 `--assets` 的处理是：目录不存在或不含 `index.html` 时不报错，
而是**静默回退到内置默认界面**——所以此前毫无报错迹象，只能从日志判断。

**改动：**

- `DufsGui.spec`：改为按目录整体打包（`datas.append((WEBUI, "assets"))`），保证归档内路径为 `assets/index.html`，与 `webui_dir()` 一致
- 新增 `test_packaged_skin_resolves_under_meipass`：用 monkeypatch 模拟 PyInstaller 的 `_MEIPASS` 环境，验证打包后皮肤可被定位
- `app.py` 皮肤生效日志改为打印实际生效路径，便于排错
- `core/crashlog.py` 环境自检新增 `webui_dir` 与 `webui html` 两行

### 验证

用 PyInstaller 的 `CArchiveReader` 实测确认 `assets/index.html` 已在归档内。

## [1.2.0] - 2026-11-02（commit `6c7fa01`）

### 修复：网页皮肤始终是 dufs 默认样式

根因是**资源前缀占位符各版本写法不一致**：

| 来源 | 写法 |
|---|---|
| crates/lib.rs 记载 | `__ASSERTS_PREFIX__`（多一个 S） |
| README / SelfHost Hub | `__ASSETS_PREFIX__` |

皮肤原本用 `<link href="__ASSETS_PREFIX__index.css">` 引用外部资源。
一旦 dufs 只认另一种写法，替换就不会发生，浏览器去请求字面量路径 → 404 →
样式与脚本全部丢失，页面退回无样式状态。

**解决：CSS 与 JS 全部内联进 index.html**，彻底不依赖该占位符，
只剩 `__INDEX_DATA__` 一个（各版本写法一致）。

### 变更

- `assets/index.html` 改为自包含单文件（21.8 KB），删除外部 index.css / index.js
- **皮肤默认启用**（原为默认关闭）：index.html 自包含且必然存在，不会拖垮启动，
  且保留 `--assets` 失败自动降级
- 启动时日志记录实际状态：`网页皮肤：已启用自定义界面` / `未启用，使用 dufs 默认界面`
- 「打开网页」URL 追加时间戳 fragment，避开浏览器缓存（fragment 不发给服务端，
  不影响 dufs 对 `?q=` / `?zip` 等参数的解析）

### 测试

- 新增：皮肤必须自包含（不得有 `<link>` / `script src` / `href="__`）
- 默认开关断言随行为反转
- 测试 48 -> 49 项

## [1.1.2] - 2026-11-02（commit `9f794d2`）

### 修复（前两版"改了但没变化"的真正原因）

- **弹窗尺寸改自适应后反而更糟**：`winfo_reqheight()` 在窗口 `withdraw()` 状态下
  不计算子控件几何，实测常返回 1，算出高度 `max(420, ...)` = 420，比原来写死的
  560 还小 —— 裁得更狠。改为**固定 760 高度 + 滚动兜底**，不再依赖测量
- **复选框改用 tk.Checkbutton**：ttk 的 `indicatorcolor` 与 `element_create` 替换指示器
  都会**静默失效**（不报错、就是没效果），这是"修了却看不到变化"的根因。
  改为 `tk.Checkbutton + indicatoron=False + image/selectimage` 自绘图片
  （Stack Overflow #58559865 已采纳方案），完全绕开 ttk 主题机制
- **对比度不足**：原选中底 `#4f9cf9` 配白勾仅 2.82:1（WCAG 要求 ≥3），
  未选中描边 `#333a45` 配面板仅 1.31:1（等于隐形）。
  改为 `check_on: #1f6feb`（4.63:1）、`check_border: #8b96a5`（5.0:1）
- **主题是否生效无法确认**：切换主题后在日志区写一行
  `主题已应用：深色（ttk 主题 clam）`，可直接核对

### 流程修复

- `build.bat` / `build_debug.bat` 先删 `dist\` 和 `build\`，杜绝双击到旧 exe
- 新增回归测试：强制所有 `.bat` 必须是纯 ASCII（防止中文注释再次混入）

### 测试

- 新增：复选框非 ttk / 使用自绘图 / **对比度达 WCAG 3:1** / 弹窗不依赖实测高度 / bat 纯 ASCII
- 测试 44 -> 48 项

## [1.1.1] - 2026-11-02（commit `367b6c4`）

### 修复

- **等效命令显示被截断**：预览标签写死 `wraplength=760`，而窗口 1020 宽、
  还要放按钮 —— 换行位置与实际宽度不符，命令被截成 `--e --allow-archive` 这类怪样子。
  改为按标签真实宽度自适应
- **复选框勾选依然看不见**：`indicatorcolor` 在部分平台静默失效（不报错、就是没效果）。
  改为**自绘 16x16 位图指示器**（`element_create` 替换 `Checkbutton.indicator`），
  颜色完全自控，任何主题下都必然可见：未选中深底描边，选中蓝底白勾
- **主题切换时高级设置弹窗不跟随**：Canvas 是原生 tk 控件，`ttk.Style` 管不到。
  切换主题时一并刷新弹窗与它的画布底色

### 测试

- 新增 3 项源码级回归（不写死 wraplength / 走自绘指示器 / 对勾像素不越界）
- 测试 41 -> 44 项

## [1.1.0] - 2026-11-02（commit `e7d3c66`）

### 变更

- **版本号收归单一真源**：`core/__init__.py` 的 `APP_VERSION`。
  界面标题、打包产物名（`DufsGui-v1.1.0.exe`）全部从它派生，避免多处不同步
- **打包产物名带版本号**：`dist\DufsGui-v1.1.0.exe`，便于区分新旧版本
- `build.bat` / `build_debug.bat` 改为通配定位产物，自动适配带版本号的 exe

### 文档

- 按 knowledge-base 单项目规范建立四件套（README / AGENTS / DEVELOPMENT / CHANGELOG）
- README 原 252 行超 150 行阈值 → 精简为门面 + 索引，详情移入 `docs/使用指南.md`
- 新增 `docs/问题记录/` 六篇，一坑一篇

## [1.0.0] - 2026-11-02（commit `e4b8cac`）

首个可用版本。完成四件套（README / AGENTS / DEVELOPMENT / CHANGELOG）重写。

### 新增

- 单站点共享配置：目录、监听地址（自动列出本机 IP）、端口、URL 路径前缀
- 网页端能力勾选：上传 / 删除 / 搜索 / 打包下载 / 符号链接 / CORS
- 配置方案管理：多套「目录 + 端口 + 能力」保存与切换，最近目录记忆
- 深色 / 浅色主题，Windows 标题栏跟随
- 服务状态、实时日志（清空 / 导出）、打开网页、复制地址
- 底部实时显示等效 dufs 命令行
- 崩溃落盘（`%LOCALAPPDATA%\DufsGui\crash.log`）与 `--selftest` 自检
- 一键打包脚本：`build.bat`（单文件）、`build_debug.bat`（诊断）、`run_debug.bat`
- 自研网页皮肤 `assets/`（默认关闭，可指向第三方皮肤包）
- 37 项单元测试

### 修复

- spec 中 `OS` 全局变量不存在导致打包中断 → 改用 `import os`
- 所有 bat 改为纯 ASCII，解决中文 UTF-8 被 cmd 当命令执行
- dufs 因 `--assets` 目录缺 `index.html` 拒绝启动 → 补齐三件套 + 三重校验 + 自动降级
- 子进程继承 bootloader 的 DLL 搜索路径 → `Popen` 前清理
- 下拉列表 / 复选框在深色下不可见 → 分别按原生 Listbox 与 clam 硬编码对勾处理
- 弹窗写死尺寸导致内容裁切 → 按内容实测高度 + 可滚动
- 移除重复的 `ui_queue` 残留引用导致的 `AttributeError`

### 已知限制

- 单实例只能挂一个共享目录（dufs 限制）
- dufs 单文件模式不适用自研网页皮肤
- Linux 沙盒无 tkinter，GUI 渲染与网页观感未经端到端验证
