---
id: pitfall.child-inherits-dll-path
title: 子进程继承 bootloader 的 DLL 搜索路径，外部 dufs.exe 起不来
summary: PyInstaller 把库搜索路径指向 _MEIPASS，该设置会被 Popen 出来的子进程继承。
type: explanation
kind: pitfall
status: resolved
owner: "@simiely"
topics: [development]
source_type: code
source: core/server.py
last_reviewed: 2026-11-04
symptom: 打包版拉起 dufs.exe 时秒退且无任何输出；源码直接运行同一套参数一切正常。
cause: Windows bootloader 用 SetDllDirectoryW 把搜索路径设为 _MEIPASS，子进程继承后可能加载到不兼容的同名 DLL。
detect: 只在冻结产物复现、进程无输出即退出；对比源码运行结果即可定位。
avoid: Popen 前调 SetDllDirectoryW(None) 并从 PATH 剔除指向 _MEIPASS 的条目，启动后立刻恢复本进程设置。
recover: 同 avoid；已发布版本需要重新打包。
applies_to: [docs.usage]
severity: high
related: []
---
# 问题：子进程继承 DLL 搜索路径，外部 dufs.exe 可能启动失败

**TL;DR**：PyInstaller 在 Windows 上把库搜索路径指向 `_MEIPASS`，该设置会被子进程继承。

- **问题**：冻结后启动外部 dufs.exe，可能秒退且无任何输出
- **根因**：官方文档 *Common Issues and Pitfalls → Launching External Programs*：
  bootloader 用 `SetDllDirectoryW` 将搜索路径设为 `_MEIPASS`，**该设置被子进程继承**，
  外部程序可能加载到不兼容版本的同名 DLL
- **解决**：`subprocess.Popen` 前调 `SetDllDirectoryW(None)`，并从 PATH 中剔除
  锚定 `_MEIPASS` 的条目，启动完立刻恢复本进程设置（本进程还要正常加载 Tk）
- **实现**：`core/server.py` 的 `_unset_dll_directory / _restore_dll_directory / _clean_child_env`
- **预防**：凡是冻结程序用 subprocess 拉外部二进制，都要做这一步
