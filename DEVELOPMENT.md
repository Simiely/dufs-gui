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
- **皮肤不能挡住共享**：网页美化默认关闭，且失败时自动降级

## 二、架构说明

```
main.py            入口，装崩溃兜底后启动 GUI
app.py             DufsGui（tk.Tk 子类）：全部界面与交互
core/
  config.py        ServerConfig 数据类：字段 + 命令行生成 + 校验 + 持久化
  dufsbin.py       dufs.exe 的查找 / 释放 / 安装 / 皮肤目录定位与校验
  server.py        DufsProcess：子进程启停、日志采集、就绪探测、DLL 环境清理
  netutil.py       本机 IP、端口占用检测、空闲端口推荐、前缀规范化
  theme.py         深浅主题配色；ThemedCombobox（下拉列表配色可控）
  winpos.py        弹窗定位（多显示器钳制）
  crashlog.py      sys.excepthook / 线程异常 / tkinter 回调异常 → 落盘
  app_state.py     全局深色状态（避免模块循环依赖）
assets/            自研网页皮肤（index.html / index.css / index.js）
tools/             fetch_dufs.py（下载 dufs）、embed_dufs.py（可选 base64 内嵌）
tests/             37 项单测；tk_stub.py 提供无 tkinter 环境下的桩
```

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
| [弹窗内容被裁切](docs/问题记录/问题：弹窗内容超出固定尺寸被裁切.md) | 按 `winfo_reqheight()` 实测，不写死 |

## 四、与 knowledge-base 的衔接

本仓库的「问题记录」与 knowledge-base 用户库**格式完全一致**，可零转换提炼。
跨项目通用的候选：

- Windows 下 PyInstaller 打包 tkinter 的通用坑（spec 变量 / DLL 继承 / 杀软误报）
- 中文 Windows 批处理编码陷阱
- ttk 深色主题的能力边界（哪些部件根本改不了）
