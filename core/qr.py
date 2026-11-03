"""最小 QR 编码器（纯标准库，无第三方依赖）。

用途：在「共享链接」旁生成可扫描的二维码。共享链接都是 ASCII 短文本
（形如 ``http://192.168.1.5:5000/``），因此只实现 QR Code Model 2 的
**字节模式 + 纠错等级 L + 版本 1–10**，足以覆盖最长约 270 字节的地址；
更长的输入直接抛 ``QrTooLong``，由界面提示，而不是静默生成错图。

选型说明（见 docs/使用指南.md 的「二维码」一节）：
- 引入 ``qrcode`` 依赖会让 onefile 体积增加约 0.15–0.3 MB，并且 build.bat
  需要先联网装包，破坏"一条命令构建"；
- 这里自带的实现约 200 行、只依赖 zlib（标准库），体积增量可忽略，
  且可用单元测试覆盖矩阵结构与 PNG 输出，不必为一张二维码引入依赖。
"""

from __future__ import annotations

import struct
import zlib

#: 支持的最大版本（10 版 L 级容量 274 个数据码字，约 270 字节文本）
MAX_VERSION = 10

#: (总码字, 纠错码字/块, 块数)；下标对应版本 1..10，仅 L 级
_ECC_L = (
    (26, 7, 1),
    (44, 10, 1),
    (70, 15, 1),
    (100, 20, 1),
    (134, 26, 1),
    (172, 18, 2),
    (196, 20, 2),
    (242, 24, 2),
    (292, 30, 2),
    (346, 18, 4),
)

_ALIGN = {
    1: (),
    2: (6, 18),
    3: (6, 22),
    4: (6, 26),
    5: (6, 30),
    6: (6, 34),
    7: (6, 22, 38),
    8: (6, 24, 42),
    9: (6, 26, 46),
    10: (6, 28, 50),
}

_VERSION_INFO = {
    7: 0x07C94,
    8: 0x085BC,
    9: 0x09A99,
    10: 0x0A4D3,
}


class QrError(ValueError):
    """二维码生成失败（输入过长 / 内部错误）。"""


class QrTooLong(QrError):
    """文本超出本实现支持的最大容量（版本 10-L）。"""


# ---------- GF(256) 与 RS 纠错 ----------
_EXP = [0] * 512
_LOG = [0] * 256


def _init_tables() -> None:
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_tables()


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree: int) -> list[int]:
    """生成多项式 ∏(x - α^i)，系数从高到低。"""
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _gf_mul(coef, _EXP[i])
        poly = nxt
    return poly


def _rs_remainder(data: list[int], degree: int) -> list[int]:
    gen = _rs_generator(degree)
    rem = list(data) + [0] * degree
    for i in range(len(data)):
        factor = rem[i]
        if factor:
            for j in range(len(gen)):
                rem[i + j] ^= _gf_mul(gen[j], factor)
    return rem[-degree:]


# ---------- 容量与分段 ----------
def _capacity_bytes(version: int) -> int:
    total, ecc, blocks = _ECC_L[version - 1]
    data_codewords = total - ecc * blocks
    count_bits = 8 if version <= 9 else 16
    return (data_codewords * 8 - 4 - count_bits) // 8


def _choose_version(length: int) -> int:
    for version in range(1, MAX_VERSION + 1):
        if _capacity_bytes(version) >= length:
            return version
    raise QrTooLong(
        f"内容 {length} 字节，超出二维码支持的最大 {_capacity_bytes(MAX_VERSION)} 字节")


def _data_codewords(version: int) -> list[int]:
    """按字节模式编码，补齐并分成块（块大小短块在前，符合标准）。"""
    total, ecc, blocks = _ECC_L[version - 1]
    data_total = total - ecc * blocks
    count_bits = 8 if version <= 9 else 16
    return [data_total, count_bits]


