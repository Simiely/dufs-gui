# 第 6 批改造报告（v1.5.0 → v1.6.0）

日期：2026-11-03 · 分支 `fix/p0-hardening` · 基线提交 `9d6b23b`

本轮把「网页标题、站点图标、文字二维码按钮、全界面圆角、版本号、左栏地址布局」一并做完。
结论先说：**五项全部落地**；无法真圆角的 5 类系统原生元素在下方单独列出，没有用假边框冒充。

## 1. 网页标题（浏览器标签页，不是 GUI 窗口标题）

来源证据：

- `assets/index.html` **没有 `<title>`**（只有 `<link rel="icon" href="__ASSETS_PREFIX__favicon.ico">`）。
- 标题由 `assets/index.js` 三处 `document.title` 决定：`Index of … - Dufs`、`Edit … - Dufs`、`View … - Dufs`。
- 关闭「网页皮肤」（`custom_ui=false`，不传 `--assets`）时，dufs 用编译进二进制里的官方 `index.js`，
  标题回到 `Index of <路径> - Dufs`，**GUI 无法修改**。

做法：启动时把皮肤复制到 `%APPDATA%\DufsGui\webui`（`core/webtweak.py::prepare_overlay`），
在副本 `index.js` 的三处标题前注入 `__DUFS_GUI_TITLE ||`，`--assets` 指向副本；
仓库内 `assets/` 保持官方原样（哈希不变）。高级设置新增「网页标题」输入框（留空 = 官方文案），
**GUI 窗口标题已恢复固定「Dufs GUI」**，两者不再混淆。

验证：`web-evidence.json`（`repo_assets_unchanged=true`、overlay `js_title_line` 含注入常量）；
`web-title-before/after.png` 为浏览器标签栏实拍。

## 2. 站点 favicon

- `assets/index.html` 里 `favicon.ico` 走 `__ASSETS_PREFIX__`，即由 `--assets` 目录提供；
- 不传 `--assets` 时 dufs 返回内置图标（实测 SHA256 `092a155f…`，9277 B，与仓库 `assets/favicon.ico` 相同）。
- 因此**只要皮肤开启就可替换**；副本里换掉 `favicon.ico` 即可，无需改二进制。

做法：高级设置「站点图标」支持选择 `.ico`（校验文件头与尺寸）与「恢复默认」；启动时复制到副本，
失败自动回退默认并写日志。验证：`favicon_matches=true`（自定义图标 203 B 与服务器返回一致），
`web-favicon-before/after-zoom.png` 为浏览器标签实拍；皮肤关闭时明说不可改（设置项灰度/提示）。

## 3. 二维码按钮

`ui/layout.py` 的 `btn_qr`：**文字「二维码」+ 1px 描边**（无图标、无填充），74×32、圆角 8px；
normal/hover/pressed/disabled 四套预渲染图，hover 描边提亮、pressed 底色下沉，点击仍走原 `_open_qr`。
4× 特写：`round5-05c-qr-button-4x.png`。

## 4. 圆角与逐元素审计

统一管线：`core/raster.py` 4×4 超采样 + zlib/struct 手写 RGBA PNG → `PhotoImage`；
`ui/roundrect.py` 把整块拆成「4 角图 + 3 直边矩形」（9 宫格），任意宽高免重光栅化。
圆角外像素与**当前背景色**混合（卡片 `#232325`、窗口 `#1e1e1e`），无浅色缺口/灰边；
缓存键 `(尺寸, 半径, 状态色, 主题, 透明)`，不每帧重算。

### 审计表

