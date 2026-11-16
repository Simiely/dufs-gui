---
id: pitfall.ttk-dark-widgets
title: ttk 下拉弹层与勾选框的配色不吃 ttk.Style
summary: 下拉是原生 tk.Listbox，clam 的对勾是硬编码深色，两条都不能用 ttk 主题改。
type: explanation
kind: pitfall
status: resolved
owner: "@simiely"
topics: [development]
source_type: code
source: core/theme.py
last_reviewed: 2026-11-04
symptom: 深色界面下下拉箭头看不见、勾选态分辨不出；改 ttk.Style 毫无反应且不报错。
cause: Combobox 的弹层是原生 tk.Listbox，不受 ttk 主题管；clam 主题的对勾颜色写死，indicatorcolor 在部分版本静默失效。
detect: 目视下拉弹层与勾选态；若改完样式无任何变化，即命中此类。
avoid: 下拉用 option database（键名大小写敏感）并在初始化时 tk.eval 刷已存在列表；勾选改用 tk.Checkbutton + indicatoron=False + 自绘图片。
recover: 按上述替换控件；不要在 ttk.Style 上继续加配置。
applies_to: [docs.usage]
severity: medium
related: []
---
# 问题：ttk 下拉列表与复选框在深色主题下看不清

**TL;DR**：下拉列表不是 ttk 控件、复选框对勾是硬编码深色，两者的配色都不能用 `ttk.Style` 改。

- **问题**：① 下拉箭头黑色叠在深色背景上看不见 ② 勾选状态分辨不出
- **根因**
  - **Combobox**：下拉部分是**原生 `tk.Listbox`，不是 ttk 控件**，`ttk::style` 完全无效。
    只能用 option database，且**大小写敏感**——`selectBackground` 的 B 必须大写，
    写成 `selectbackground` 会静默失效（不报错，就是没效果）。
    另外 `option_add` 只在 widget 创建**前**可靠生效，运行时切主题属于"之后"
  - **Checkbutton**：clam 主题下**对勾是硬编码深色**，无任何配置项可改其颜色
- **解决**
  - 下拉：`arrowcolor` 显式设前景色 + 正确大小写的 `option_add` +
    用 `tk.eval` 直接给已存在的 popdown Listbox 上色（见 `core/theme.py` 的 `ThemedCombobox`）
  - 勾选：让**选中态方框填成高亮 accent 色**，深色对勾落在亮底上；
    未选中用 `bordercolor` 勾轮廓；`indicatordiameter` 放大到 16
- **预防**：改动 ttk 深色主题时，先确认目标部件是否为"原生 Tk 控件"
