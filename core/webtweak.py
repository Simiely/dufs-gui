"""网页标题、站点图标与界面文案的运行时覆盖。

证据链：dufs 的 ``--assets`` 目录同时提供 ``index.html`` / ``index.js`` /
``index.css`` / ``favicon.ico``，页面通过 ``__ASSETS_PREFIX__`` 引用它们；
``index.js`` 里有三处 ``document.title = `... - Dufs` ``` 决定浏览器标签标题。
因此不改 ``tools/fetch_skin.py`` 拉取的仓库资产，而是在用户目录生成一份覆盖
副本：复制官方资产 → 注入标题常量 → 汉化固定界面文案 → 去掉顶部彩条 →
替换 ``favicon.ico``。

只替换源码里的固定文案字面量（按钮/菜单/空列表/上传提示等），不动文件名、
用户数据与服务器返回的错误文本；官方皮肤结构变化时整文件跳过并写日志，
避免出现中英混杂的半成品。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from .dufsbin import app_data_dir, resource_dir

MAX_TITLE_LEN = 48
_TITLE_CONST = "__DUFS_GUI_TITLE"
_OFFICIAL_TITLES = {
    "index": "document.title = `Index of ${DATA.href} - Dufs`;",
    "edit": "document.title = `Edit ${DATA.href} - Dufs`;",
    "view": "document.title = `View ${DATA.href} - Dufs`;",
}

#: index.js 里的固定界面文案：(原文, 译文, 原文应出现的次数)。
#: 不收录文件名/用户数据（${...} 插值原样保留），也不翻译服务端错误。
_JS_I18N: tuple[tuple[str, str, int], ...] = (
    ('alert("No data");', 'alert("页面数据缺失，请刷新重试");', 1),
    ("'No results'", "'没有匹配结果'", 1),
    ("'Empty folder'", "'空文件夹'", 1),
    ("'Folder will be created when a file is uploaded'",
     "'上传文件后将自动创建此文件夹'", 1),
    ("`Index of ${DATA.href} - Dufs`", "`目录 ${DATA.href} · Dufs`", 1),
    ("`Edit ${DATA.href} - Dufs`", "`编辑 ${DATA.href} · Dufs`", 1),
    ("`View ${DATA.href} - Dufs`", "`预览 ${DATA.href} · Dufs`", 1),
    ('title="Retry"', 'title="重试"', 1),
    ('title="Root"', 'title="根目录"', 1),
    ('$download.title = "Download folder as a .zip file";',
     '$download.title = "将文件夹打包为 .zip 下载";', 1),
    ('title="Download folder as a .zip file"',
     'title="将文件夹打包为 .zip 下载"', 1),
    ('title="Download file"', 'title="下载文件"', 1),
    ('title="Move & Rename"', 'title="移动 / 重命名"', 1),
    ('title="Edit file"', 'title="编辑文件"', 1),
    ('title="Delete"', 'title="删除"', 1),
    ('title="View file"', 'title="查看文件"', 1),
    ('text: "Name",', 'text: "名称",', 1),
    ('text: "Last Modified",', 'text: "修改时间",', 1),
    ('text: "Size",', 'text: "大小",', 1),
    ('<th class="cell-actions">Actions</th>', '<th class="cell-actions">操作</th>', 1),
    ('"Failed to fetch token"', '"获取下载令牌失败"', 1),
    ("`Failed to download, ${err.message}`",
     "`下载失败：${err.message}`", 1),
    ('prompt("Enter folder name")', 'prompt("输入文件夹名称")', 1),
    ('prompt("Enter file name")', 'prompt("输入文件名称")', 1),
    ('"Cannot edit because file is too large or binary."',
     '"文件过大或为二进制格式，无法编辑。"', 1),
    ("`Failed to get file, ${err.message}`",
     "`读取文件失败：${err.message}`", 1),
    ("`Delete \\`${name}\\`?`", "`删除「${name}」？`", 1),
    ("`Cannot delete \\`${file.name}\\`, ${err.message}`",
     "`无法删除「${file.name}」：${err.message}`", 1),
    ('prompt("Enter new path", filePath)', 'prompt("输入新路径", filePath)', 1),
    ('confirm("Override existing file?")', 'confirm("覆盖已存在的文件？")', 1),
    ("`Cannot move \\`${filePath}\\` to \\`${newPath}\\`, ${err.message}`",
     "`无法移动「${filePath}」到「${newPath}」：${err.message}`", 1),
    ("`Failed to save file, ${err.message}`",
     "`保存文件失败：${err.message}`", 1),
    ("`Cannot create folder \\`${name}\\`, ${err.message}`",
     "`无法创建文件夹「${name}」：${err.message}`", 1),
    ("`Cannot create file \\`${name}\\`, ${err.message}`",
     "`无法创建文件「${name}」：${err.message}`", 1),
    ('const unit = size === 1 ? "item" : "items";', 'const unit = "项";', 1),
    ("`Invalid status ${res.status}`", "`HTTP 状态异常：${res.status}`", 1),
)

#: index.html 里的固定属性/文案（含上传任务表头）。
_HTML_I18N: tuple[tuple[str, str, int], ...] = (
    ('lang="en-US"', 'lang="zh-CN"', 1),
    ('title="Download file"', 'title="下载文件"', 1),
    ('title="Move & Rename"', 'title="移动 / 重命名"', 1),
    ('title="Delete"', 'title="删除"', 1),
    ('title="Upload files/folders"', 'title="上传文件 / 文件夹"', 2),
    ('title="New folder"', 'title="新建文件夹"', 1),
    ('title="New File"', 'title="新建文件"', 1),
    ('title="Searching for folders or files"', 'title="搜索文件夹或文件"', 1),
    ('title="Login"', 'title="登录"', 1),
    ('title="Logout"', 'title="退出登录"', 1),
    ('title="Save file"', 'title="保存文件"', 1),
    ('<th class="cell-name" colspan="2">Uploaders</th>',
     '<th class="cell-name" colspan="2">上传任务</th>', 1),
    ('aria-label="Editor"', 'aria-label="编辑器"', 1),
)

#: 顶部彩条覆盖 + 操作按钮样式：官方 ``body::before`` 是 3px 渐变；
#: 官方 ``.action-btn`` 是 26x26 纯图标。只在运行时副本末尾追加覆盖，
#: 皮肤重新 fetch 也不丢。
_TOP_BAR_OVERRIDE = """
/* ===== DufsGui 运行时覆盖（每次启动重新生成，不修改仓库资产）===== */
/* 顶栏内容与文件列表左缘对齐：.main 内容宽 1280 + 左右各 22px 内边距，
   宽屏时随列表一起居中；≤640 时两者同为 12px。背景仍铺满整条顶栏 */
