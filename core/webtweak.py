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

from .dufsbin import app_data_dir

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
"""

#: 站点图标：dufs 官方引用 ``__ASSETS_PREFIX__favicon.ico``。
#: 覆盖副本改成内联 SVG data URI 的 emoji，不依赖外部文件、不会 404。
_FAVICON_LINK = ('<link rel="icon" type="image/x-icon" '
                 'href="__ASSETS_PREFIX__favicon.ico">')

#: 选 📤 而不是 🗂️/📁：16px 下托盘+箭头轮廓最清楚，浅色/深色标签栏都不糊。
FAVICON_EMOJI = "📤"

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


def emoji_favicon_link(emoji: str = FAVICON_EMOJI) -> str:
    """内联 SVG data URI 的 emoji 站点图标。"""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<text x="50" y="50" font-size="88" text-anchor="middle" '
           f'dominant-baseline="central">{emoji}</text></svg>')
    return ('<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,'
            + quote(svg, safe="") + '">')


def patch_favicon_html(html: str, emoji: str = FAVICON_EMOJI) -> tuple[str, str]:
    """把官方 favicon.ico 引用换成 emoji data URI；找不到引用则原样返回。"""
    if _FAVICON_LINK not in html:
        return html, "未找到官方 favicon 引用，跳过 emoji 图标"
    return (html.replace(_FAVICON_LINK, emoji_favicon_link(emoji)),
            f"站点图标已改为内联 emoji：{emoji}")


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
