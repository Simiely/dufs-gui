# Dufs 文件共享 · GUI 封装

给 [dufs](https://github.com/sigoden/dufs) 套一个 Windows 桌面外壳：选目录、配端口、点一下开启共享，附带深色界面和可选的美化网页端。

**为什么不用命令行**：dufs 本身很优秀，但每次共享都要敲 `dufs D:\xxx -b 10.x.x.x -p 5000 --allow-delete`，参数记不住、端口占用要自己查。这个 GUI 把这些变成勾选框和输入框。

```
┌─ 配置区 ──────────────┬─ 状态与日志 ─────────────┐
│ 共享目录  [D:\...] [浏览] │ ● 未启动                  │
│ 监听地址  [10.4.240.16 ▾] │ http://10.4.240.16:5000/  │
│ 端口      [5000]        │ [打开网页] [复制地址]      │
│ ☑ 允许上传 ☐ 允许删除 …  │ ── 运行日志 ──            │
│ [高级设置…]             │ 17:03:21 dufs 就绪         │
└────────────────────────┴───────────────────────────┘
                          [开启共享] [停止]
```

## 快速开始

**目前尚未发布 Release**。请从源码构建（Windows）：

```bat
git clone https://github.com/Simiely/dufs-gui
cd dufs-gui
build.bat          :: 产出单个 dist\DufsGui-v1.5.0.exe
```

> 环境要求：**python.org 官方 Python 3.12.x**（conda / 嵌入式版的 tcl-tk 路径不一致，会闪退）。
> 路径用纯英文。闪退或打包失败先跑 `build_debug.bat`，它把报错重定向到文件，看得见。

**不想打包，直接跑源码**：

```bat
python tools\fetch_dufs.py    :: 下载 dufs.exe 到 bin\
python main.py
```

## 主要能力

| | 说明 |
|---|---|
| 共享配置 | 目录、监听地址（自动列出本机 IP）、端口（占用自动推荐空闲端口）、URL 前缀 |
| 访问口令 | 高级设置里填写用户名/口令，生成 dufs `-a user:pass@/:rw`；界面预览与日志只显示脱敏值 |
| 网页端能力 | 上传 / 删除 / 搜索 / 打包下载 / 符号链接 / CORS，勾选即生效 |
| 配置方案 | 多套「目录 + 端口 + 能力」存成方案随时切换 |
| 深色模式 | 默认深色，一键切浅色，Windows 标题栏跟随 |
| 日志 | 实时回显，可清空 / 导出 |
| 网页皮肤 | dufs 官方 assets v0.47.0 + CSS 覆盖层：官方 HTML/JS 保证功能，CSS 做深色配色与视觉改造；升级 dufs 后用 `tools/fetch_skin.py` 同步 |

安全默认值：监听默认 `127.0.0.1`（仅本机）、删除默认关闭、符号链接默认关闭并二次确认。
**监听非回环地址（如 `0.0.0.0`）且未设置访问口令时，启动会被直接拒绝**，不再只是提示。

## 版本

当前 **v1.5.0**。版本号唯一定义在 [`core/__init__.py`](core/__init__.py)，
界面标题与打包产物名（`dist\DufsGui-v1.5.0.exe`）都从它派生。

## 测试

```bat
python -m unittest discover -s tests   :: 117 项，1 项自动跳过（皮肤 jsdom E2E）
```

Windows CI 见 [.github/workflows/windows-ci.yml](.github/workflows/windows-ci.yml)，
矩阵为 Python 3.9 / 3.12，只跑标准库 `unittest`。

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
- dufs 单文件模式（分享单个 iso 等）不走目录列表逻辑，网页皮肤不适用
- 网页皮肤基于 dufs 官方 assets v0.47.0；dufs 升级后需用 `tools/fetch_skin.py` 重新抓取，HTML/JS 与 dufs 必须同版本
- 访问口令以**明文**保存在本地配置文件（`%LOCALAPPDATA%\DufsGui\config.json` 或项目 `.dufsgui\config.json`）；HTTP 下口令也以明文经过网络，跨公网共享请自行启用 HTTPS
- 关闭程序会结束 dufs；Windows 下父进程被强杀时由 Job Object 兜底，POSIX 下 SIGKILL 无法捕获（只能覆盖正常退出与 SIGTERM/SIGINT）

## License

本项目代码采用 **MIT**，见 [LICENSE](LICENSE)。

内置/随包下载的 dufs 二进制来自 [sigoden/dufs](https://github.com/sigoden/dufs)，
上游按 **MIT OR Apache-2.0** 授权分发；本项目不改变上游许可。
上游许可全文见 [LICENSE-MIT](https://github.com/sigoden/dufs/blob/main/LICENSE-MIT) /
[LICENSE-APACHE](https://github.com/sigoden/dufs/blob/main/LICENSE-APACHE)。
