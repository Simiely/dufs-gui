---
id: docs.generated.index
title: 生成索引
summary: 从 frontmatter 自动生成的导航；勿手改。
type: reference
kind: index
status: active
owner: "@platform"
source_type: doc
source: schema/taxonomy.json
last_reviewed: 2026-11-11
related: []
---

# 生成索引

> 生成文件，勿手改。运行 `python tools/repo-kit/generate.py --root . --write` 重建。

## 按 type

### how-to

| 页面 | kind | status | owner | tier | source |
|---|---|---|---|---|---|
| [使用指南：配置项、打包流程与排障的完整说明](../使用指南.md) | standard | active | @simiely | normal | `core/launch.py` |

### reference

| 页面 | kind | status | owner | tier | source |
|---|---|---|---|---|---|
| [Dufs GUI 文档索引](../index.md) | index | active | @simiely | normal | `README.md` |

## Reports

| 页面 | status | owner | tier | source |
|---|---|---|---|---|
| [2026-11-16 文档审计：按单项目规范 2.1.1 迁移与 8 处内容纠偏](../audits/2026-11-16-dufs-gui.md) | archived | @simiely | normal | `CHANGELOG.md` |
| [第 6 批改造报告：网页标题、站点图标、圆角与版本号](../round-report.md) | archived | @simiely | normal | `CHANGELOG.md` |
| [启动实测：单文件外壳 + onedir 落地缓存的取舍依据](../startup-benchmark-20261104.md) | archived | @simiely | normal | `CHANGELOG.md` |

## Pitfalls

| 坑 | severity | 症状 | applies_to | status |
|---|---|---|---|---|
| [dufs 因 --assets 目录缺 index.html 直接拒绝启动](../问题记录/问题：dufs因assets目录缺少index.html拒绝启动.md) | high | 勾选「网页美化界面」后共享启动失败，取消勾选则一切正常，日志里没有更多线索。 | `docs.usage` | resolved |
| [子进程继承 bootloader 的 DLL 搜索路径，外部 dufs.exe 起不来](../问题记录/问题：子进程继承DLL搜索路径导致dufs无法启动.md) | high | 打包版拉起 dufs.exe 时秒退且无任何输出；源码直接运行同一套参数一切正常。 | `docs.usage` | resolved |
| [弹窗写死尺寸，新增控件后底部被裁掉](../问题记录/问题：弹窗内容超出固定尺寸被裁切.md) | low | 高级设置弹窗底部（dufs 程序那一行）看不见，新增的说明文字被切掉。 | `docs.usage` | resolved |
| [中文 .bat 存成 UTF-8 会被 cmd 逐行当命令执行](../问题记录/问题：UTF-8编码的中文bat被cmd当成命令执行.md) | medium | 双击后满屏「'鍗充娇涓€闂' 不是内部或外部命令」，脚本不执行，后续步骤全部跳过。 | `docs.usage` | resolved |
| [spec 文件里没有 OS 全局变量，写了就 NameError 中断打包](../问题记录/问题：spec文件里OS变量未定义导致打包中断.md) | medium | 双击 build.bat 打包直接中断，报 NameError: name 'OS' is not defined。 | `docs.usage` | resolved |
| [ttk 下拉弹层与勾选框的配色不吃 ttk.Style](../问题记录/问题：ttk下拉列表与复选框在深色下不可见.md) | medium | 深色界面下下拉箭头看不见、勾选态分辨不出；改 ttk.Style 毫无反应且不报错。 | `docs.usage` | resolved |

## 全部页面

| id | 标题 | type | kind | status |
|---|---|---|---|---|
| `docs.index` | [Dufs GUI 文档索引](../index.md) | reference | index | active |
| `docs.usage` | [使用指南：配置项、打包流程与排障的完整说明](../使用指南.md) | how-to | standard | active |
| `pitfall.assets-needs-index-html` | [dufs 因 --assets 目录缺 index.html 直接拒绝启动](../问题记录/问题：dufs因assets目录缺少index.html拒绝启动.md) | explanation | pitfall | resolved |
| `pitfall.bat-utf8-cmd` | [中文 .bat 存成 UTF-8 会被 cmd 逐行当命令执行](../问题记录/问题：UTF-8编码的中文bat被cmd当成命令执行.md) | explanation | pitfall | resolved |
| `pitfall.child-inherits-dll-path` | [子进程继承 bootloader 的 DLL 搜索路径，外部 dufs.exe 起不来](../问题记录/问题：子进程继承DLL搜索路径导致dufs无法启动.md) | explanation | pitfall | resolved |
| `pitfall.dialog-fixed-size` | [弹窗写死尺寸，新增控件后底部被裁掉](../问题记录/问题：弹窗内容超出固定尺寸被裁切.md) | explanation | pitfall | resolved |
| `pitfall.spec-os-undefined` | [spec 文件里没有 OS 全局变量，写了就 NameError 中断打包](../问题记录/问题：spec文件里OS变量未定义导致打包中断.md) | explanation | pitfall | resolved |
| `pitfall.ttk-dark-widgets` | [ttk 下拉弹层与勾选框的配色不吃 ttk.Style](../问题记录/问题：ttk下拉列表与复选框在深色下不可见.md) | explanation | pitfall | resolved |
| `report.audit-20261116` | [2026-11-16 文档审计：按单项目规范 2.1.1 迁移与 8 处内容纠偏](../audits/2026-11-16-dufs-gui.md) | explanation | report | archived |
| `report.round6` | [第 6 批改造报告：网页标题、站点图标、圆角与版本号](../round-report.md) | explanation | report | archived |
| `report.startup-benchmark` | [启动实测：单文件外壳 + onedir 落地缓存的取舍依据](../startup-benchmark-20261104.md) | explanation | report | archived |
