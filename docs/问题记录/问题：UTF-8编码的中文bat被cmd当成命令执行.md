---
id: pitfall.bat-utf8-cmd
title: 中文 .bat 存成 UTF-8 会被 cmd 逐行当命令执行
summary: 中文 Windows 的 cmd 按代码页解码批处理，UTF-8 汉字解成乱码碎片后落在命令名位置。
type: explanation
kind: pitfall
status: resolved
owner: "@simiely"
topics: [development]
source_type: code
source: build.bat
last_reviewed: 2026-11-04
symptom: 双击后满屏「'鍗充娇涓€闂' 不是内部或外部命令」，脚本不执行，后续步骤全部跳过。
cause: cmd 按当前代码页逐行解码 bat；UTF-8 一个汉字 3 字节，用 GBK 解得 1.5 个字，剩下碎片正好落在命令名位置。
detect: 首屏出现乱码命令名即可判定；用编辑器或 `file -i *.bat` 确认编码不是 ASCII。
avoid: 所有 bat 存纯 ASCII；确需中文就另存为 ANSI(GBK)；不要指望 chcp 65001 补救，它在文件开头之后才生效。
recover: 用编辑器另存为 ASCII 或 ANSI 后重跑；已发布产物需重新打包。
applies_to: [docs.usage]
severity: medium
related: []
---
# 问题：UTF-8 编码的中文 .bat 被 cmd 当成命令执行

**TL;DR**：Windows 中文 cmd 默认按 GBK 读批处理，UTF-8 中文被解成乱码后逐行当命令跑。

- **问题**：双击中文 bat 后满屏 `'鍗充娇涓€闂€岃繃' 不是内部或外部命令`
- **根因**：cmd 是逐行读、按当前代码页即时转换的。UTF-8 的一个汉字 3 字节，
  用 GBK 解会变成 1.5 个汉字，剩下的碎片正好落在命令名位置上
- **解决**：本项目所有 bat 改为**纯 ASCII 英文**（最稳，任何代码页都不乱）；
  若坚持中文，记事本另存为时编码选 **ANSI**（不是 UTF-8）
- **注意**：`chcp 65001` 救不了——它在文件开头之后才生效，前面的内容已经错了
- **预防**：新增 bat 一律纯 ASCII；CI 可加一条「bat 文件必须是 ASCII」的检查
