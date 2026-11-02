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