| 元素 | 半径 | 状态 |
| --- | --- | --- |
| 主窗口（Win11 DWM `DWMWA_WINDOW_CORNER_PREFERENCE=2`） | 12 | 已圆（`round5-02b-window-corner-4x.png`）；Win10 静默直角 |
| 高级设置 / 二维码 / 确认对话框窗口 | 12 | 已圆（`round5-06d-qr-window-corner-4x.png`） |
| 卡片/面板：共享目录、共享地址、配置方案、服务状态、运行日志、对话框内卡片 | 10 | 已圆（`round5-04c-advanced-fields-4x.png`） |
| 主按钮：开启共享 / 停止 | 8 | 已圆，四态（`round5-01e-start-button-4x.png`） |
| 次级按钮：二维码/打开网页/复制地址/选择…/检测/保存/删除/高级设置…/对话框按钮 | 8 | 已圆 |
| 24px 小按钮：全部 / 清空 / 导出… / 展开 | 6 | 已圆 |
| 输入框外框：共享目录、端口、高级设置各字段、二维码链接 | 8 | 已圆；Focus 描边 accent（`round5-02d-entry-focus-4x.png`） |
| 下拉框外框：方案、渲染模式 | 8 | 已圆 |
| 下拉弹层（tk.Listbox） | — | **未圆，见清单** |
| 复选框指示器 | 4 | 已圆（透明角块叠行底色，勾选态画对勾） |
| 地址列表卡片 / 每行 / hover 行 | 10 / 6 | 已圆（`round5-01f-address-row-4x.png`） |
| 网卡折叠摘要行 | — | 无矩形底（纯弱化文字），不适用 |
| 展开区：明细头「全部」/ 勾选行 hover+focus | 6 | 已圆（`round5-02b-bind-detail-4x.png`） |
| 日志区外框（well） | 8 | 已圆；Text 本体直角，被 ≥4px 留白包住 |
| 日志垂直/水平滚动条 | thumb 圆角 | 自绘 `RoundScrollbar`，宽 10（`round5-01g-log-scrollbar-4x.png`） |
| 状态区（dot + 文案 + 二维码） | 10（所在卡片） | 已圆 |
| 失败详情面板 / 展开按钮 | 8 / 6 | 已圆 |
| 二维码白色底 | 8 | 已圆（`round5-06c-qr-corner-4x.png`） |
| 自绘 chips / 徽标 | — | 本界面不存在 |

### 保持直角清单（不可圆 + 原因）

1. **下拉弹层**：ttk.Combobox 的 popdown 是 Tk 内部 `tk.Listbox`，位于独立原生窗口，
   没有可靠 API 设圆角/区域；强改需 hack 内部类结构，跨版本易碎。保留直角。
2. **Text / Entry 内部绘制区**：控件本体是矩形，已用「圆角 well + 内缩留白」包裹，
   视觉四角不暴露直角；但文本选区高亮仍是矩形，这一点不掩饰。
3. **Win10 窗口/对话框**：DWM 圆角属性不可用，保持直角（功能不受影响，已注明）。
4. **系统标题栏按钮、系统文件选择器**：OS 绘制，不受应用控制。
5. **滚动条轨道**：自绘 thumb 圆角、轨道透明，无可见矩形；不额外画方槽。

### 性能实测（源码 Tk 8.6，本机中位数，含 PhotoImage 创建）

| 路径 | 耗时 |
| --- | --- |
| 单角块冷光栅化 + PhotoImage | 0.50 ms |
| 4 角缓存命中 | ≈0.00 ms |
| `RoundPanel` 冷建 | 2.09 ms |
| `RoundButton` 冷建（角图已缓存） | 0.45 ms |
| 9 行地址整表重绘 | 2.60 ms |

### Pillow 评估（先量再定 → 否决）

| 方案 | onefile 体积 | import 耗时 | 结论 |
| --- | --- | --- | --- |
| 纯标准库探针 | 9,912,815 B | — | 基线 |
| + `PIL.Image/ImageDraw/ImageTk` | 30,017,173 B | 约 62.6 ms | **+20.1 MB，否决** |

主窗创建耗时（有/无 PIL）941–1052 ms，差异在噪声内。备选方案对比后选**标准库角块**：
构建期预生成位图仍需构建依赖、且尺寸/主题组合膨胀；无 AA 小半径灰边明显。
因此仅新增 `core/raster.py`，**零新依赖**。

### 窗口层兜底

`SetWindowRgn` 已做 spike：无抗锯齿、边缘锯齿明显，**否决**；窗口层只走 DWM，
Win10 直角接受。证据：`spike-legacy-rgn.png` / `spike-legacy-rgn-zoom.png`、
`spike-dwm.png` / `spike-dwm-zoom.png`。

## 5. 布局：网址优先、网卡折叠、左栏填满

