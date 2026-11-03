"""网页标题与站点图标（favicon）的运行时覆盖。

证据链：dufs 的 ``--assets`` 目录同时提供 ``index.html`` / ``index.js`` /
``favicon.ico``，页面通过 ``__ASSETS_PREFIX__`` 引用它们；``index.js`` 里有
三处 ``document.title = `... - Dufs` ``` 决定浏览器标签标题。因此不改
``tools/fetch_skin.py`` 拉取的仓库资产，而是在用户目录生成一份覆盖副本：
复制官方资产 → 给 ``index.js`` 注入标题常量 → 替换 ``favicon.ico``。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .dufsbin import app_data_dir

MAX_TITLE_LEN = 48
_TITLE_CONST = "__DUFS_GUI_TITLE"
_OFFICIAL_TITLES = {
    "index": "document.title = `Index of ${DATA.href} - Dufs`;",
    "edit": "document.title = `Edit ${DATA.href} - Dufs`;",
    "view": "document.title = `View ${DATA.href} - Dufs`;",
}


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
    """生成覆盖资产目录；失败时回退原目录，绝不修改仓库/fetch 产物。"""
    title = sanitize_title(title)
    source = Path(source_dir) if source_dir else None
    if not title and not favicon_path:
        return OverlayResult(str(source or ""))

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

    if title:
        js_path = dest / "index.js"
        try:
            original = js_path.read_text(encoding="utf-8")
        except OSError as e:
            notes.append(f"读取 index.js 失败：{e}")
        else:
            patched, msg = patch_index_js(original, title)
            notes.append(msg)
            if patched is not None:
                try:
                    js_path.write_text(patched, encoding="utf-8")
                    applied = True
                except OSError as e:
                    notes.append(f"写入 index.js 失败：{e}")

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
