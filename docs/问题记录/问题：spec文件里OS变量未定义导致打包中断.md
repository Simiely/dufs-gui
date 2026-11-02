# 问题：spec 文件里 `OS` 变量未定义，打包直接中断

**TL;DR**：PyInstaller 的 .spec 不存在名为 `OS` 的全局变量，写 `if OS == "nt"` 会抛 `NameError` 让打包中止。

- **问题**：`DufsGui.spec` 里用 `if OS == "nt"` 判断系统，双击 build.bat 时打包失败
- **根因**：spec 由 exec 执行，PyInstaller 注入的全局变量只有
  `DISTPATH / HOMEPATH / SPEC / SPECPATH / specnm / workpath / WARNFILE`
  以及 `Analysis / EXE / PYZ / COLLECT / BUNDLE / MERGE / TOC` 等类，**没有 `OS`**
- **解决**：改为 `import os` + `os.name == "nt"`
- **诊断方法**：在 spec 里 `print(globals().keys())` 即可看到真实可用变量
- **预防**：spec 中需要任何系统/路径信息，一律自己 import，不要猜全局变量名