- 地址列表独立成卡片，列表下移并拉高；**折叠态一屏 9 行**（旧版运行态只有 1 行，
  地址粘在状态卡里）。对比图：`round5-00-before-after.png`（同尺寸 1056×819，标题标注 1→9 行）。
- 网址 10pt bold 高对比、靠左为主信息；网卡名 9pt 弱化为右对齐次要信息；
  超长 IPv6 地址在中间省略（`http://[fdfa:da62:b01…9387:faef:8711]:5099/`），不再与标签重叠。
- 网卡默认折叠：弱化摘要行「9 个地址 · 单击查看网卡」，点击展开；展开状态记在同一次会话内
  （`_binds_expanded`）；再次点击收起。
- 展开区：固定 3 行可见 + 自绘滚动条，勾选框/名称/IP/状态；行点击、空格、↑/↓ 均可用；
  右上角「全部」一键勾选（优先具体网卡，无具体地址时退化为通配）；勾选后即时刷新预览。
- 状态栏去重：状态卡只写「运行中」，不再附「· N 个地址」；地址数只在左栏。
  失败详情仅在异常时出现，按需展开。
- 最小窗口宽度 960：无横向溢出（`round5-03-min-width.png`，976×759）。

## 6. 版本号迭代

- `core/__init__.py`：`APP_VERSION = "1.6.0"`（唯一真源）。
- `DufsGui.spec`：版本资源从源码读取 `APP_VERSION`，产物名 `dist\DufsGui-v1.6.0.exe`。
- `dist/BUILD-INFO.txt`：版本、Git 状态、体积、SHA256、皮肤版本自动写入。
- `CHANGELOG.md`：新增 `[1.6.0] - 2026-11-03`。
- `README.md` / `docs/使用指南.md`：产物名、版本、圆角与网页外观说明同步。
- `AGENTS.md`：基线更新到 v1.6.0，并记录网页标题/favicon 只能改运行时副本。
- 测试：`python -m unittest discover -s tests -q` → **181 tests OK (skipped=1)**。
- 产物命名核对（2026-11-03）：`DufsGui.spec` 由 `APP_VERSION` 生成 `DufsGui-v1.6.0.exe`，
  `dist/` 仅有该文件，`BUILD-INFO.txt`、`SHA256SUMS`、README 与使用指南中的下载名均为 v1.6.0，
  仓库内无任何 v1.5.0 产物残留。
- `tools/skin_checksums.json` 的 `pinned_version: v0.47.0` 与 `assets/ASSETS_VERSION: 0.47.0`
  **不动**：它们锁定 dufs 二进制与官方皮肤，升级需同时更新官方 SHA256 清单，与 GUI 版本无耦合。

## 7. 构建与冻结验证

| 项 | v1.5.0 基线 | v1.6.0 |
| --- | --- | --- |
| onefile exe | 15,670,029 B | **15,709,253 B**（+39,224 B，+0.25%） |
| SHA256 | — | `5ad1ed670679a7646dcf325e7234dd804d090de9913e00d811895aa06bb38ce0` |
| 启动（冻结 → 主窗可见） | 无同口径基线 | 中位 2.22 s（5 次 1.91–2.93 s，分解见 7.1） |

最终产物由提交 `dd5e31a` 的干净工作树构建，`BUILD-INFO.txt` 记录 Git 状态为「dd5e31a（工作区干净）」。

`build.bat` 从当前工作树一次跑通（构建依赖固定，产物校验与 `SHA256SUMS` 全部通过）。

### 7.1 启动耗时分解（实测）

打点由 `DUFS_GUI_TIMING_FILE` 环境变量开启（默认零开销），每节点记录 epoch 毫秒；
外部脚本从 `Popen` 起每 30 ms 探测 `Dufs GUI` 窗口，取 5 次中位：

| 阶段 | onefile | onedir |
| --- | --- | --- |
| 解包 + 引导（Popen→脚本首行） | **928 ms** | 67 ms |
| Python 导入（→ `imports_done`） | 217 ms | 51 ms |
| Tk 根窗口（→ `tk_root`） | 37 ms | 35 ms |
| 表单变量（→ `vars_ready`） | 329 ms | 28 ms（首启 317） |
| UI 构建（→ `ui_built`） | 143 ms | 140 ms |
| 主题（→ `theme_done`） | 162 ms | 164 ms |
| 状态恢复（→ `state_restored`，含网卡枚举） | 387 ms | 374 ms |
| **合计到窗口可见** | **2220 ms** | **871 ms** |

