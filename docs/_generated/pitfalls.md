---
id: docs.generated.pitfalls
title: 踩坑索引
summary: 从 kind=pitfall 页面自动生成的失败模式索引；勿手改。
type: reference
kind: index
status: active
owner: "@platform"
source_type: doc
source: schema/taxonomy.json
last_reviewed: 2026-11-11
related: []
---

# 踩坑索引

> 生成文件，勿手改。运行 `python tools/repo-kit/generate.py --root . --write` 重建。
> 每个坑的权威内容在它自己的页面；本页只做导航。

## 未解决（0）

（无）

## 已解决（6）

| 严重度 | 坑 | 症状 | 适用 |
|---|---|---|---|
| high | [dufs 因 --assets 目录缺 index.html 直接拒绝启动](../问题记录/问题：dufs因assets目录缺少index.html拒绝启动.md) | 勾选「网页美化界面」后共享启动失败，取消勾选则一切正常，日志里没有更多线索。 | `docs.usage` |
| high | [子进程继承 bootloader 的 DLL 搜索路径，外部 dufs.exe 起不来](../问题记录/问题：子进程继承DLL搜索路径导致dufs无法启动.md) | 打包版拉起 dufs.exe 时秒退且无任何输出；源码直接运行同一套参数一切正常。 | `docs.usage` |
| medium | [中文 .bat 存成 UTF-8 会被 cmd 逐行当命令执行](../问题记录/问题：UTF-8编码的中文bat被cmd当成命令执行.md) | 双击后满屏「'鍗充娇涓€闂' 不是内部或外部命令」，脚本不执行，后续步骤全部跳过。 | `docs.usage` |
| medium | [spec 文件里没有 OS 全局变量，写了就 NameError 中断打包](../问题记录/问题：spec文件里OS变量未定义导致打包中断.md) | 双击 build.bat 打包直接中断，报 NameError: name 'OS' is not defined。 | `docs.usage` |
| medium | [ttk 下拉弹层与勾选框的配色不吃 ttk.Style](../问题记录/问题：ttk下拉列表与复选框在深色下不可见.md) | 深色界面下下拉箭头看不见、勾选态分辨不出；改 ttk.Style 毫无反应且不报错。 | `docs.usage` |
| low | [弹窗写死尺寸，新增控件后底部被裁掉](../问题记录/问题：弹窗内容超出固定尺寸被裁切.md) | 高级设置弹窗底部（dufs 程序那一行）看不见，新增的说明文字被切掉。 | `docs.usage` |

## 按适用范围

### `docs.usage`

- [dufs 因 --assets 目录缺 index.html 直接拒绝启动](../问题记录/问题：dufs因assets目录缺少index.html拒绝启动.md)（high）
- [子进程继承 bootloader 的 DLL 搜索路径，外部 dufs.exe 起不来](../问题记录/问题：子进程继承DLL搜索路径导致dufs无法启动.md)（high）
- [中文 .bat 存成 UTF-8 会被 cmd 逐行当命令执行](../问题记录/问题：UTF-8编码的中文bat被cmd当成命令执行.md)（medium）
- [spec 文件里没有 OS 全局变量，写了就 NameError 中断打包](../问题记录/问题：spec文件里OS变量未定义导致打包中断.md)（medium）
- [ttk 下拉弹层与勾选框的配色不吃 ttk.Style](../问题记录/问题：ttk下拉列表与复选框在深色下不可见.md)（medium）
- [弹窗写死尺寸，新增控件后底部被裁掉](../问题记录/问题：弹窗内容超出固定尺寸被裁切.md)（low）
