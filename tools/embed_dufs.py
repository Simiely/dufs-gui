"""把 dufs 二进制以 base64 形式内嵌进 Python 源码（可选，追求极致自包含时使用）。

用法：
    python tools/embed_dufs.py                     # 读取 bin/dufs(.exe)
    python tools/embed_dufs.py --bin path/to/dufs.exe

生成 core/dufs_embedded.py。之后即使打包时忘了 --add-binary，
程序首次启动也能从内嵌数据释放出一个可用的 dufs。

代价：源码体积约为二进制的 1.33 倍（10 MB 的 dufs.exe → 约 13.4 MB 的 .py），
PyInstaller 分析和打包会明显变慢。若用 --add-binary 正常打包，不必执行本脚本。
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

CHUNK = 76 * 1000  # 每行约 76KB，避免单行过长拖慢解析


def default_binary(root: Path) -> Path:
    exe = root / "bin" / ("dufs.exe" if sys.platform.startswith("win") else "dufs")
    if not exe.exists():
        raise SystemExit(f"未找到 {exe}，请先运行 python tools/fetch_dufs.py")
    return exe


def generate(src: Path, out: Path) -> int:
    raw = src.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    lines = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write('"""自动生成，勿手动修改：内嵌的 dufs 二进制（base64）。\n\n')
        f.write(f"来源：{src.name}，原始大小 {len(raw)} 字节。\n")
        f.write('由 tools/embed_dufs.py 生成。\n"""\n\n')
        f.write("NAME = %r\n" % ("dufs.exe" if src.name.endswith(".exe") else "dufs"))
        f.write("SIZE = %d\n" % len(raw))
        f.write("DATA = (\n")
        for line in lines:
            f.write('    "%s"\n' % line)
        f.write(")\n")
    return len(raw)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default="", help="dufs 可执行文件路径")
    ap.add_argument("--out", default="", help="输出 py 文件路径")
    args = ap.parse_args()

    src = Path(args.bin) if args.bin else default_binary(root)
    out = Path(args.out) if args.out else root / "core" / "dufs_embedded.py"
    size = generate(src, out)
    print(f"已生成 {out}（原始 {size / 1024 / 1024:.2f} MB，"
          f"内嵌后 {out.stat().st_size / 1024 / 1024:.2f} MB）")


if __name__ == "__main__":
    main()
