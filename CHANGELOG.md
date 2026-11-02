# CHANGELOG

本项目版本格式：`主版本.次版本.修订`，按版本倒序分节。
版本号唯一定义在 [`core/__init__.py`](core/__init__.py) 的 `APP_VERSION`，界面标题与打包产物名均从它派生，不要在多处改。

## [1.1.1] - 2026-11-02（commit `367b6c4`）

### 修复

- **等效命令显示被截断**：预览标签写死 `wraplength=760`，而窗口 1020 宽、
  还要放按钮 —— 换行位置与实际宽度不符，命令被截成 `--e --allow-archive` 这类怪样子。
  改为按标签真实宽度自适应
- **复选框勾选依然看不见**：`indicatorcolor` 在部分平台静默失效（不报错、就是没效果）。
  改为**自绘 16x16 位图指示器**（`element_create` 替换 `Checkbutton.indicator`），
  颜色完全自控，任何主题下都必然可见：未选中深底描边，选中蓝底白勾
- **主题切换时高级设置弹窗不跟随**：Canvas 是原生 tk 控件，`ttk.Style` 管不到。
  切换主题时一并刷新弹窗与它的画布底色

### 测试

- 新增 3 项源码级回归（不写死 wraplength / 走自绘指示器 / 对勾像素不越界）
- 测试 41 -> 44 项

## [1.1.0] - 2026-11-02（commit `e7d3c66`）

### 变更

- **版本号收归单一真源**：`core/__init__.py` 的 `APP_VERSION`。
  界面标题、打包产物名（`DufsGui-v1.1.0.exe`）全部从它派生，避免多处不同步
- **打包产物名带版本号**：`dist\DufsGui-v1.1.0.exe`，便于区分新旧版本
- `build.bat` / `build_debug.bat` 改为通配定位产物，自动适配带版本号的 exe

### 文档

- 按 knowledge-base 单项目规范建立四件套（README / AGENTS / DEVELOPMENT / CHANGELOG）
- README 原 252 行超 150 行阈值 → 精简为门面 + 索引，详情移入 `docs/使用指南.md`
- 新增 `docs/问题记录/` 六篇，一坑一篇

## [1.0.0] - 2026-11-02（commit `e4b8cac`）

首个可用版本。完成四件套（README / AGENTS / DEVELOPMENT / CHANGELOG）重写。

### 新增

- 单站点共享配置：目录、监听地址（自动列出本机 IP）、端口、URL 路径前缀
- 网页端能力勾选：上传 / 删除 / 搜索 / 打包下载 / 符号链接 / CORS
- 配置方案管理：多套「目录 + 端口 + 能力」保存与切换，最近目录记忆
- 深色 / 浅色主题，Windows 标题栏跟随
- 服务状态、实时日志（清空 / 导出）、打开网页、复制地址
- 底部实时显示等效 dufs 命令行
- 崩溃落盘（`%LOCALAPPDATA%\DufsGui\crash.log`）与 `--selftest` 自检
- 一键打包脚本：`build.bat`（单文件）、`build_debug.bat`（诊断）、`run_debug.bat`
- 自研网页皮肤 `assets/`（默认关闭，可指向第三方皮肤包）
- 37 项单元测试

### 修复

- spec 中 `OS` 全局变量不存在导致打包中断 → 改用 `import os`
- 所有 bat 改为纯 ASCII，解决中文 UTF-8 被 cmd 当命令执行
- dufs 因 `--assets` 目录缺 `index.html` 拒绝启动 → 补齐三件套 + 三重校验 + 自动降级
- 子进程继承 bootloader 的 DLL 搜索路径 → `Popen` 前清理
- 下拉列表 / 复选框在深色下不可见 → 分别按原生 Listbox 与 clam 硬编码对勾处理
- 弹窗写死尺寸导致内容裁切 → 按内容实测高度 + 可滚动
- 移除重复的 `ui_queue` 残留引用导致的 `AttributeError`

### 已知限制

- 单实例只能挂一个共享目录（dufs 限制）
- dufs 单文件模式不适用自研网页皮肤
- Linux 沙盒无 tkinter，GUI 渲染与网页观感未经端到端验证