.head {
  padding-left: calc(22px + max(0px, (100% - 1324px) / 2));
  padding-right: calc(22px + max(0px, (100% - 1324px) / 2));
}
@media (max-width: 640px) {
  .head { padding-left: 12px; padding-right: 12px; }
}

/* 移除顶部渐变彩条：与页面背景同色，深色下不出现亮色断层 */
body::before {
  content: none !important;
  display: none !important;
  height: 0 !important;
  background: none !important;
}

/* 操作列：图标 + 文字的描边圆角小按钮，间距 8px */
.paths-table .cell-actions {
  width: auto;
  display: table-cell;
  white-space: nowrap;
  vertical-align: middle;
  padding-left: 14px;
}
.paths-table .cell-actions .action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: auto;
  height: 26px;
  padding: 0 8px;
  margin-left: 8px;
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1;
  text-decoration: none;
  cursor: pointer;
  vertical-align: middle;
  transition: background .13s ease, border-color .13s ease, color .13s ease;
}
.paths-table .cell-actions .action-btn:first-child { margin-left: 0; }
.paths-table .cell-actions .action-btn:hover {
  background: #2c2c2e;
  border-color: var(--text-accent);
  color: var(--text-primary);
}
.paths-table .cell-actions .action-btn:focus-visible {
  outline: 2px solid var(--text-accent);
  outline-offset: 1px;
}
.paths-table .cell-actions .action-btn svg {
  width: 14px;
  height: 14px;
  flex: none;
}
.paths-table .cell-actions .action-btn .act-text { white-space: nowrap; }

/* 窄窗口放不下文字时只留图标，语义由 aria-label 保留 */
@media (max-width: 1080px) {
  /* 官方 .path a 在 >=768px 有 min-width:400px，会把名称列撑到表格溢出 */
  .paths-table .cell-name a { min-width: 0; }
  .paths-table .cell-actions .action-btn {
    width: 28px;
    padding: 0;
    margin-left: 6px;
  }
  .paths-table .cell-actions .action-btn:first-child { margin-left: 0; }
  .paths-table .cell-actions .action-btn .act-text { display: none; }
}

/* 顶栏工具按钮（左：下载/上传/新建/移动/删除，右：登录/保存）：
   桌面态图标 + 文字，与操作列同一套描边圆角；DOM 里文字在图标前，故 reverse */
.toolbox .control.has-text,
.toolbox-right .has-text {
  flex-direction: row-reverse;
  width: auto;
  height: 30px;
  padding: 0 9px;
  gap: 6px;
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
  transition: background .13s ease, border-color .13s ease, color .13s ease;
}
.toolbox .control.has-text:hover,
.toolbox-right .has-text:hover {
  background: #2c2c2e;
  border-color: var(--text-accent);
  color: var(--text-primary);
}
.toolbox .control.has-text svg,
.toolbox-right .has-text svg { width: 14px; height: 14px; flex: none; }
.toolbox .control.has-text .act-text,
.toolbox-right .has-text .act-text { white-space: nowrap; }
/* 上传按钮的点击热区是 label：让图标与文字一起横排、整块可点 */
.toolbox .control.has-text > label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 100%;
}

@media (max-width: 1080px) {
  .toolbox .control.has-text,
  .toolbox-right .has-text { width: 30px; padding: 0; gap: 0; }
  .toolbox .control.has-text .act-text,
  .toolbox-right .has-text .act-text { display: none; }
}

