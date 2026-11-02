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