def _encode_data(text: str, version: int) -> list[int]:
    raw = text.encode("utf-8")
    data_total, count_bits = _data_codewords(version)
    bits: list[int] = [0, 1, 0, 0]            # 字节模式 0100
    bits += [(len(raw) >> i) & 1 for i in range(count_bits - 1, -1, -1)]
    for b in raw:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    capacity_bits = data_total * 8
    bits += [0] * min(4, capacity_bits - len(bits))     # 终止符
    while len(bits) % 8:
        bits.append(0)
    codewords = [
        int("".join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)
    ]
    pad = (0xEC, 0x11)
    k = 0
    while len(codewords) < data_total:
        codewords.append(pad[k % 2])
        k += 1
    return codewords


def _interleave(version: int, codewords: list[int]) -> list[int]:
    total, ecc, blocks = _ECC_L[version - 1]
    data_total = total - ecc * blocks
    short_len = data_total // blocks
    long_count = data_total % blocks
    chunks: list[list[int]] = []
    ecc_chunks: list[list[int]] = []
    pos = 0
    for i in range(blocks):
        n = short_len + (1 if i >= blocks - long_count else 0)
        chunk = codewords[pos:pos + n]
        pos += n
        chunks.append(chunk)
        ecc_chunks.append(_rs_remainder(chunk, ecc))
    out: list[int] = []
    for i in range(max(len(c) for c in chunks)):
        for chunk in chunks:
            if i < len(chunk):
                out.append(chunk[i])
    for i in range(ecc):
        for chunk in ecc_chunks:
            out.append(chunk[i])
    return out