- onefile 主要来源是**每次启动解包**（928 ms，占 42%），且它在 623–1223 ms 间波动
  （杀软扫描临时目录）；Python/Tk 引导本身很小（导入 217 + 根窗口 37）。
- 应用自身初始化稳定在 ≈1.0–1.15 s：`_restore()`+`_refresh_preview()` 约 387 ms
  （主要是 `list_interfaces()` 枚举网卡），`_build_vars()` 在 onefile 每次冷启约 329 ms
  （onedir 热态仅 28 ms，说明是磁盘/杀软首触成本，不是 Tk 变量本身）。
- 此前口径的「≈1.07 s」对应的是**应用初始化段**（不含 onefile 解包与解释器导入），
  与本次 `app_ms`/onedir 总耗时吻合；不是同一段起止点，不能直接对比。

两种分发形式对比（同一提交、同一代码，不改变当前 onefile 选择）：

| 项 | onefile | onedir |
| --- | --- | --- |
| 启动到窗口可见（中位） | 2.22 s（1.91–2.93） | 0.87 s（0.85–0.92，首启 1.40） |
| 体积 | 15.7 MB | 35.2 MB |
| 文件数 | 1 | 1002 |
| 代价 | 每次解包到 `%TEMP%`，首启受杀软影响 | 目录必须整体分发，不可单文件拷贝 |

结论：启动慢的主因是 onefile 解包，**是否切换分发形式由用户决定**，本轮未改。

冻结 exe 复验（`screenshots/frozen-evidence.json`）：

- 5099 监听 ✔；`%APPDATA%` 下 `webui` 副本存在 ✔
- 服务端 JS 含 `const __DUFS_GUI_TITLE` 与注入行 ✔
- 自定义 favicon 字节与服务器返回一致 ✔（SHA256 `54b2f47e…`）
- 二维码按钮点击后弹出「共享二维码」✔（点击坐标修正为客户区 (969,142)）
- 新布局、圆角、折叠态在冻结版渲染正常（`round4-08/09-frozen*.png`）

## 8. 截图索引（`screenshots/`）

- 同尺寸整窗对比：`round5-00-before-after.png`
- 折叠态：`round5-01-main-folded.png`；展开态：`round5-02-main-expanded.png`；多网卡勾选：`round5-02b-bind-detail-4x.png`
- 最小宽度：`round5-03-min-width.png`
- 高级设置：`round5-04-advanced.png`、`04c` 字段、`04d` 滚动条
- 运行态：`round5-05-running.png`；二维码按钮：`05c-qr-button-4x.png`
- 二维码弹窗：`round5-06-qr-dialog.png`、`06c` 白底圆角、`06d` 窗口圆角
- 网页标题/favicon：`web-title-before/after*.png`、`web-favicon-before/after-zoom.png`
- 冻结版：`round4-08-frozen-main.png`、`round4-09-frozen-running.png`、`round4-10-frozen-qr.png`
- 4× 特写：`02b` 窗口角、`02d` 输入框焦点、`01d` 路径字段、`01e` 主按钮、`01f` 地址行、`01g` 日志滚动条

## 9. 未做到 / 未验证

- **未圆**：下拉弹层、Text 选区、系统标题栏/文件选择器；原因见第 4 节清单。
- Win10 仅按 API 返回值降级，当前机器为 Win11，未在 Win10 实机截图。
- 125%/150% DPI 缩放下未逐档截图（Tk 整数缩放，角块按逻辑像素生成）。
- 启动分解为本机（Win11、Defender 开启）5 次中位，未覆盖不同磁盘/杀软组合；
  旧的「≈1.07 s」无原始日志，只能按段位对齐（对应应用初始化段，不含解包）。

## 10. 现场核对

开工前 `git status` 无他人改动，`git log -5` 顶部为 `9d6b23b`；本轮所有改动均为本会话产出，
未发现接手会话留下的额外提交或冲突文件。

