"""二维码编码器测试（纯标准库，不依赖第三方解码器）。

矩阵结构用「黄金哈希」防回归；真正的可扫性由构建时的人工/工具验证保证
（本次改造用 zxing-cpp 解码过 8 组不同版本的地址，见交付说明）。
"""

from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import qr  # noqa: E402


URL = "http://192.168.1.5:5000/"
GOLDEN = "e94ce302846a182bfcf7481e7c68edb5001aafd89706ca625ad867affacdd6ef"


class QrTest(unittest.TestCase):
    def test_matrix_size_and_shape(self):
        m = qr.encode(URL)
        self.assertEqual(len(m), 25, "24 字节地址应落在版本 2（25×25）")
        self.assertTrue(all(len(row) == 25 for row in m))
        # 三个定位图形：7×7 方环，中心 3×3 实心、外环实心、中间一圈浅色
        self.assertTrue(m[0][0] and m[3][3] and not m[1][1])
        self.assertTrue(m[0][24] and m[24][0])

    def test_golden_matrix_stable(self):
        """固定输入 + 自动选掩码：矩阵哈希锁死，防止编码/掩码回归。"""
        bits = "".join("1" if v else "0" for row in qr.encode(URL) for v in row)
        self.assertEqual(hashlib.sha256(bits.encode()).hexdigest(), GOLDEN)

    def test_all_masks_are_distinct(self):
        matrices = {hashlib.sha256(
            "".join("1" if v else "0" for row in qr.matrix_for(URL, mask)
                    for v in row).encode()).hexdigest()
            for mask in range(8)}
        self.assertEqual(len(matrices), 8, "8 个掩码不应产生相同矩阵")

    def test_png_is_valid_and_quiet_zoned(self):
        m = qr.encode(URL)
        data = qr.png_bytes(m, scale=4)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        # 解析 IHDR：边长 = (模块数 + 8 格静区) × 缩放
        self.assertEqual(data[12:16], b"IHDR")
        width, height, depth, ctype = struct.unpack(">IIBB", data[16:26])
        self.assertEqual((width, height), ((25 + 8) * 4, (25 + 8) * 4))
        self.assertEqual((depth, ctype), (8, 0))
        # IDAT 可解压，且每行长度与位深一致
        i, idat = 8, b""
        while i < len(data):
            ln = struct.unpack(">I", data[i:i + 4])[0]
            tag = data[i + 4:i + 8]
            body = data[i + 8:i + 8 + ln]
            if tag == b"IDAT":
                idat += body
            crc = struct.unpack(">I", data[i + 8 + ln:i + 12 + ln])[0]
            self.assertEqual(crc, zlib.crc32(tag + body) & 0xFFFFFFFF)
            i += 12 + ln
        raw = zlib.decompress(idat)
        self.assertEqual(len(raw), height * (width + 1))

    def test_save_png_writes_decodable_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "qr.png"
            qr.save_png(str(out), URL, scale=6)
            data = out.read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(len(data), 100)

    def test_too_long_input_is_rejected(self):
        with self.assertRaises(qr.QrTooLong):
            qr.encode("http://x/" + "a" * 400)
        with self.assertRaises(qr.QrError):
            qr.encode("")

    def test_versions_grow_with_payload(self):
        lengths = [20, 40, 80, 120, 180]
        sizes = [len(qr.encode("http://x/" + "a" * (n - 9))) for n in lengths]
        self.assertEqual(sizes, sorted(sizes))
        self.assertGreaterEqual(sizes[-1], 41, "长内容应使用更高版本")


if __name__ == "__main__":
    unittest.main(verbosity=2)