# ---------- 矩阵 ----------
class _Matrix:
    def __init__(self, version: int) -> None:
        self.version = version
        self.size = version * 4 + 17
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.function = [[False] * self.size for _ in range(self.size)]

    def set_function(self, x: int, y: int, dark: bool) -> None:
        self.modules[y][x] = dark
        self.function[y][x] = True

    def draw_function_patterns(self) -> None:
        size = self.size
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        d = max(abs(dx), abs(dy))
                        self.set_function(x, y, d in (0, 1, 3))
        # 定位图形外圈的一格浅色分隔带：不画的话数据会顶进来，扫码器读不出
        for i in range(8):
            self.set_function(7, i, False)
            self.set_function(i, 7, False)
            self.set_function(size - 8, i, False)
            self.set_function(size - 1 - i, 7, False)
            self.set_function(7, size - 1 - i, False)
            self.set_function(i, size - 8, False)
        for i in range(8, size - 8):
            self.set_function(i, 6, i % 2 == 0)
            self.set_function(6, i, i % 2 == 0)
        positions = _ALIGN[self.version]
        for cy in positions:
            for cx in positions:
                # 与三个定位图形重叠的角落不画
                if (cx, cy) in ((6, 6), (6, size - 7), (size - 7, 6)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        d = max(abs(dx), abs(dy))
                        self.set_function(cx + dx, cy + dy, d in (0, 2))
        self._draw_format(0)  # 先占位，最终会按掩码重画
        if self.version >= 7:
            bits = _VERSION_INFO[self.version]
            for i in range(18):
                bit = (bits >> i) & 1
                a = size - 11 + i % 3
                b = i // 3
                self.set_function(a, b, bool(bit))
                self.set_function(b, a, bool(bit))

    def _draw_format(self, mask: int) -> None:
        data = (0b01 << 3) | mask        # 纠错等级 L = 01
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = ((data << 10) | rem) ^ 0x5412

        def bit(i: int) -> bool:
            return bool((bits >> i) & 1)

        size = self.size
        for i in range(6):
            self.set_function(8, i, bit(i))
        self.set_function(8, 7, bit(6))
        self.set_function(8, 8, bit(7))
        self.set_function(7, 8, bit(8))
        for i in range(9, 15):
            self.set_function(14 - i, 8, bit(i))
        for i in range(8):
            self.set_function(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set_function(8, size - 15 + i, bit(i))
        self.set_function(8, size - 8, True)   # 固定的暗模块

    def place_data(self, codewords: list[int], mask: int) -> None:
        size = self.size
        raw_bits = [(cw >> i) & 1 for cw in codewords for i in range(7, -1, -1)]
        idx = 0
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(size):
                upward = ((right + 1) & 2) == 0
                y = size - 1 - vert if upward else vert
                for j in (0, 1):
                    x = right - j
                    if self.function[y][x]:
                        continue
                    dark = bool(raw_bits[idx]) if idx < len(raw_bits) else False
                    if _mask_bit(mask, x, y):
                        dark = not dark
                    self.modules[y][x] = dark
                    idx += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        for y in range(self.size):
            for x in range(self.size):
                if not self.function[y][x] and _mask_bit(mask, x, y):
                    self.modules[y][x] = not self.modules[y][x]


def _mask_bit(mask: int, x: int, y: int) -> bool:
    return (
        (x + y) % 2 == 0,
        y % 2 == 0,
        x % 3 == 0,
        (x + y) % 3 == 0,
        (y // 2 + x // 3) % 2 == 0,
        (x * y) % 2 + (x * y) % 3 == 0,
        ((x * y) % 2 + (x * y) % 3) % 2 == 0,
        ((x + y) % 2 + (x * y) % 3) % 2 == 0,
    )[mask]


def _penalty(modules: list[list[bool]]) -> int:
    size = len(modules)
    score = 0
    for line in list(modules) + [list(col) for col in zip(*modules)]:
        run = 1
        for i in range(1, size):
            if line[i] == line[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run = 1
        if run >= 5:
            score += 3 + run - 5
        seq = [int(v) for v in line]
        for i in range(size - 10):
            if seq[i:i + 11] in ([1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]):
                score += 40
    for y in range(size - 1):
        for x in range(size - 1):
            if modules[y][x] == modules[y][x + 1] == modules[y + 1][x] == modules[y + 1][x + 1]:
                score += 3
    dark = sum(sum(1 for v in row if v) for row in modules)
    percent = dark * 100.0 / (size * size)
    score += int(abs(percent - 50) / 5) * 10
    return score


def matrix_for(text: str, mask: int | None = None) -> list[list[bool]]:
    """生成矩阵；mask 指定时固定掩码（用于交叉校验），None 时自动选择。"""
    if not text:
        raise QrError("二维码内容不能为空")
    version = _choose_version(len(text.encode("utf-8")))
    codewords = _interleave(version, _encode_data(text, version))
    if mask is not None:
        m = _Matrix(version)
        m.draw_function_patterns()
        m.place_data(codewords, mask)
        m._draw_format(mask)
        return m.modules

    best_modules: list[list[bool]] | None = None
    best_score: int | None = None
    for candidate in range(8):
        m = _Matrix(version)
        m.draw_function_patterns()
        m.place_data(codewords, candidate)
        # 格式信息必须记录当选掩码，否则解码器读到的掩码与实际不符
        m._draw_format(candidate)
        score = _penalty(m.modules)
        if best_score is None or score < best_score:
            best_modules, best_score = m.modules, score
    assert best_modules is not None
    return best_modules


def encode(text: str) -> list[list[bool]]:
    """生成二维码矩阵（True = 深色模块）。自动选版本与掩码。"""
    return matrix_for(text)


# ---------- PNG 输出 ----------
def png_bytes(matrix: list[list[bool]], scale: int = 8, border: int = 4) -> bytes:
    """生成 8 位灰度 PNG：白底黑模块 + 标准静区。"""
    n = len(matrix)
    side = (n + border * 2) * scale
    white = b"\xff" * side
    rows: list[bytes] = []
    for y in range(side):
        my = y // scale - border
        if my < 0 or my >= n:
            rows.append(white)
            continue
        line = matrix[my]
        row = bytearray()
        row += b"\xff" * (border * scale)
        for dark in line:
            row += (b"\x00" if dark else b"\xff") * scale
        row += b"\xff" * (border * scale)
        rows.append(bytes(row))
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def save_png(path: str, text: str, scale: int = 8) -> str:
    """把文本编码成二维码并写到 PNG，返回路径。"""
    data = png_bytes(encode(text), scale=scale)
    with open(path, "wb") as f:
        f.write(data)
    return path