## 11. 批次 6b：控制台黑框核实 + 删除确认框

### 11.1 黑框：先核实，再加固

核实顺序与结论：

1. **代码**：`core/server.py` 的 `popen_kwargs` 原本就有 `stdout=PIPE`、`stderr=STDOUT`，
   Windows 分支原本就有 `creationflags=CREATE_NO_WINDOW`，且 `version()` 探测也带该标志
   （`core/dufsbin.py:213`）。本轮补齐 `STARTUPINFO`：`STARTF_USESHOWWINDOW` + `wShowWindow=0`
   （SW_HIDE），作为第二层保险；非 Windows 分支未改。
2. **打包**：`DufsGui.spec` 为 `console=False`，成品 PE subsystem = 2（Windows GUI），
   不存在「debug 版 exe」被误发的迹象。
3. **实测**（本轮新构建 v1.6.0，19:10 产物）：

| 时点 | 可见控制台窗口 | conhost 数 | dufs 进程 | 5099 |
| --- | --- | --- | --- | --- |
| 启动前 | 0（另有 1 个隐藏 `ConsoleWindowClass`，pid 27128，早于本次启动存在） | 20 | 无 | 关闭 |
| 运行中 | 0（同一隐藏窗口，列表无新增） | 21 | 1 个 | 监听 |
| 停止后 | 0（同一隐藏窗口） | 20 | 无 | 关闭 |

- 运行期多出的 1 个 `conhost.exe` 经 `Win32_Process.ParentProcessId` 确认父进程 = `dufs.exe`：
  这是 `CREATE_NO_WINDOW` 下**无窗口**的控制台宿主，不是用户看到的黑框形态。
- 日志证据（`round6-01-frozen-running.png` 日志区）：`[命令]` → `已启动` →
  `[仅本机] Listening on http://127.0.0.1:5099/` → `HEAD` 请求，说明输出仍被 PIPE 接管并进日志。
- 结论：当前代码与产物**不可复现**常驻黑框。若用户仍见黑框，基本可判定其运行的是旧版
  或 debug（`console=True`）构建；本轮的 SW_HIDE 加固对「控制台闪现」也一并兜住。
- 取证脚本 `C:\Temp\dufsgui_shots\console_probe.py`（窗口枚举 + `Win32_Process` 父子关系 +
  `PrintWindow` 截图），原始 JSON `C:\Temp\dufsgui_shots\console-evidence.json`。

### 11.2 删除方案：深色自绘模态确认框

- 复用 `ui/dialog.py` 的 `ask_yes_no`（Toplevel + DWM 深色标题栏 + DWM 圆角 + 圆角卡片 +
  `RoundButton`），未使用原生 `messagebox`。
- 文案：`删除方案「X」？` / `此操作不可撤销`；按钮「删除」（`danger` 红 `#ff453a`）/「取消」。
- 按键：`_key_results(default_ok=False)` → `<Escape>`=取消、`<Return>`=取消；
  调用改用 `dialogs.ask_yes_no(..., destructive=True, default_ok=False)`。
- 模态：`_modal` 内 `grab_set()` + `wait_window()`，期间主窗口不可操作。
- 保存/应用未加确认（保持原行为）。
- 尺寸修正：`_card` 取消 `expand`，`_modal` 先把窗口摆到屏幕外完成映射再量高，
  确认框从 460×333（大片空白）收口为 460×142。
- 实测（源码运行态，`capture_delete_confirm.py`）：
  `esc_keeps=true`、`enter_keeps=true`、`delete_removes=true`（点「删除」后才移除）。
- 截图：`round6-02-delete-confirm.png`（深色整窗）、`round6-02b-delete-dialog-full.png`、
  `round6-02b-delete-dialog-full-3x.png`（圆角/描边抗锯齿特写）。

### 11.3 回归与产物

- 全量单测：**186 通过 / 1 跳过**（新增 `tests/test_popen_flags.py`，
  `tests/test_ui_smoke.py` 增两条删除流程测试）。
