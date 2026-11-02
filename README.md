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

**用现成的**：从 Releases 下载 `DufsGui.exe`，双击即用（dufs 已内置）。

**自己打包**（Windows）：

```bat
git clone https://github.com/Simiely/dufs-gui
cd dufs-gui
build.bat          :: 产出单个 dist\DufsGui.exe
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
| 网页端能力 | 上传 / 删除 / 搜索 / 打包下载 / 符号链接 / CORS，勾选即生效 |
| 配置方案 | 多套「目录 + 端口 + 能力」存成方案随时切换 |
| 深色模式 | 默认深色，一键切浅色，Windows 标题栏跟随 |
| 日志 | 实时回显，可清空 / 导出 |
| 网页皮肤 | 基于 dufs 官方 assets：官方 JS 保证功能，CSS 层做深色配色 + 视觉改造；可用 `tools/fetch_skin.py` 随 dufs 升级 |

安全默认值：监听默认 `127.0.0.1`（仅本机）、删除默认关闭、符号链接默认关闭并二次确认。

## 版本

当前 **v1.2.0**。版本号唯一定义在 [`core/__init__.py`](core/__init__.py)，
界面标题与打包产物名（`dist\DufsGui-v1.2.0.exe`）都从它派生。

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
- 网页皮肤为自研前端，若 dufs 未来改动 IndexData 结构需同步

## License

同 dufs：MIT 或 Apache-2.0，二选一。
