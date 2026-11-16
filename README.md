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

| 场景 | 怎么做 |
|---|---|
| 已有构建产物 | 双击 `dist\DufsGui-v<版本>.exe` |
| 从源码构建 | 双击 `build.bat`：取 dufs → 打包 → `--selftest` → 生成校验和 |
| 只想看界面 | `python tools\fetch_dufs.py` → `python main.py` |

环境要求：python.org 官方 CPython **3.12+**（本机验证 3.14.6；不要用 3.13.0、conda / 嵌入式版），
路径用纯英文。闪退或打包失败先跑 `build_debug.bat`。

> **两种产物形态**：`build.bat` 产出的是普通 onefile；发布用的「单文件外壳 + onedir 缓存」由
> 仓库外的 `_exp/build_release.py` 产出，**无法从本仓库复现**。
> 打包细节见 [打包与供应链](docs/打包与供应链.md)，排错见 [使用指南](docs/使用指南.md)。

## 首次启动预期

- 首次运行创建 `%APPDATA%\DufsGui\config.json`，并把内置 dufs 释放到
  `%LOCALAPPDATA%\DufsGui\bin\dufs.exe`
- 默认勾选**第一块已连接网卡**；只有回环可用时才默认「仅本机 · 127.0.0.1」
- 主窗按**最小可用尺寸 960×720** 打开，不记忆上次大小/位置
- 发布包（外壳形态）首次启动解压 payload 到 `%LOCALAPPDATA%\DufsGui\payload\v<版本>\`；
  onefile 每次启动解压到 `%TEMP%\_MEI*`

## 主要能力

| | 说明 |
|---|---|
| 多网卡共享 | 同时勾选多块网卡，每个地址一个 dufs 进程；单地址失败不影响其他，状态栏汇总「N 个中 M 个已启动」 |
| 共享配置 | 目录、网卡、端口（占用自动推荐空闲端口）、URL 前缀；多套「方案」随时切换 |
| 访问口令 | 高级设置里填用户名/口令即启用（`-a user:pass@/:rw`）；**留空即匿名访问**，界面与日志只显示脱敏值 |
| 网页端能力 | 上传 / 删除 / 搜索 / 打包下载 / 符号链接 / CORS，勾选即生效 |
| 网页皮肤 | dufs 官方 assets v0.47.0 + CSS 覆盖层，深色改造；标题与图标可自定义 |
| 界面 | 固定深色、按 macOS 深色 token 排版；圆角、二维码、实时日志与导出 |

完整能力表与每个选项对应的 dufs 参数见 [使用指南 · 界面能配什么](docs/使用指南.md)。

安全默认值：默认勾选第一块已连接网卡、删除默认关闭、符号链接默认关闭并二次确认；
**不填口令即为匿名访问**，同网段任何人都能访问。只想本机使用就在「查看网卡」里只勾 `127.0.0.1`。

## 版本

当前 **v1.6.15**。版本号唯一定义在 [`core/__init__.py`](core/__init__.py)，打包产物名
（`dist\DufsGui-v<版本>.exe`）与构建信息从它派生。GUI 窗口标题固定「Dufs GUI」，
浏览器标签页标题在高级设置「网页外观」里配置。

## 文档

| 文档 | 给谁看 |
|---|---|
| [使用指南](docs/使用指南.md) | **唯一权威**：环境要求、界面配置项、口令、深色界面、排障、日志位置 |
| [打包与供应链](docs/打包与供应链.md) | 构建者：三种产物形态、可复现构建、SHA256SUMS 校验、测试与 CI、逐源哈希 |
| [文档索引](docs/index.md) | 全部页面导航：报告、审计记录、踩坑索引 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发者：架构与关键问题 |
| [问题记录](docs/问题记录/) | 排查具体坑（一坑一篇） |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更 |
| [AGENTS.md](AGENTS.md) | AI / 未来的自己 |

## 已知限制

单实例只能挂一个共享目录；多网卡共享时每地址一个进程（共用端口与目录）；口令以明文存在本地配置，
HTTP 下也明文过网；网页皮肤与 dufs 版本绑定，升级需重新抓取。完整六条（含 POSIX 信号、
单文件模式等）见 [使用指南](docs/使用指南.md)。

## License

本项目代码采用 **MIT**，见 [LICENSE](LICENSE)。

内置/随包下载的 dufs 二进制固定为 **v0.47.0**，来自 [sigoden/dufs](https://github.com/sigoden/dufs)，
上游按 **MIT OR Apache-2.0** 双许可分发；本项目不改变上游许可。
两份许可原文已作为数据文件打进产物：源码树 [`licenses/`](licenses/)，
运行时可在 exe 解压目录的 `licenses/` 下查看（`--selftest` 会列出）。
上游许可：[LICENSE-MIT](https://github.com/sigoden/dufs/blob/v0.47.0/LICENSE-MIT) /
[LICENSE-APACHE](https://github.com/sigoden/dufs/blob/v0.47.0/LICENSE-APACHE)；
dufs 版本与二进制 SHA256 见 [`tools/dufs_checksums.json`](tools/dufs_checksums.json)。