- `build.bat`：成功；`--selftest` 通过；`BUILD-INFO.txt` / `SHA256SUMS` 已重新生成。
- 产物：`dist/DufsGui-v1.6.0.exe`，**15,711,066 字节**（上一版 15,670,029，+41,037 B），
  SHA256 `CDF7314BF14D08A62D769E62A35BF033F2B44238133ED1C2C283FF8847F64BEC`。
- 冻结复验：启动共享 → 5099 可连、日志有 dufs 输出、停止后 dufs 进程与端口均消失、无新增可见控制台。
- 未验证：删除确认框截图为源码运行态（冻结版共用同一 `ui/dialog.py`，未在冻结版点选方案流程中复现）。

## 12. 批次 7：共享页汉化 / 去彩条 / 二维码多地址

### 12.1 文案来源与可改边界

先区分「页面自绘」「dufs 二进制」「浏览器原生」三类来源，只改第一类：

| 来源 | 具体位置 | 处理 |
| --- | --- | --- |
| 皮肤 JS 固定文案 | `assets/index.js`：按钮 `title`、空列表提示、搜索表头、上传/编辑/删除/重命名弹窗文本 | 运行时副本逐条替换，共 36 条 |
| 皮肤静态文案 | `assets/index.html`：`lang`、按钮 `title`、`aria-label="Editor"`、上传任务表头 | 运行时副本替换，共 13 条 / 14 处 |
| 皮肤样式 | `assets/index.css` 第 357–365 行 `body::before` 渐变彩条 | 运行时副本末尾追加覆盖 |
| 浏览器标签标题 | `index.js` 3 处 ``document.title = ...`` | 沿用既有标题注入；空值回落中文标题 |
| **dufs 二进制内置页** | `?noscript` 回退页（`Index of /`、`10.00 B`、`../`） | **不可改**，明确保留英文 |
| **dufs 二进制错误正文** | 404 `Not Found`、403 等纯文本；401 由 `WWW-Authenticate: Basic realm="DUFS"` 触发浏览器登录框 | **不可改** |
| **浏览器原生弹层** | `confirm`/`prompt`/`alert` 的按钮文字、HTTP Basic 登录框 | 文本已汉化；按钮文字随浏览器语言，**不可改** |
| 服务端动态文本 | `${ajax.status} ${ajax.statusText}`、上传失败 `${reason}` | **不翻译**（服务器/浏览器状态文本） |
| 内部枚举 | `DATA.kind` 的 `Dir`/`File`/`SymlinkDir` 等 | 逻辑值，非界面文案，不动 |
| 文件名/用户数据 | 目录项、路径、共享名 | **不翻译** |

没有用 CSS 隐藏英文来冒充汉化：`?noscript`、错误正文、登录框仍会显示英文，选中「网页美化界面」
时页面常规操作文案为中文。关闭「网页美化界面」则 dufs 使用内置官方皮肤（英文），这是用户显式选择。

### 12.2 运行时副本注入与维护成本

- `core/webtweak.py` 的 `prepare_overlay` 现在只要 `custom_ui` 开启就生成副本（此前仅标题/favicon
  非空才生成）：复制 `assets/` → 标题注入 → `localize_index_js` / `localize_index_html` →
  `patch_index_css` → 自定义 favicon（可选）。仓库 `assets/` 始终不写（测试断言源目录仍为英文）。
- 汉化采用**锚点计数 + 整文件全有或全无**：每条原文必须出现预期次数(M=1/2)，否则该文件不写并记日志
  「结构已变化，未汉化（N 处不符）」。优点是不会出现中英混杂；维护成本是皮肤升级后按日志补映射，
  单测 `test_localize_real_skin_and_remove_top_bar` 会在锚点失配时直接失败提醒。
- CSS 覆盖带标记，重复调用幂等；每次启动重建副本，因此皮肤重新 `fetch_skin.py` 后依然生效。

### 12.3 顶部彩条去掉

- 来源：`assets/index.css:358` `body::before`，`height: 3px`，
  `linear-gradient(90deg, #4f9cf9, #7c5cff, #3fb950)`，`z-index:100`。
- 复制副本末尾追加 `body::before { content:none; display:none; height:0; background:none }`，
  不改官方文件。彩条下面是 `.head` 的深色背景，去掉后无白边、无断层；导航/工具栏未动。