/* ===== 自绘对话框：替换原生 confirm/prompt/alert ===== */
.dg-mask {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(0, 0, 0, .55);
}
.dg-modal {
  width: min(380px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  overflow: auto;
  box-sizing: border-box;
  padding: 16px;
  border: 1px solid var(--border-secondary);
  border-radius: 12px;
  background: #2c2c2e;
  color: var(--text-primary);
  box-shadow: 0 16px 48px rgba(0, 0, 0, .45);
}
.dg-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}
.dg-message {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.dg-input {
  width: 100%;
  height: 32px;
  margin-top: 12px;
  padding: 0 10px;
  box-sizing: border-box;
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
  background: #1b1e23;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.dg-input:focus {
  border-color: var(--text-accent);
  box-shadow: 0 0 0 2px rgba(79, 156, 249, .18);
}
.dg-input.dg-invalid { border-color: #f0a35e; }
.dg-input::selection {
  background: rgba(79, 156, 249, .35);
  color: var(--text-primary);
}
.dg-error {
  min-height: 16px;
  margin-top: 6px;
  color: #f0a35e;
  font-size: 11.5px;
}
.dg-count {
  margin-top: 10px;
  color: var(--text-accent);
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  letter-spacing: .02em;
}
.dg-modal:focus { outline: none; }
.dg-btn:focus { outline: none; }
.dg-btn:focus-visible { box-shadow: 0 0 0 2px rgba(10, 132, 255, .45); }
.dg-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.dg-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}
.dg-btn:hover {
  background: #3a3a3c;
  color: var(--text-primary);
}
.dg-btn:focus-visible {
  outline: 2px solid var(--text-accent);
  outline-offset: 1px;
}
.dg-btn-primary {
  border-color: var(--text-accent);
  background: rgba(79, 156, 249, .12);
  color: var(--text-primary);
}
.dg-btn-primary:hover { background: rgba(79, 156, 249, .22); }
"""

#: 站点图标：dufs 官方引用 ``__ASSETS_PREFIX__favicon.ico``。
#: 覆盖副本改成内联 SVG data URI，图形与应用图标（assets/app.svg）同一份，
#: 不依赖外部文件、不会 404。
_FAVICON_LINK = ('<link rel="icon" type="image/x-icon" '
                 'href="__ASSETS_PREFIX__favicon.ico">')

#: 重命名图标：铅笔 + 基线，与"移动"箭头、"编辑"文档图标区分。
_RENAME_ICON = (
    '<svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" '
    'aria-hidden="true"><path d="M1 13h14v1.1H1z"/>'
    '<path d="M12.2 1.6l2.2 2.2-8.7 8.7-3 .8.8-3z"/></svg>'
)



def sanitize_title(value: str) -> str:
    """去掉控制字符并裁剪空白；空串表示使用 dufs 官方标题。"""
    cleaned = "".join(ch for ch in str(value or "")
                      if ch.isprintable() and ch not in "\r\n\t")
    return cleaned.strip()


def check_title(value: str) -> tuple[bool, str]:
    """校验网页标题，返回 (通过, 清洗后的值/错误说明)。"""
    title = sanitize_title(value)
    if len(title) > MAX_TITLE_LEN:
        return False, f"网页标题最多 {MAX_TITLE_LEN} 个字符"
    return True, title


def _js_string(value: str) -> str | None:
    """生成安全的 JS 字符串字面量；U+2028/2029 在旧解析器里会断行。"""
    if "\u2028" in value or "\u2029" in value:
        return None
    return json.dumps(value, ensure_ascii=False)


def patch_index_js(js: str, title: str) -> tuple[str | None, str]:
    """把三处官方 ``document.title`` 改成「自定义标题优先，空值回落官方」。

    只认官方三条原文；任何一条缺失都说明上游结构变了，直接拒绝改写，
    避免把页面脚本改坏（dufs 端不会报错，只会白屏）。
    """
    literal = _js_string(title)
    if literal is None:
        return None, "网页标题包含不支持的字符"
    missing = [k for k, v in _OFFICIAL_TITLES.items() if js.count(v) != 1]
    if missing:
        return None, (f"官方 index.js 结构已变化（{', '.join(missing)} 处标题语句"
                      "缺失或重复），未覆盖网页标题")
    patched = f"const {_TITLE_CONST} = {literal};\n" + js
    t = _TITLE_CONST
    patched = patched.replace(
        _OFFICIAL_TITLES["index"],
        "document.title = " + t + " || `Index of ${DATA.href} - Dufs`;")
    patched = patched.replace(
        _OFFICIAL_TITLES["edit"],
        "document.title = " + t
        + " ? `${" + t + "} · 编辑` : `Edit ${DATA.href} - Dufs`;")
    patched = patched.replace(
        _OFFICIAL_TITLES["view"],
        "document.title = " + t
        + " ? `${" + t + "} · 预览` : `View ${DATA.href} - Dufs`;")
    return patched, f"网页标题已注入：{title}"


def _apply_i18n(text: str, table: tuple[tuple[str, str, int], ...],
                label: str) -> tuple[str | None, str]:
    """逐条核验锚点次数后整体替换；任何一条对不上就不改，避免半汉化。"""
    missing = []
    for original, _replacement, expected in table:
        actual = text.count(original)
        if actual != expected:
            missing.append(f"{original[:48]!r} 出现 {actual} 次（应为 {expected} 次）")
    if missing:
        return None, (f"{label} 结构已变化，未汉化（{len(missing)} 处不符："
                      + "；".join(missing[:3]) + "）")
    for original, replacement, _expected in table:
        text = text.replace(original, replacement)
    return text, f"{label}已汉化（{len(table)} 处）"


def localize_index_js(js: str) -> tuple[str | None, str]:
    """汉化 index.js 的固定界面文案（按钮提示、空列表、弹窗文本）。"""
    return _apply_i18n(js, _JS_I18N, "网页脚本文案")


def localize_index_html(html: str) -> tuple[str | None, str]:
    """汉化 index.html 的静态 title / aria 文案与上传任务表头。"""
    return _apply_i18n(html, _HTML_I18N, "网页静态文案")


#: 顶栏工具按钮：桌面态图标 + 文字；窄屏由 CSS 只留图标。
#: 锚点是**已汉化**的静态 HTML；每处必须唯一命中，否则整体跳过。
#: DOM 顺序统一为「文字在前、图标在后」，配合 CSS row-reverse 显示成图标 + 文字。
_TOOLBAR_TEXT_PATCHES: tuple[tuple[str, str], ...] = (
    # 左上：打包下载当前目录 / 下载当前文件
    (
        '<a href="" class="control download hidden" title="下载文件" download="">',
        '<a href="" class="control download hidden has-text" title="下载文件" '
        'download="" aria-label="下载"><span class="act-text">下载</span>',
    ),
    # 左上：上传（点击热区是 <label>，文字放进 label 保证整块可点）
    (
        '<div class="control upload-file hidden" title="上传文件 / 文件夹">',
        '<div class="control upload-file hidden has-text" '
        'title="上传文件 / 文件夹" aria-label="上传">',
    ),
    (
        '          </svg>\n        </label>',
        '          </svg><span class="act-text">上传</span>\n        </label>',
    ),
    # 左上：移动 / 重命名（仅编辑页）
    (
        '<div class="control move-file hidden" title="移动 / 重命名">',
        '<div class="control move-file hidden has-text" title="移动 / 重命名" '
        'aria-label="移动"><span class="act-text">移动</span>',
    ),
    # 左上：删除（仅编辑页）
    (
        '<div class="control delete-file hidden" title="删除">',
        '<div class="control delete-file hidden has-text" title="删除" '
        'aria-label="删除"><span class="act-text">删除</span>',
    ),
    # 左上：新建文件夹 / 新建文件
    (
        '<div class="control new-folder hidden" title="新建文件夹">',
        '<div class="control new-folder hidden has-text" title="新建文件夹" '
        'aria-label="新建文件夹"><span class="act-text">新建文件夹</span>',
    ),
    (
        '<div class="control new-file hidden" title="新建文件">',
        '<div class="control new-file hidden has-text" title="新建文件" '
        'aria-label="新建文件"><span class="act-text">新建文件</span>',
    ),
    # 右上：登录（仅启用认证且未登录）
    (
        '<div class="login-btn hidden" title="登录">',
        '<div class="login-btn hidden has-text" title="登录" '
        'aria-label="登录"><span class="act-text">登录</span>',
    ),
    # 右上：保存（仅编辑页且文件可编辑）
    (
        '<div class="save-btn hidden" title="保存文件">',
        '<div class="save-btn hidden has-text" title="保存文件" '
        'aria-label="保存"><span class="act-text">保存</span>',
    ),
)


def patch_toolbar_text(html: str) -> tuple[str | None, str]:
    """把顶栏仍是纯图标的按钮改成图标 + 文字（窄屏由 CSS 隐藏文字）。"""
    text = html
    for old, new in _TOOLBAR_TEXT_PATCHES:
        if text.count(old) != 1:
            return None, "顶栏按钮文字化：锚点未全部唯一命中，跳过"
        text = text.replace(old, new, 1)
    return text, (f"顶栏按钮文字化：已应用（{len(_TOOLBAR_TEXT_PATCHES)} 处，"
                  "下载/上传/新建/移动/删除/登录/保存）")



#: 在**已汉化**的 index.js 上拆出"重命名"，并把操作按钮改成图标 + 文字。
#: 锚点都是汉化后的完整模板片段；任一处缺失就整体跳过（保留官方纯图标）。
_ACTION_PATCHES: tuple[tuple[str, str], ...] = (
    (
        '''      actionDownload = `
      <div class="action-btn">
        <a class="dlwt" href="${url}?zip" title="将文件夹打包为 .zip 下载" download>${ICONS.download}</a>
      </div>`;''',
        '''      actionDownload = `
      <a class="action-btn dlwt" href="${url}?zip" title="将文件夹打包为 .zip 下载" download aria-label="下载">${ICONS.download}<span class="act-text">下载</span></a>`;''',
    ),
    (
        '''    actionDownload = `
    <div class="action-btn" >
      <a class="dlwt" href="${url}" title="下载文件" download>${ICONS.download}</a>
    </div>`;''',
        '''    actionDownload = `
    <a class="action-btn dlwt" href="${url}" title="下载文件" download aria-label="下载">${ICONS.download}<span class="act-text">下载</span></a>`;''',
    ),
    (
        '''  let actionMove = "";''',
        '''  let actionMove = "";
  let actionRename = "";''',
    ),
    (
        '''      actionMove = `<div onclick="movePath(${index})" class="action-btn" id="moveBtn${index}" title="移动 / 重命名">${ICONS.move}</div>`;''',
        '''      actionMove = `<div onclick="movePath(${index})" class="action-btn" id="moveBtn${index}" title="移动" aria-label="移动">${ICONS.move}<span class="act-text">移动</span></div>`;
      actionRename = `<div onclick="renamePath(${index})" class="action-btn" id="renameBtn${index}" title="重命名" aria-label="重命名">${__DUFS_GUI_RENAME_ICON}<span class="act-text">重命名</span></div>`;''',
    ),
    (
        '''        actionEdit = `<a class="action-btn" title="编辑文件" target="_blank" href="${url}?edit">${ICONS.edit}</a>`;''',
        '''        actionEdit = `<a class="action-btn" title="编辑文件" target="_blank" href="${url}?edit" aria-label="编辑">${ICONS.edit}<span class="act-text">编辑</span></a>`;''',
    ),
    (
        '''    actionDelete = `
    <div onclick="deletePath(${index})" class="action-btn" id="deleteBtn${index}" title="删除">${ICONS.delete}</div>`;''',
        '''    actionDelete = `
    <div onclick="deletePath(${index})" class="action-btn" id="deleteBtn${index}" title="删除" aria-label="删除">${ICONS.delete}<span class="act-text">删除</span></div>`;''',
    ),
    (
        '''    actionView = `<a class="action-btn" title="查看文件" target="_blank" href="${url}?view">${ICONS.view}</a>`;''',
        '''    actionView = `<a class="action-btn" title="查看文件" target="_blank" href="${url}?view" aria-label="查看">${ICONS.view}<span class="act-text">查看</span></a>`;''',
    ),
    (
        '''    ${actionMove}
    ${actionDelete}''',
        '''    ${actionMove}
    ${actionRename}
    ${actionDelete}''',
    ),
    (
        '''}


/**
 * Save editor change''',
        '''}


/**
 * Rename path（同一目录内改名，跨目录仍走"移动"）
 * @param {number} index
 */
async function renamePath(index) {
  const file = DATA.paths[index];
  if (!file) return;
  const fileUrl = newUrl(file.name);
  const urlObj = new URL(fileUrl);
  const prefix = DATA.uri_prefix.slice(0, -1);
  const filePath = decodeURIComponent(urlObj.pathname.slice(prefix.length));
  const name = prompt("输入新名称", file.name);
  if (!name || name === file.name) return;
  if (name.includes("/")) {
    alert("名称不能包含「/」，跨目录请使用「移动」");
    return;
  }
  const dir = filePath.split("/").slice(0, -1).join("/");
  const newPath = dir + "/" + name;
  const newFileUrl = urlObj.origin + prefix + newPath.split("/").map(encodeURIComponent).join("/");

  try {
    await checkAuth();
    const res1 = await fetch(newFileUrl, {
      method: "HEAD",
    });
    if (res1.status === 200) {
      if (!confirm("覆盖已存在的文件？")) return;
    }
    const res2 = await fetch(fileUrl, {
      method: "MOVE",
      headers: {
        "Destination": newFileUrl,
      }
    });
    await assertResOK(res2);
    location.href = newFileUrl.split("/").slice(0, -1).join("/");
  } catch (err) {
    alert(`无法重命名「${file.name}」：${err.message}`);
  }
}


/**
 * Save editor change''',
    ),
)


def patch_action_buttons(js: str) -> tuple[str | None, str]:
    """拆开移动/重命名，并给操作按钮加文字与 aria-label。

    只处理汉化后的模板；任何锚点数量不为 1 都整体跳过，避免半套 UI。
    """
    bad = [(a.splitlines()[0][:40], js.count(a))
           for a, _ in _ACTION_PATCHES if js.count(a) != 1]
    if bad:
        return None, (f"操作按钮结构不符，未拆分（{len(bad)} 处："
                      + "；".join(f"{name}×{n}" for name, n in bad[:3]) + "）")
    for anchor, replacement in _ACTION_PATCHES:
        js = js.replace(anchor, replacement)
    js = "const __DUFS_GUI_RENAME_ICON = " + json.dumps(_RENAME_ICON) + ";\n" + js
    return js, f"操作按钮已改为图标+文字（{len(_ACTION_PATCHES)} 处，移动/重命名已拆分）"


#: 自绘对话框运行时：askConfirm / askPrompt / toastAlert。
#: 原生 confirm/prompt 是同步阻塞，改写成 Promise 后所有调用点必须 await。
_DIALOG_RUNTIME = r"""
/* ===== DufsGui 自绘对话框：askConfirm / askPrompt / toastAlert ===== */
(function () {
  let locked = [];
  let active = null;

  function lockBackground(mask) {
    locked = Array.prototype.slice.call(document.body.children).filter(function (el) {
      return el !== mask;
    });
    locked.forEach(function (el) {
      el.__dgPrev = [el.inert, el.getAttribute("aria-hidden")];
      el.inert = true;
      el.setAttribute("aria-hidden", "true");
    });
  }

  function unlockBackground() {
    locked.forEach(function (el) {
      var prev = el.__dgPrev || [false, null];
      el.inert = !!prev[0];
      if (prev[1] === null) el.removeAttribute("aria-hidden");
      else el.setAttribute("aria-hidden", prev[1]);
      delete el.__dgPrev;
    });
    locked = [];
  }

  function focusables(panel) {
    return Array.prototype.slice.call(
      panel.querySelectorAll('button, input, [href], [tabindex]:not([tabindex="-1"])')
    ).filter(function (el) {
      return !el.disabled && el.offsetParent !== null;
    });
  }

  function openDialog(kind, opts) {
    opts = opts || {};
    if (active) active.cancel();

    return new Promise(function (resolve) {
      var mask = document.createElement("div");
      mask.className = "dg-mask";
      var panel = document.createElement("div");
      panel.className = "dg-modal";
      panel.setAttribute("role", "dialog");
      panel.setAttribute("aria-modal", "true");

      var title = document.createElement("div");
      title.className = "dg-title";
      title.id = "dg-title-" + Date.now();
      title.textContent = opts.title || (kind === "confirm" ? "请确认" : kind === "prompt" ? "请输入" : "提示");
      panel.setAttribute("aria-labelledby", title.id);
      panel.appendChild(title);

      if (opts.message) {
        var message = document.createElement("div");
        message.className = "dg-message";
        message.textContent = opts.message;
        panel.appendChild(message);
      }

      var input = null;
      var error = null;
      if (kind === "prompt") {
        input = document.createElement("input");
        input.type = "text";
        input.className = "dg-input";
        input.value = opts.value || "";
        if (opts.placeholder) input.placeholder = opts.placeholder;
        input.setAttribute("aria-label", opts.inputLabel || opts.title || "输入");
        panel.appendChild(input);
        error = document.createElement("div");
        error.className = "dg-error";
        error.setAttribute("role", "status");
        panel.appendChild(error);
      }

      var actions = document.createElement("div");
      actions.className = "dg-actions";
      panel.appendChild(actions);

      var okBtn = null;

      function finish(value) {
        document.removeEventListener("keydown", onKey, true);
        unlockBackground();
        if (mask.parentNode) mask.parentNode.removeChild(mask);
        active = null;
        resolve(value);
      }

      function cancel() {
        finish(kind === "prompt" ? null : kind === "confirm" ? false : undefined);
      }

      function showError(text) {
        if (!error) return;
        error.textContent = text;
        input.classList.add("dg-invalid");
        input.focus();
      }

      function submit() {
        if (kind === "prompt") {
          var value = input.value;
          var invalid = opts.validate ? (opts.validate(value) || "") : "";
          if (!invalid && opts.required !== false && !value.trim()) invalid = "不能为空";
          if (invalid) { showError(invalid); return; }
          finish(value);
          return;
        }
        finish(kind === "confirm" ? true : undefined);
      }

      function addButton(text, primary, handler) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "dg-btn" + (primary ? " dg-btn-primary" : "");
        btn.textContent = text;
        btn.addEventListener("click", handler);
        actions.appendChild(btn);
        return btn;
      }

      if (kind !== "alert") addButton(opts.cancelText || "取消", false, cancel);
      okBtn = addButton(opts.confirmText || "确定", true, submit);

      function onKey(e) {
        if (e.key === "Escape") {
          e.preventDefault();
          cancel();
        } else if (e.key === "Enter") {
          if (kind !== "prompt" || document.activeElement === input) {
            e.preventDefault();
            submit();
          }
        } else if (e.key === "Tab") {
          var list = focusables(panel);
          if (!list.length) { e.preventDefault(); return; }
          var first = list[0];
          var last = list[list.length - 1];
          if (!panel.contains(document.activeElement)) {
            e.preventDefault();
            first.focus();
          } else if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }

      if (input) {
        input.addEventListener("input", function () {
          error.textContent = "";
          input.classList.remove("dg-invalid");
        });
      }
      mask.addEventListener("mousedown", function (e) {
        if (e.target === mask) cancel();
      });
      document.addEventListener("keydown", onKey, true);

      document.body.appendChild(mask);
      mask.appendChild(panel);
      lockBackground(mask);
      active = { cancel: cancel };
      window.setTimeout(function () {
        if (input) { input.focus(); input.select(); }
        else okBtn.focus();
      }, 0);
    });
  }

  window.askConfirm = function (opts) {
    return openDialog("confirm", opts).then(function (v) { return v === true; });
  };
  window.askPrompt = function (opts) {
    return openDialog("prompt", opts);
  };
  window.toastAlert = function (opts) {
    return openDialog("alert", opts).then(function () { return undefined; });
  };

  /* ===== 上传完成汇总：仅在所有文件结束后弹一次 ===== */
  var uploadBatch = { pending: 0, done: [], failed: [] };

  function uploadList(names, reasons) {
    var lines = names.map(function (name, i) {
      return "· " + name + (reasons ? "：" + (reasons[i] || "网络或服务器错误") : "");
    });
    return lines.join("\n");
  }

  window.__dgShowUploadResult = function (opts) {
    opts = opts || {};
    var done = opts.done || [];
    var failed = opts.failed || [];
    if (active) active.cancel();

    var mask = document.createElement("div");
    mask.className = "dg-mask";
    var panel = document.createElement("div");
    panel.className = "dg-modal";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");

    var title = document.createElement("div");
    title.className = "dg-title";
    title.id = "dg-title-" + Date.now();
    title.textContent = failed.length ? "上传完成（有文件失败）" : "上传完成";
    panel.setAttribute("aria-labelledby", title.id);
    panel.appendChild(title);

    var message = document.createElement("div");
    message.className = "dg-message";
    if (!failed.length) {
      message.textContent = "已成功上传 " + done.length + " 个文件。";
    } else {
      var parts = [];
      if (done.length) {
        parts.push("成功 " + done.length + " 个：\n" + uploadList(done));
      } else {
        parts.push("没有文件成功上传。");
      }
      parts.push("失败 " + failed.length + " 个：\n"
        + uploadList(failed.map(function (f) { return f.name; }),
                    failed.map(function (f) { return f.reason; })));
      message.textContent = parts.join("\n\n");
    }
    panel.appendChild(message);

    var actions = document.createElement("div");
    actions.className = "dg-actions";
    panel.appendChild(actions);

    var countdown = null;
    var timer = null;
    var closed = false;

    function finish(reload) {
      if (closed) return;
      closed = true;
      if (timer) { window.clearInterval(timer); timer = null; }
      document.removeEventListener("keydown", onKey, true);
      unlockBackground();
      if (mask.parentNode) mask.parentNode.removeChild(mask);
      active = null;
      if (reload) window.location.reload();
    }

    function onKey(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        // 成功窗只有一个动作：Esc 也立即刷新，避免关掉后看不到新文件
        finish(!failed.length);
      } else if (e.key === "Enter" && !failed.length) {
        e.preventDefault();
        e.stopPropagation();
        finish(true);
      }
    }

    if (failed.length) {
      var okBtn = document.createElement("button");
      okBtn.type = "button";
      okBtn.className = "dg-btn dg-btn-primary";
      okBtn.textContent = "知道了";
      okBtn.addEventListener("click", function () { finish(false); });
      actions.appendChild(okBtn);
    } else {
      countdown = document.createElement("div");
      countdown.className = "dg-count";
      countdown.setAttribute("role", "status");
      panel.insertBefore(countdown, actions);
      var n = 3;
      countdown.textContent = n + " 秒后自动刷新";

      var refreshBtn = document.createElement("button");
      refreshBtn.type = "button";
      refreshBtn.className = "dg-btn dg-btn-primary";
      refreshBtn.textContent = "确认";
      refreshBtn.addEventListener("click", function () { finish(true); });
      actions.appendChild(refreshBtn);

      timer = window.setInterval(function () {
        n--;
        if (n > 0) {
          countdown.textContent = n + " 秒后自动刷新";
        } else {
          finish(true);
        }
      }, 1000);
    }

    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(mask);
    mask.appendChild(panel);
    lockBackground(mask);
    active = { cancel: function () { finish(false); } };
    window.setTimeout(function () {
      var btn = actions.querySelector("button");
      if (btn) btn.focus();
    }, 0);
  };

  function uploadMaybeFinish() {
    if (uploadBatch.pending > 0) return;
    if (!uploadBatch.done.length && !uploadBatch.failed.length) return;
    var payload = { done: uploadBatch.done.slice(), failed: uploadBatch.failed.slice() };
    uploadBatch.pending = 0;
    uploadBatch.done = [];
    uploadBatch.failed = [];
    window.__dgShowUploadResult(payload);
  }

  window.__dgUploadStart = function () {
    if (uploadBatch.pending === 0
        && (uploadBatch.done.length || uploadBatch.failed.length)) {
      uploadBatch.done = [];
      uploadBatch.failed = [];
    }
    uploadBatch.pending++;
  };
  window.__dgUploadDone = function (name) {
    uploadBatch.done.push(name || "未命名文件");
    uploadBatch.pending = Math.max(0, uploadBatch.pending - 1);
    uploadMaybeFinish();
  };
  window.__dgUploadFail = function (name, reason) {
    uploadBatch.failed.push({
      name: name || "未命名文件",
      reason: reason || "网络或服务器错误"
    });
    uploadBatch.pending = Math.max(0, uploadBatch.pending - 1);
    uploadMaybeFinish();
  };
})();
"""


#: 原生调用点 → 自绘 Promise 弹窗。全部基于"汉化 + 操作按钮改写"后的文本，
#: 任一处锚点不唯一就整体跳过，避免出现一半自绘一半原生。
_DIALOG_PATCHES: tuple[tuple[str, str], ...] = (
    (
        '''    alert("页面数据缺失，请刷新重试");''',
        '''    await toastAlert({ title: "提示", message: "页面数据缺失，请刷新重试" });''',
    ),
    (
        '''        alert(`下载失败：${err.message}`);''',
        '''        await toastAlert({ title: "下载失败", message: err.message });''',
    ),
    (
        '''  $newFolder.addEventListener("click", () => {
    const name = prompt("输入文件夹名称");
    if (name) createFolder(name);
  });''',
        '''  $newFolder.addEventListener("click", async () => {
    const name = await askPrompt({
      title: "新建文件夹",
      message: "输入文件夹名称",
      confirmText: "创建",
      required: true,
    });
    if (name) createFolder(name);
  });''',
    ),
    (
        '''  $newFile.addEventListener("click", () => {
    const name = prompt("输入文件名称");
    if (name) createFile(name);
  });''',
        '''  $newFile.addEventListener("click", async () => {
    const name = await askPrompt({
      title: "新建文件",
      message: "输入文件名称",
      confirmText: "创建",
      required: true,
    });
    if (name) createFile(name);
  });''',
    ),
    (
        '''    alert(`读取文件失败：${err.message}`);''',
        '''    await toastAlert({ title: "读取失败", message: err.message });''',
    ),
    (
        '''async function doDeletePath(name, url, cb) {
  if (!confirm(`删除「${name}」？`)) return;''',
        '''async function doDeletePath(name, url, cb) {
  const okDelete = await askConfirm({
    title: "删除确认",
    message: `确定删除「${name}」吗？删除后无法恢复。`,
    confirmText: "删除",
    danger: true,
  });
  if (!okDelete) return;''',
    ),
    (
        '''    alert(`无法删除「${file.name}」：${err.message}`);''',
        '''    await toastAlert({ title: "删除失败", message: `无法删除「${name}」：${err.message}` });''',
    ),
    (
        '''  let newPath = prompt("输入新路径", filePath);''',
        '''  let newPath = await askPrompt({
    title: "移动到",
    message: "输入完整的新路径（以 / 开头）",
    value: filePath,
    confirmText: "移动",
    required: true,
  });''',
    ),
    (
        '''    if (res1.status === 200) {
      if (!confirm("覆盖已存在的文件？")) {
        return;
      }
    }''',
        '''    if (res1.status === 200) {
      if (!(await askConfirm({
        title: "覆盖文件",
        message: "目标位置已存在同名文件，确定覆盖吗？",
        confirmText: "覆盖",
        danger: true,
      }))) {
        return;
      }
    }''',
    ),
    (
        '''    alert(`无法移动「${filePath}」到「${newPath}」：${err.message}`);''',
        '''    await toastAlert({ title: "移动失败", message: `无法移动「${filePath}」到「${newPath}」：${err.message}` });''',
    ),
    (
        '''  const name = prompt("输入新名称", file.name);
  if (!name || name === file.name) return;
  if (name.includes("/")) {
    alert("名称不能包含「/」，跨目录请使用「移动」");
    return;
  }''',
        '''  const name = await askPrompt({
    title: "重命名",
    message: `输入「${file.name}」的新名称`,
    value: file.name,
    confirmText: "重命名",
    required: true,
    validate: v => v.includes("/") ? "名称不能包含「/」，跨目录请使用「移动」" : "",
  });
  if (!name || name === file.name) return;''',
    ),
    (
        '''      if (!confirm("覆盖已存在的文件？")) return;''',
        '''      if (!(await askConfirm({
        title: "覆盖文件",
        message: "目标位置已存在同名文件，确定覆盖吗？",
        confirmText: "覆盖",
        danger: true,
      }))) return;''',
    ),
    (
        '''    alert(`无法重命名「${file.name}」：${err.message}`);''',
        '''    await toastAlert({ title: "重命名失败", message: `无法重命名「${file.name}」：${err.message}` });''',
    ),
    (
        '''    alert(`保存文件失败：${err.message}`);''',
        '''    await toastAlert({ title: "保存失败", message: err.message });''',
    ),
    (
        '''    alert(`无法创建文件夹「${name}」：${err.message}`);''',
        '''    await toastAlert({ title: "创建失败", message: `无法创建文件夹「${name}」：${err.message}` });''',
    ),
    (
        '''    alert(`无法创建文件「${name}」：${err.message}`);''',
        '''    await toastAlert({ title: "创建失败", message: `无法创建文件「${name}」：${err.message}` });''',
    ),
)


def patch_native_dialogs(js: str) -> tuple[str | None, str]:
    """把所有原生 confirm/prompt/alert 换成自绘 Promise 弹窗。"""
    bad = [(a.splitlines()[0].strip()[:42], js.count(a))
           for a, _ in _DIALOG_PATCHES if js.count(a) != 1]
    if bad:
        return None, (f"原生弹窗调用结构不符，未替换（{len(bad)} 处："
                      + "；".join(f"{name}×{n}" for name, n in bad[:3]) + "）")
    for anchor, replacement in _DIALOG_PATCHES:
        js = js.replace(anchor, replacement)
    leftover = [p for p in ("alert(", "prompt(", "confirm(") if p in js]
    if leftover:
        return None, f"仍残留原生调用：{', '.join(leftover)}"
    return (_DIALOG_RUNTIME + "\n" + js,
            f"原生弹窗已全部替换（alert {js.count('toastAlert({')} 处、"
            f"prompt {js.count('askPrompt({')} 处、confirm {js.count('askConfirm({')} 处）")


#: 上传完成反馈：批次数、完成/失败汇总，以及去掉了原来的对勾。
_UPLOAD_FEEDBACK_PATCHES: tuple[tuple[str, str], ...] = (
    (
        '''    Uploader.queues.push(this);
    Uploader.runQueue();''',
        '''    __dgUploadStart(name);
    Uploader.queues.push(this);
    Uploader.runQueue();''',
    ),
    (
        '''    this.$status.textContent = "✓";''',
        '''    this.$status.textContent = "完成";''',
    ),
    (
        '''    failUploaders.delete(this.idx);
    Uploader.runnings--;
    Uploader.runQueue();''',
        '''    failUploaders.delete(this.idx);
    Uploader.runnings--;
    Uploader.runQueue();
    __dgUploadDone(this.name);''',
    ),
    (
        '''    failUploaders.set(this.idx, this);
    Uploader.runnings--;
    Uploader.runQueue();''',
        '''    failUploaders.set(this.idx, this);
    Uploader.runnings--;
    Uploader.runQueue();
    __dgUploadFail(this.name, reason);''',
    ),
    (
        '''    this.uploadOffset = uploadOffset;
    this.ajax();''',
        '''    this.uploadOffset = uploadOffset;
    __dgUploadStart(this.name);
    this.ajax();''',
    ),
)


def patch_upload_feedback(js: str) -> tuple[str | None, str]:
    """上传全部结束后弹一次汇总窗；成功 3 秒倒计时后刷新，失败则停留。"""
    bad = [(a.splitlines()[0].strip()[:42], js.count(a))
           for a, _ in _UPLOAD_FEEDBACK_PATCHES if js.count(a) != 1]
    if bad:
        return None, (f"上传反馈结构不符，未改动（{len(bad)} 处："
                      + "；".join(f"{name}×{n}" for name, n in bad[:3]) + "）")
    for anchor, replacement in _UPLOAD_FEEDBACK_PATCHES:
        js = js.replace(anchor, replacement)
    return js, "上传完成汇总：已接入（完成/失败 + 倒计时刷新）"


def app_icon_svg() -> str | None:
    """应用图标的 SVG 源（assets/app.svg，随包分发）。

    与 exe 的 ICO、Tk 窗口图标共用同一份图形；读不到时返回 None，
    由调用方保留官方 favicon，避免画出半成品。
    """
    try:
        svg = (resource_dir() / "assets" / "app.svg").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return svg if svg.startswith("<svg") and svg.endswith("</svg>") else None


def app_favicon_link() -> str | None:
    """内联 SVG data URI 的站点图标（与应用图标同形）。"""
    svg = app_icon_svg()
    if not svg:
        return None
    return ('<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,'
            + quote(svg, safe="") + '">')


def patch_favicon_html(html: str) -> tuple[str, str]:
    """把官方 favicon.ico 引用换成应用图标 data URI；失败则原样返回。"""
    if _FAVICON_LINK not in html:
        return html, "未找到官方 favicon 引用，跳过站点图标"
    link = app_favicon_link()
    if link is None:
        return html, "应用图标 SVG 缺失，保留官方站点图标"
    return html.replace(_FAVICON_LINK, link), "站点图标已改为内联 SVG（与应用图标同形）"


def patch_index_css(css: str) -> tuple[str, str]:
    """追加顶部彩条覆盖与操作按钮样式；重复调用不会叠加（幂等）。"""
    marker = "DufsGui 运行时覆盖"
    if marker in css:
        return css, "运行时样式覆盖已存在"
    return css + _TOP_BAR_OVERRIDE, "顶部渐变彩条与操作按钮样式已追加"


#: dufs 对 /__dufs_v<ver>__/index.css|index.js 返回
#: ``Cache-Control: public, max-age=31536000, immutable``，而路径不随皮肤内容变化。
#: 浏览器会沿用旧脚本/样式，导致"服务端已汉化、页面仍是英文"。
#: 在 index.html 的资源引用后加内容哈希，URL 变了才会重新拉取。
_ASSET_LINKS = ("__ASSETS_PREFIX__index.css", "__ASSETS_PREFIX__index.js")


def asset_token(dest_dir: str | Path) -> str:
    """按 index.js + index.css 内容生成短版本号。"""
    h = hashlib.sha256()
    for name in ("index.js", "index.css"):
        p = Path(dest_dir) / name
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


def bust_asset_cache(html: str, token: str) -> tuple[str, str]:
    """给样式/脚本引用追加 ``?v=<token>``，绕开 immutable 缓存。

    幂等：已有 ``?v=`` 时先去掉旧值再加新值。
    """
    if not token:
        return html, "缓存版本未生成"
    changed = 0
    for link in _ASSET_LINKS:
        if link not in html:
            continue
        html = html.replace(link + "?v=" + token, link)
        html = html.replace(link, f"{link}?v={token}")
        changed += 1
    return html, (f"网页资源缓存版本已更新：v={token}" if changed
                  else "未找到样式/脚本引用，跳过缓存版本")


def favicon_bytes(path: str) -> tuple[bytes | None, str]:
    """读取并校验 .ico 文件，返回 (内容, 说明)。"""
    p = Path(path)
    if not p.is_file():
        return None, f"图标文件不存在：{p}"
    try:
        data = p.read_bytes()
    except OSError as e:
        return None, f"无法读取图标：{e}"
    if len(data) < 6 or data[:4] != b"\x00\x00\x01\x00":
        return None, "不是有效的 .ico 文件（文件头不是 00 00 01 00）"
    if len(data) > 2 * 1024 * 1024:
        return None, "图标文件超过 2 MB"
    return data, f"站点图标已替换：{p.name}"


@dataclass
class OverlayResult:
    assets_dir: str
    applied: bool = False
    notes: list[str] = field(default_factory=list)


def prepare_overlay(source_dir: str, title: str, favicon_path: str,
                    dest_dir: Path | None = None) -> OverlayResult:
    """生成覆盖资产目录（始终汉化 + 去彩条）；绝不修改仓库/fetch 产物。"""
    title = sanitize_title(title)
    source = Path(source_dir) if source_dir else None

    if source is None or not (source / "index.html").is_file():
        return OverlayResult(str(source or ""),
                             notes=["原皮肤目录缺少 index.html，未生成网页覆盖"])

    dest = Path(dest_dir) if dest_dir else app_data_dir() / "webui"
    try:
        if dest.resolve() == source.resolve():
            return OverlayResult(str(source),
                                 notes=["皮肤目录指向覆盖目录本身，跳过覆盖"])
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
    except OSError as e:
        return OverlayResult(str(source), notes=[f"生成网页覆盖失败：{e}"])

    applied = False
    notes: list[str] = []

    # ---- index.js：标题注入 + 文案汉化（顺序不能反，标题锚点依赖官方英文）----
    js_path = dest / "index.js"
    if js_path.is_file():
        try:
            original = js_path.read_text(encoding="utf-8")
        except OSError as e:
            notes.append(f"读取 index.js 失败：{e}")
        else:
            text = original
            if title:
                patched, msg = patch_index_js(original, title)
                notes.append(msg)
                if patched is not None:
                    text = patched
            localized, msg = localize_index_js(text)
            notes.append(msg)
            if localized is not None:
                text = localized
            actioned, msg = patch_action_buttons(text)
            notes.append(msg)
            if actioned is not None:
                text = actioned
            dialogs, msg = patch_native_dialogs(text)
            notes.append(msg)
            if dialogs is not None:
                text = dialogs
            uploaded, msg = patch_upload_feedback(text)
            notes.append(msg)
            if uploaded is not None:
                text = uploaded
            if text != original:
                try:
                    js_path.write_text(text, encoding="utf-8")
                    applied = True
                except OSError as e:
                    notes.append(f"写入 index.js 失败：{e}")
    else:
        notes.append("皮肤缺少 index.js，跳过脚本文案汉化")

    # ---- index.html：静态 title / aria / 上传任务表头 ----
    html_path = dest / "index.html"
    try:
        original_html = html_path.read_text(encoding="utf-8")
    except OSError as e:
        notes.append(f"读取 index.html 失败：{e}")
    else:
        localized, msg = localize_index_html(original_html)
        notes.append(msg)
        text_html = localized if localized is not None else original_html
        buttoned, msg = patch_toolbar_text(text_html)
        notes.append(msg)
        if buttoned is not None:
            text_html = buttoned
        if not favicon_path:
            text_html, msg = patch_favicon_html(text_html)
            notes.append(msg)
        if text_html != original_html:
            try:
                html_path.write_text(text_html, encoding="utf-8")
                applied = True
            except OSError as e:
                notes.append(f"写入 index.html 失败：{e}")

    # ---- index.css：去掉顶部渐变彩条 ----
    css_path = dest / "index.css"
    if css_path.is_file():
        try:
            original_css = css_path.read_text(encoding="utf-8")
        except OSError as e:
            notes.append(f"读取 index.css 失败：{e}")
        else:
            patched_css, msg = patch_index_css(original_css)
            notes.append(msg)
            if patched_css != original_css:
                try:
                    css_path.write_text(patched_css, encoding="utf-8")
                    applied = True
                except OSError as e:
                    notes.append(f"写入 index.css 失败：{e}")
    else:
        notes.append("皮肤缺少 index.css，跳过顶部彩条处理")

    # ---- index.html：样式/脚本引用追加内容版本，绕开 immutable 缓存 ----
    # 必须放在 CSS/JS 改写之后：token 由最终内容算出。
    try:
        html_now = html_path.read_text(encoding="utf-8")
        token = asset_token(dest)
        busted, msg = bust_asset_cache(html_now, token)
        notes.append(msg)
        if busted != html_now:
            html_path.write_text(busted, encoding="utf-8")
            applied = True
    except OSError as e:
        notes.append(f"写入缓存版本失败：{e}")

    if favicon_path:
        data, msg = favicon_bytes(favicon_path)
        notes.append(msg)
        if data is not None:
            try:
                (dest / "favicon.ico").write_bytes(data)
                applied = True
            except OSError as e:
                notes.append(f"写入 favicon.ico 失败：{e}")

    return OverlayResult(str(dest), applied=applied, notes=notes)
