# DEVELOPMENT.md

> 结构固定三块：项目概览 → 架构说明 → 关键问题与方案。
> 一坑一篇的完整记录见 [`docs/问题记录/`](docs/问题记录/)。

## 一、项目概览

给命令行工具 **dufs** 套一个 Windows 桌面外壳。本身不实现任何文件服务能力，
全部能力来自以子进程方式拉起的 `dufs.exe`——本项目的职责是**把 dufs 的参数变成表单**，
并保证在各种环境下都能稳定地把 dufs 拉起来。

设计取向：

- **零第三方运行时依赖**（仅标准库），打包体积小、可靠性高
- **默认安全**：监听 `127.0.0.1`、删除关闭、符号链接关闭
- **失败要看得见**：`console=False` 下异常会静默消失，因此内置崩溃落盘与自检
- **皮肤不能挡住共享**：网页美化默认开启，失败时自动降级；降级只影响本次运行，不写盘

## 二、架构说明

```
main.py            入口，装崩溃兜底后启动 GUI
app.py             窗口生命周期与启停编排（界面/表单/弹窗已拆到 ui/）
ui/
  common.py        APP_NAME 与跨平台字体
  form.py          表单变量 ⇄ ServerConfig 的双向映射
  layout.py        主窗口控件骨架
  advanced.py      高级设置弹窗
  bindlist.py      固定高度网卡勾选列表（Canvas + 内嵌行；方向键/空格/滚动）
core/
  config.py        ServerConfig 数据类：字段 + 命令行生成 + 校验 + 持久化；
                   AppConfig schema 版本化（v1→v2 自动迁移、坏配置备份、原子写）
  launch.py        build_launch_plan(cfg) 纯函数：参数/皮肤诊断/降级参数/URL
  runtime.py       DufsRuntime：dufs 定位、版本探测与进程状态的统一入口
  dufsbin.py       dufs.exe 的查找 / 释放 / 安装 / 皮肤目录定位与校验
  server.py        DufsProcess：子进程启停、日志采集、就绪探测、DLL 环境清理
  netutil.py       本机 IP、端口占用检测、空闲端口推荐、前缀规范化
  netif.py         Windows GetAdaptersAddresses 枚举网卡：排序（物理 > 虚拟/VPN > IPv6 >
                   不可用 > 0.0.0.0 > 回环）、默认勾选、保存值回填
  instances.py     InstanceManager：每个绑定地址一个 DufsProcess，共用端口/目录/Job Object，
                   并行等待就绪、单地址失败隔离、启动结果汇总
  theme.py         固定深色 + Apple 设计 token（含滚动条/下拉/列表/勾选框）
  winpos.py        弹窗定位（多显示器钳制）
  crashlog.py      sys.excepthook / 线程异常 / tkinter 回调异常 → 落盘
assets/            dufs 官方 v0.47.0 网页皮肤 + CSS 覆盖层
tools/             fetch_dufs.py（下载 dufs）、fetch_skin.py（同步官方皮肤）、
                   _integrity.py（固定版本 + 逐源 SHA256）、
                   *_checksums.json（官方 digest / TOFU 清单）、
                   embed_dufs.py（可选 base64 内嵌）、
                   build_info.py（生成 BUILD-INFO.txt 与 SHA256SUMS）
licenses/          dufs 上游 MIT / Apache-2.0 许可原文 + 来源说明（随包分发）
tests/             标准库 unittest；tk_stub.py 提供无 tkinter 环境下的桩
```

测试与 CI：

- 本地：`python -m unittest discover -s tests`，测试数量以输出为准；
  jsdom 皮肤 E2E 在缺依赖时自动跳过
- Windows CI：`.github/workflows/windows-ci.yml`
  - `unittest` job：`windows-latest`，矩阵 Python 3.9 / 3.12，只跑标准库 unittest
  - `build-check` job：Python 3.14，安装 `requirements.txt` 锁定依赖 → 打包 onefile
    → `--selftest` → 断言产物非空 → 生成并校验 BUILD-INFO/SHA256SUMS
  - runner 无交互桌面，故只跑 `--selftest`，不启动 GUI；CI 不发布

配置与启动（P1）：

- `AppConfig` 带 `config_version`（当前 v2）；无版本号的旧配置载入即迁移。
  解析失败或版本高于当前支持时，先把坏文件备份为 `config.bad.json`，
  再回落默认值，并通过 `notice` 在日志里明确提示，不静默吞掉。
- 配置保存走同目录临时文件 + `os.replace`，避免崩溃留下半截 JSON。
- 启动决策集中在 `core/launch.py` 的 `build_launch_plan(cfg)`：
  参数、皮肤诊断、降级参数、检查主机与 URL 都是纯数据，界面层只执行计划。
- 多地址：`ServerConfig.binds` 为真源，`effective_binds()` 兼容旧 `bind` 单地址自动升级；
  `build_launch_plans()` 为每个地址生成一份 `LaunchPlan`（各自 `-b`、同一端口），
  `InstanceManager` 逐地址拉起 `DufsProcess` 并加入**同一个 Job Object**。
  `all_loopback()` 仅在全部地址为回环时为真。
- `summarize_start_results()` 汇总为「N 个地址均已启动 / N 个中 M 个已启动 / 全部失败」，
  端口占用只跳过该地址，不阻断其他地址。

界面（P1.5）：

- 固定深色，token 集中在 `core/theme.py`：`#1e1e1e` 底、`#232325` 面板、`#2c2c2e` 控件、
  `#1a1a1c` 滚动槽、`#3a3a3c` 边框、`#8e8e93` 次要文字、`#0a84ff` 强调、`#ff453a` 危险；
  间距 4/8/12/16/24（8pt 栅格），控件高约 32px，三级字号。