- 截图（Edge 实际渲染，1280×900 / 520×900）：
  `round7-web-before-1280.png`、`round7-web-before-520.png`（有彩条、英文表头）；
  `round7-web-after-1280.png`、`round7-web-after-520.png`（无彩条、中文表头）。

### 12.4 二维码多地址

- `app._qr_urls()`：运行中用 `manager.running_states` 的实际地址，未运行用
  `cfg.effective_binds()` 的配置地址；去重且保留顺序（启动计划/网卡排序：活动网卡优先、回环垫底），
  首项即默认主推。
- `dialogs.build_qr_window(parent, url, urls=...)`：首项默认选中；多于一个地址时顶部显示
  「访问地址」`ttk.Combobox`，切换触发 `qr_select()`；单地址不创建选择器。
- 性能：构建时按 URL 预生成矩阵缓存 `qr_cache`；切换只重绘 Canvas，不重新编码；窗口按最大
  QR 边长固定，切换不跳动。复制链接读 `qr_payload`，保存 PNG 读 `qr_matrix`，均跟随当前地址。
- 尺寸：多地址 376×575，单地址 376×523（少 52px 选择器行，无空洞）。
- 截图：`round7-qr-multi-default.png`（10.4.240.16）、`round7-qr-multi-switched.png`（127.0.0.1）、
  `round7-qr-single.png`（无选择器）；冻结版对应 `round7-frozen-qr-*.png`。

### 12.5 GUI 副标题移除

- 删除 `ui/layout.py` 中「固定深色 · 基于 dufs 的轻量文件共享」整行，`actions` 从 `rowspan=2`
  改为单行；仅保留 `Dufs GUI` 标题。全文检索该文案已无残留（单测断言）。
- 截图：`round7-gui-no-subtitle.png`、`round7-gui-no-subtitle-header-2x.png`、冻结版
  `round7-frozen-main.png`；标题与右侧按钮同排，无空行/空洞。

### 12.6 回归与产物

- 全量单测：**192 通过 / 1 跳过**。新增/调整：运行时副本始终生成、真实皮肤全量汉化与去彩条、
  锚点失配拒绝半汉化、CSS 覆盖幂等、二维码选择器切换/单地址隐藏、`_qr_urls` 顺序去重、副标题移除。
- `build.bat`：成功；`--selftest` 通过；`BUILD-INFO.txt` / `SHA256SUMS` 已更新。
- 产物：`dist/DufsGui-v1.6.0.exe`，**15,716,495 字节**，
  SHA256 `483DAAC4A0AA6ECECF81C6539CB7ABFB20AB2DA438CB48922DB972B6890B3C49`。
- 冻结复验（`C:\Temp\dufsgui_shots\freeze_round7.py`）：
  - 双地址启动后 `10.4.240.16:5099` 与 `127.0.0.1:5099` 均 HTTP 200；
  - 冻结进程生成的 `%HOME%\webui\index.js` 含中文表头/删除确认，`index.css` 含覆盖标记；
  - 冻结版二维码弹窗选择器存在，自动化点击下拉+↓/Enter 后链接区像素变化（`QR_SWITCHED True`）；
  - 单地址冻结版弹窗 376×523，无选择器；停止后进程退出码 0，无 dufs 残留；
  - 冻结服务页面截图 `round7-frozen-web-1280.png`（中文、无彩条）；运行/停止态
    `round7-frozen-running.png` / `round7-frozen-stopped.png`。

### 12.7 未验证 / 不能验证

- `?noscript` 页、HTTP 错误正文、Basic 登录框保持英文（dufs 二进制/浏览器硬编码，非隐藏）。
- 浏览器原生 `confirm/prompt/alert` 按钮文字（OK/取消）由浏览器语言决定，未做也不可做。
- 未用真实手机扫码验证；二维码内容与链接一致性由单测断言（`qr_payload == 当前地址`）。
- 冻结版未实际点击「复制链接」「保存 PNG」（按钮存在、代码路径与批次 6 相同，未改动）；
  保存路径依赖系统文件对话框。
- 仅在本机 Win11 / 125% 缩放下截图，未覆盖 Win10 与其他 DPI。

