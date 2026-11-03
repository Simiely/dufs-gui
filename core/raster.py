"""纯标准库圆角位图光栅化（4x4 超采样），供 UI 与主题复用。

为什么不用 Pillow：实测 Pillow 12.3 会让 onefile exe 增加约 20.1 MB、
导入约 42 ms（见 docs/round-report.md）。这里只依赖 zlib/struct，4x4
超采样得到抗锯齿边缘；角块尺寸只有半径大小，运行时开销可忽略。
"""

from __future__ import annotations

import base64
import math
import struct
import zlib

SAMPLE = 4


def chunk(tag: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + tag + body
            + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))


def png_rgba(width: int, height: int, rows) -> bytes:
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def rgb(color):
    if isinstance(color, (tuple, list)):
        return tuple(color)
    if isinstance(color, str) and color.startswith("#") and len(color) == 7:
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    return (30, 30, 30)


def inside(x: float, y: float, w: int, h: int, r: int) -> bool:
    cx = min(max(x, r), w - r)
    cy = min(max(y, r), h - r)
    return math.hypot(x - cx, y - cy) <= r


def _mix(parts):
    n = sum(p[1] for p in parts)
    if n <= 0:
        return (0, 0, 0)
    return tuple(int(round(sum(p[0][i] * p[1] for p in parts) / n))
                 for i in range(3))


def rounded_rows(w: int, h: int, radius: int, fill, bg=None,
                 border=None, border_w: int = 0, transparent: bool = False,
                 tick=None, tick_fill=None):
    """返回 h 行 RGBA 像素。

    transparent=False 时圆角外与边缘按 bg 混合成不透明色（按钮/卡片用，避免
    贴图下方颜色变化造成浅色缺口）；True 时圆角外 alpha=0、边缘保留覆盖率
    （复选框等需要叠在任意底色上的小元素用）。
    """
    border = border or fill
    tick_fill = tick_fill or (255, 255, 255)
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            n_out = n_border = n_fill = 0
            for sy in range(SAMPLE):
                for sx in range(SAMPLE):
                    px = x + (sx + 0.5) / SAMPLE
                    py = y + (sy + 0.5) / SAMPLE
                    if not inside(px, py, w, h, radius):
                        n_out += 1
                    elif border_w and not inside(px - border_w, py - border_w,
                                                 w - 2 * border_w, h - 2 * border_w,
                                                 max(radius - border_w, 0)):
                        n_border += 1
                    else:
                        n_fill += 1
            parts = [((fill), n_fill), ((border), n_border)]
            if transparent:
                alpha = int(round(255 * (n_fill + n_border) / (SAMPLE * SAMPLE)))
                color = _mix(parts)
            else:
                alpha = 255
                color = _mix(parts + [((bg or (30, 30, 30)), n_out)])
            if tick and tick(x + 0.5, y + 0.5):
                color = tick_fill
                alpha = 255
            row.extend((*color, alpha))
        rows.append(row)
    return rows


def rounded_png(w: int, h: int, radius: int, fill, bg=None, border=None,
                border_w: int = 0, transparent: bool = False, tick=None,
                tick_fill=None):
    """整块圆角 PNG。tick 为 (x, y) -> bool 的覆盖函数（按像素中心判断）。"""
    rows = rounded_rows(w, h, radius, rgb(fill), rgb(bg) if bg else None,
                        rgb(border) if border else None, border_w,
                        transparent, tick, rgb(tick_fill) if tick_fill else None)
    return png_rgba(w, h, rows)


def corner_png(size: int, radius: int, fill, bg, corner: int = 0,
               border=None, border_w: int = 0, transparent: bool = False):
    """size×size 角块，corner 0/1/2/3 = 左上/右上/左下/右下。"""
    fill, bg = rgb(fill), rgb(bg)
    border = rgb(border) if border else fill
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            n_out = n_border = n_fill = 0
            for sy in range(SAMPLE):
                for sx in range(SAMPLE):
                    px = x + (sx + 0.5) / SAMPLE
                    py = y + (sy + 0.5) / SAMPLE
                    if corner in (1, 3):
                        px = size - px
                    if corner in (2, 3):
                        py = size - py
                    dist = math.hypot(px - radius, py - radius)
                    if dist > radius:
                        n_out += 1
                    elif border_w and dist > radius - border_w:
                        n_border += 1
                    else:
                        n_fill += 1
            parts = [((fill), n_fill), ((border), n_border)]
            if transparent:
                alpha = int(round(255 * (n_fill + n_border) / (SAMPLE * SAMPLE)))
                color = _mix(parts)
            else:
                alpha = 255
                color = _mix(parts + [((bg), n_out)])
            row.extend((*color, alpha))
        rows.append(row)
    return png_rgba(size, size, rows)


def photo(png: bytes):
    import tkinter as tk
    return tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))