- Tk 不支持真实圆角、毛玻璃、SF 字体与连续动画，因此层次用**背景色差 + 1px 低对比描边**
  表达，不为"像 macOS"堆自绘；勾选框用自绘 16x16 位图保证深色下选中态可见。
- 网卡选择从下拉改为勾选列表：`ui/bindlist.py` 内嵌 Frame + Canvas，行高固定 32px；
  弹窗 ≤20 行一次显示、>20 行封顶 20 行滚动（滚动条走 `Vertical.TScrollbar` 深色样式），
  小屏按工作区高度兜底；无地址网卡在弹窗层过滤。
- 主窗启动尺寸固定为 `minsize` 960×720（客户区），不记忆上次大小/位置；Tk 实测
  `minsize` 优先于 `geometry`：小于最小值的 geometry 会被钳回，等值时两种设置顺序结果一致。
  960×720 下最下缘控件（高级设置 695px、日志横向滚动条 691px）与最右缘控件（二维码 927px）
  均在窗内，无裁切。
- 网页皮肤顶栏与文件列表共用同一条左边线：运行时覆盖把 `.head` 的左右内边距改为
  `calc(22px + max(0px, (100% - 1324px) / 2))`，跟随 `.main` 的 1280px 居中容器
  （外宽 = 1280 + 左右各 22px）；≤640px 断点同步为 12px。只影响 >1324px 的宽视口，
  1280 / 1080 / 520 档位数值不变。

构建与产物（P2）：

- `requirements.txt` 固定 `pyinstaller==6.22.3`；`build.bat` / `build_debug.bat` /
  `build.sh` 缺包时只提示按 requirements 安装，不再自动 `pip install -U`。
- `build.bat` 打包后先跑 `--selftest`，再调用 `tools/build_info.py` 生成
  `dist/BUILD-INFO.txt`（Python / PyInstaller / Tk / dufs / 皮肤 / Git 状态）
  与 `dist/SHA256SUMS`（exe + 关键构建输入）。
- dufs 上游 MIT / Apache-2.0 许可原文位于 `licenses/`，由 spec 打进 `licenses/`
  随包分发；`--selftest` 的 `licenses` 行可用于确认冻结产物里确实带上了。
- 当前本机验证产物：CPython 3.14.6 + PyInstaller 6.22.3 + Tk 8.6（详见 BUILD-INFO）。
- 发布 exe 的 PE 清单没有 `dpiAware` 声明，属于 DPI 不感知进程：150% 缩放下由系统
  整窗位图放大（960×720 逻辑 → 1440×1080 物理），`minsize` 数值不随 DPI 变化；
  若将来声明 DPI 感知，需按 `dpi / 96` 同步放大 `minsize`，否则字体变大会挤压 960×720 布局。

关键安全默认（P0）：

- 访问口令是可选能力：`ServerConfig.validate()` 不再因"非回环监听 + 无口令"拒绝启动，
  只校验 `-a` 参数合法性；未填口令即匿名访问，且**运行时不产生任何提示**。
  `command_line()` 只输出脱敏口令，日志与 URL 不含密码。
- Windows 子进程加入 Job Object（`KILL_ON_JOB_CLOSE`）；POSIX 用 atexit/SIGTERM 兜底。
- 下载脚本固定 `pinned_version`，每个来源单独比对 SHA256；哈希不符立即失败，
  只有网络失败才换源。TOFU 仅用于清单缺失时，不能当作上游签名。

三条关键链路：

1. **配置 → 命令行**：`ServerConfig.to_args()` 是唯一的真源。界面底部实时显示等效命令行，
   既方便用户学 dufs 参数，也便于排查。
2. **dufs 定位**：`环境变量指定 > 内置资源 > 已落盘副本 > PATH > 内嵌数据`。
   内置排在落盘副本**前面**，配合大小/mtime 比对，保证升级 GUI 时新版 dufs 能覆盖旧版。
3. **启动判定**：`wait_ready()` 同时监测端口与进程存活——进程秒退立即返回 False，
   不白等超时。

## 三、关键问题与方案

| 问题 | 一句话 |
|---|---|
| [spec 里 `OS` 未定义](docs/问题记录/问题：spec文件里OS变量未定义导致打包中断.md) | spec 没有 `OS` 全局变量，判断系统要 `import os` |
| [中文 bat 被当命令执行](docs/问题记录/问题：UTF-8编码的中文bat被cmd当成命令执行.md) | bat 必须 GBK 或纯 ASCII，`chcp 65001` 救不了 |
| [`--assets` 缺 index.html](docs/问题记录/问题：dufs因assets目录缺少index.html拒绝启动.md) | dufs 启动即 bail，必须三件套齐全 |
| [子进程继承 DLL 搜索路径](docs/问题记录/问题：子进程继承DLL搜索路径导致dufs无法启动.md) | `Popen` 前 `SetDllDirectoryW(None)` 并清 PATH |
| [下拉列表/复选框深色不可见](docs/问题记录/问题：ttk下拉列表与复选框在深色下不可见.md) | 下拉是原生 Listbox；clam 对勾是硬编码深色 |
| [弹窗内容被裁切](docs/问题记录/问题：弹窗内容超出固定尺寸被裁切.md) | withdrawn 时 `winfo_reqheight()` 不可靠；固定 760 高 + Canvas 滚动兜底 |

## 四、与 knowledge-base 的衔接

本仓库的「问题记录」与 knowledge-base 用户库**格式完全一致**，可零转换提炼。
跨项目通用的候选：

- Windows 下 PyInstaller 打包 tkinter 的通用坑（spec 变量 / DLL 继承 / 杀软误报）
- 中文 Windows 批处理编码陷阱
- ttk 深色主题的能力边界（哪些部件根本改不了）
