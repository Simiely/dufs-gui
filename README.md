# Dufs 文件共享 · GUI 封装

给 [dufs](https://github.com/sigoden/dufs) 套一个 Windows 桌面外壳：选目录、配端口、点一下开启共享，附带深色界面和可选的美化网页端。

**为什么不用命令行**：dufs 本身很优秀，但每次共享都要敲 `dufs D:\xxx -b 10.x.x.x -p 5000 --allow-delete`，参数记不住、端口占用要自己查。这个 GUI 把这些变成勾选框和输入框。

```
┌─ 常用配置 ───────────────┬─ 状态与日志 ────────────────┐
│ 方案      [方案名 ▾]      │ ● 未启动                     │
│ 共享目录  [D:\...] [选择]  │ http://10.4.240.16:5000/     │
│ 共享网卡  ☑ 以太网 10.4…   │ [打开网页] [复制地址]         │
│          ☑ 仅本机 127.0.0.1│ ── 运行日志 ──               │
│ 端口      [5000] [检测]    │ 17:03:21 dufs 就绪           │
│ [高级设置…]               │                              │
└───────────────────────────┴──────────────────────────────┘
                        [开启共享] [停止]
```

## 快速开始

**已有构建产物**：双击 `dist\DufsGui-v1.6.15.exe` 即可（单文件外壳；首次启动解压到本地缓存，之后复用）。

**从源码构建**：双击 `build.bat`，它自动完成「取 dufs → 打包 → `--selftest` → 生成校验和」。
只有缺 PyInstaller 时会停下并打印一行可复制的安装命令
（`python -m pip install -r requirements.txt`），装完再双击一次即可。

**只想看界面**（不打包）：`python tools\fetch_dufs.py`（首次取 v0.47.0）→ `python main.py`。

环境要求：python.org 官方 CPython **3.12+**（本机验证 3.14.6；不要用 3.13.0、conda / 嵌入式版）。
路径请用纯英文。闪退或打包失败先跑 `build_debug.bat`。

### 首次启动预期

- 首次启动会把内置的 onedir payload 解压到 `%LOCALAPPDATA%\DufsGui\payload\v1.6.15\`
  （约 1 秒）；之后启动直接校验缓存并复用。缓存损坏会自动重解压，原因记在
  `%LOCALAPPDATA%\DufsGui\shell.log`。
- 首次运行创建 `%APPDATA%\DufsGui\config.json`，并把内置 dufs 释放到
  `%LOCALAPPDATA%\DufsGui\bin\dufs.exe`。
- 主窗口默认勾选**第一块已连接网卡**（本机实测为以太网 `10.4.240.16`）；只有回环可用时才默认
  「仅本机 · 127.0.0.1」。选好共享目录后点「开启共享」，再点「打开网页」。
- 主窗口每次按**最小可用尺寸 960×720** 打开（与拖到最小后的客户区同尺寸），不记忆上次窗口
  大小/位置；该尺寸下底部按钮行、状态行与右侧日志栏完整可见。

## 主要能力

| | 说明 |
|---|---|
| 共享配置 | 目录、共享网卡（「查看网卡」弹窗内**可多选**）、端口（占用自动推荐空闲端口）、URL 前缀；卡片底部只用 `10.4.240.16 · 127.0.0.1` 显示参与共享的 IP |
| 多网卡共享 | 同时勾选多块网卡，各自访问地址与状态分别显示；每块网卡一个 dufs 进程共用同一端口与目录，单地址失败不影响其他，状态栏汇总「N 个中 M 个已启动 · K 个失败」，具体原因在可折叠「失败详情」区；无失败时该区整块隐藏 |
| 共享链接二维码 | 服务状态区链接右侧的按钮可打开深色二维码窗，内容为当前运行地址（如 `http://10.4.240.16:5099/`），支持复制链接与保存 PNG |
| 访问口令 | 可选：高级设置里填写用户名/口令即启用，生成 dufs `-a user:pass@/:rw`；留空即为匿名访问（不鉴权、不提示）；界面预览与日志只显示脱敏值 |
| 网页端能力 | 上传 / 删除 / 搜索 / 打包下载 / 符号链接 / CORS，勾选即生效 |
| 配置方案 | 多套「目录 + 端口 + 能力」存成方案随时切换 |
| 界面 | 固定深色（含滚动条、下拉列表、Windows 标题栏与自绘对话框），不提供浅色模式；按 macOS 深色设计 token 排版（色差分层、8pt 栅格、32px 控件、系统蓝 `#0a84ff`）；「开启共享 / 停止」固定在标题行右侧 |
| 网页标题与图标 | 浏览器标签页标题可自定义（最长 48 字，空值用 dufs 官方标题），可换本地 `.ico` 站点图标；需勾选「网页美化界面」，下次开启共享生效。GUI 窗口标题固定「Dufs GUI」 |
| 圆角 | 主按钮与卡片/面板抗锯齿圆角（8px / 12px），Win11 下窗口与对话框由 DWM 圆角；Win10 保持直角，功能不受影响 |
| 日志 | 实时回显，可清空 / 导出；启动时把等效命令行以 `[命令]` 前缀写入日志（口令显示为 `user:***@/:rw`），可直接复制排查 |
| 网页皮肤 | dufs 官方 assets v0.47.0 + CSS 覆盖层：官方 HTML/JS 保证功能，CSS 做深色配色与视觉改造；升级 dufs 后用 `tools/fetch_skin.py` 同步 |

安全默认值：默认勾选第一块已连接网卡（只有回环可用时才是 `127.0.0.1`）、删除默认关闭、符号链接默认关闭并二次确认。
**不填口令即为匿名访问**（不鉴权、不弹窗、不提示、不写日志），同网段任何人都能访问；
需要限制访问请在高级设置里填写口令，填了就生效。只想本机使用就在「查看网卡」弹窗里只勾选 `127.0.0.1`。

## 版本

当前 **v1.6.15**。版本号唯一定义在 [`core/__init__.py`](core/__init__.py)，
打包产物名（`dist\DufsGui-v1.6.15.exe`）与构建信息从它派生；GUI 窗口标题固定
「Dufs GUI」，浏览器标签页标题在高级设置「网页外观」里配置。

## 构建可复现与产物校验

- PyInstaller 固定在 [`requirements.txt`](requirements.txt) 的 **6.22.3**（本机验证：
  CPython 3.14.6 / Tk 8.6）。CI 与本地安装同一精确版本；未锁传递依赖哈希，
  因为它是构建工具而非运行时依赖。
- 每次打包生成 `dist\BUILD-INFO.txt`：记录实际 Python、PyInstaller、Tk、dufs、
  皮肤版本与 Git 状态，回答"这个产物由哪套环境构建"。
- 同时生成 `dist\SHA256SUMS`（sha256sum 格式）：exe + 关键构建输入
  （`bin\dufs.exe`、`assets\`、`licenses\`、`requirements.txt`、spec、两份校验和清单）。
  除 exe 外的条目是**打进包内的输入**，用于审计来源，不单独分发。
- 校验：`Get-FileHash dist\DufsGui-v1.6.15.exe -Algorithm SHA256`，
  或在仓库根目录执行 `sha256sum -c dist/SHA256SUMS`。

## 测试

```bat
python -m unittest discover -s tests   :: 数量以实际输出为准；jsdom 皮肤 E2E 缺依赖时自动跳过
```

Windows CI 见 [.github/workflows/windows-ci.yml](.github/workflows/windows-ci.yml)：
单测 job 覆盖 Python 3.9 / 3.12；另有一个 **build-check** job，安装锁定依赖 → 打包
onefile → `--selftest` → 断言产物非空并校验 SHA256SUMS。runner 没有交互桌面，
因此 build-check 不启动 GUI；CI 不负责发布（无 tag 触发、无上传步骤）。

## 供应链校验

- dufs 版本固定在校验和清单 [`tools/dufs_checksums.json`](tools/dufs_checksums.json)
  中（当前 `v0.47.0`），下载脚本不再自动追 latest。
- 每个资产、**每一条下载来源**都有独立 SHA256；下载后逐个比对。哈希不符会立即
  失败并停止，**不会静默切换到下一个镜像**。只有网络失败才允许换源，且逐条打印原因。
- 内置皮肤的 `index.html` / `index.js` / `favicon.ico` 与官方逐字节一致，
  `index.css` 是"官方原始文件 + 本地覆盖层"；清单记录的是官方原始文件的哈希。
  见 [`tools/skin_checksums.json`](tools/skin_checksums.json)。
- 清单中的哈希来自 GitHub Releases API 的官方 `digest`（sha256）字段。若某个来源
  留空，脚本会按 **TOFU（首次信任）** 记录哈希并写回清单：该策略只能发现
  "下载后被替换"，**无法发现首次下载即被投毒，不等价于上游签名**。
  升级版本时请先更新清单，不要让脚本跳过校验。

## 常见问题

| 现象 | 说明与处理 |
|---|---|
| SmartScreen 拦截"未知发布者" | exe 未签名且下载量少；点「更多信息 → 仍要运行」，或从源码自行构建 |
| 杀毒软件报毒 / 隔离 | onefile 会往 `%TEMP%` 释放可执行文件并拉起 dufs，行为本身可疑；加白名单，或改 `DUFS_GUI_MODE=onedir` 打包（误报显著更低） |
| 启动要 1–3 秒 | onefile 每次启动都解压到 `%TEMP%\_MEI*`；onedir 明显更快 |
| 端口被占用 | 界面会提示并推荐空闲端口；也可 `netstat -ano \| findstr :5000` 查占用进程 |
| 多网卡只有部分启动成功 | 状态栏汇总「N 个中 M 个已启动 · K 个失败」，展开「失败详情」查看失败地址与原因（常见是某个 IP 上端口被占）；其他地址照常可用 |
| 双击闪退、无报错 | 先跑 `build_debug.bat`（控制台 + 抓输出），或读 `%LOCALAPPDATA%\DufsGui\crash.log` |
| 网页皮肤没生效 | 看日志是「已加入 --assets」还是「未传 --assets」；单文件共享不支持皮肤 |

## 日志与配置位置

| 内容 | 路径 | 说明 |
|---|---|---|
| 配置 | `%APPDATA%\DufsGui\config.json` | **Roaming**，用户设置随账户漫游 |
| 崩溃日志 | `%LOCALAPPDATA%\DufsGui\crash.log` | **Local**，机器相关，不随账户漫游 |
| dufs 缓存副本 | `%LOCALAPPDATA%\DufsGui\bin\dufs.exe` | 包内 dufs 释放到这里，避免每次从 `%TEMP%` 启动 |
| 运行日志 | 界面「运行日志」区；导出路径由你选择 | 若配置了 dufs `--log-file`，写到指定文件 |

`%APPDATA%` 与 `%LOCALAPPDATA%` 是**两个不同目录**，不要只翻 Local 找 `config.json`。
设置环境变量 `DUFS_GUI_HOME=<目录>` 时，配置、crash.log 与 dufs 缓存都改落到该目录。

## 文档

| 文档 | 给谁看 |
|---|---|
| [使用指南](docs/使用指南.md) | 使用者：完整配置项、打包与排错 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发者：架构与关键问题 |
| [问题记录](docs/问题记录/) | 排查具体坑（一坑一篇） |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更 |
| [AGENTS.md](AGENTS.md) | AI / 未来的自己 |

## 已知限制

- 单实例只能挂一个共享目录（dufs 限制）；要多个就开多个程序实例
- 多网卡同时共享时，每个地址各起一个 dufs 进程（共用同一端口与目录）。dufs 0.47 的
  `-b a,b` 单进程多绑定可用，但任一地址端口被占会让整进程失败，无法做到"只失败一个地址"，
  因此这里按地址拆进程；同一端口绑定不同 IP 是合法的，停止时统一结束全部实例
- dufs 单文件模式（分享单个 iso 等）不走目录列表逻辑，网页皮肤不适用
- 网页皮肤基于 dufs 官方 assets v0.47.0；dufs 升级后需用 `tools/fetch_skin.py` 重新抓取，HTML/JS 与 dufs 必须同版本
- 访问口令以**明文**保存在本地配置文件（`%APPDATA%\DufsGui\config.json`，或 `DUFS_GUI_HOME` 指定目录）；HTTP 下口令也以明文经过网络，跨公网共享请自行启用 HTTPS
- 关闭程序会结束 dufs；Windows 下父进程被强杀时由 Job Object 兜底，POSIX 下 SIGKILL 无法捕获（只能覆盖正常退出与 SIGTERM/SIGINT）

## License

本项目代码采用 **MIT**，见 [LICENSE](LICENSE)。

内置/随包下载的 dufs 二进制固定为 **v0.47.0**，来自 [sigoden/dufs](https://github.com/sigoden/dufs)，
上游按 **MIT OR Apache-2.0** 双许可分发；本项目不改变上游许可。
两份许可原文已作为数据文件打进产物：源码树 [`licenses/`](licenses/)，
运行时可在 exe 解压目录的 `licenses/` 下查看（`--selftest` 会列出）。
上游许可：[LICENSE-MIT](https://github.com/sigoden/dufs/blob/v0.47.0/LICENSE-MIT) /
[LICENSE-APACHE](https://github.com/sigoden/dufs/blob/v0.47.0/LICENSE-APACHE)；
dufs 版本与二进制 SHA256 见 [`tools/dufs_checksums.json`](tools/dufs_checksums.json)。
