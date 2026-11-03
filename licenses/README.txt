内嵌 dufs 的上游许可说明
=========================

项目：dufs（https://github.com/sigoden/dufs）
版本：v0.47.0（与 tools/dufs_checksums.json 的 pinned_version 一致）
许可：MIT OR Apache-2.0（双许可，使用者可任选其一）

本目录随打包产物一起分发，供审计与合规核对：

- dufs-LICENSE-MIT     上游 LICENSE-MIT 原文
- dufs-LICENSE-APACHE  上游 LICENSE-APACHE 原文

文本取自 https://github.com/sigoden/dufs/tree/v0.47.0（2026-11-03 获取）。
本项目只把 dufs 作为独立子进程调用，不修改其二进制，也不改变上游许可。
dufs.exe 的 SHA256 见 tools/dufs_checksums.json；打包产物内的
BUILD-INFO.txt / SHA256SUMS 由 tools/build_info.py 生成。
