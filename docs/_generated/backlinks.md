---
id: docs.generated.backlinks
title: 反向链接
summary: 从 related 与 pitfall 的 applies_to 自动派生的反向链接；勿手改。
type: reference
kind: index
status: active
owner: "@platform"
source_type: doc
source: schema/taxonomy.json
last_reviewed: 2026-11-11
related: []
---

# 反向链接

> 生成文件，勿手改。方向性关系只存一侧，本页是派生结果；对称关系按规范边去重。
> `applies_to` 是 pitfall 的专用字段，可指向页面 id 或技能 name；技能没有页面可链，故只出现在目标列。

| 目标 id / 技能 | 来源 id | 关系 | 来源页面 |
|---|---|---|---|
| `docs.usage` | [dufs 因 --assets 目录缺 index.html 直接拒绝启动](../问题记录/问题：dufs因assets目录缺少index.html拒绝启动.md) | applies-to（反向：has-pitfall；来自 applies_to 字段） | `docs/问题记录/问题：dufs因assets目录缺少index.html拒绝启动.md` |
| `docs.usage` | [中文 .bat 存成 UTF-8 会被 cmd 逐行当命令执行](../问题记录/问题：UTF-8编码的中文bat被cmd当成命令执行.md) | applies-to（反向：has-pitfall；来自 applies_to 字段） | `docs/问题记录/问题：UTF-8编码的中文bat被cmd当成命令执行.md` |
| `docs.usage` | [子进程继承 bootloader 的 DLL 搜索路径，外部 dufs.exe 起不来](../问题记录/问题：子进程继承DLL搜索路径导致dufs无法启动.md) | applies-to（反向：has-pitfall；来自 applies_to 字段） | `docs/问题记录/问题：子进程继承DLL搜索路径导致dufs无法启动.md` |
| `docs.usage` | [弹窗写死尺寸，新增控件后底部被裁掉](../问题记录/问题：弹窗内容超出固定尺寸被裁切.md) | applies-to（反向：has-pitfall；来自 applies_to 字段） | `docs/问题记录/问题：弹窗内容超出固定尺寸被裁切.md` |
| `docs.usage` | [spec 文件里没有 OS 全局变量，写了就 NameError 中断打包](../问题记录/问题：spec文件里OS变量未定义导致打包中断.md) | applies-to（反向：has-pitfall；来自 applies_to 字段） | `docs/问题记录/问题：spec文件里OS变量未定义导致打包中断.md` |
| `docs.usage` | [ttk 下拉弹层与勾选框的配色不吃 ttk.Style](../问题记录/问题：ttk下拉列表与复选框在深色下不可见.md) | applies-to（反向：has-pitfall；来自 applies_to 字段） | `docs/问题记录/问题：ttk下拉列表与复选框在深色下不可见.md` |
