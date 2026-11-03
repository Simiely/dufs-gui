"""下载资产完整性校验：固定版本 + 逐源 SHA256。

为什么需要这个模块：两个下载脚本都会从多个 GitHub 镜像取同一个文件。
镜像可能返回被篡改、过期或错误的内容，仅靠"像不像压缩包"（PK / gzip 魔数）
无法发现替换攻击，必须比对固定 SHA256。

校验和来源：优先使用上游官方 digest（GitHub Releases API 的 assets[].digest）。
拿不到时退化为 TOFU（首次信任）：首次下载计算并写回仓库内的校验和文件，
之后强制比对。TOFU 只能发现"下载后被替换"，**不等于上游签名**，
无法发现"首次下载即被投毒"，文档中不得把它说成等价的安全保证。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


class IntegrityError(RuntimeError):
    """内容与固定 SHA256 不一致。必须立即终止，禁止静默换源重试。"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> dict:
    """读取校验和清单；缺失或损坏都直接报错，不当作"没有校验和"继续下载。"""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise IntegrityError(f"缺少校验和文件：{path}") from e
    except OSError as e:
        raise IntegrityError(f"无法读取校验和文件：{path}（{e}）") from e
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise IntegrityError(f"校验和文件不是合法 JSON：{path}（{e}）") from e
    if not isinstance(doc, dict):
        raise IntegrityError(f"校验和文件结构无效（顶层应为对象）：{path}")
    return doc


def save(path: Path, doc: dict) -> None:
    """原子写回仓库内的校验和清单（TOFU 首次记录时使用）。"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def source_sha256(doc: dict, asset: str, source: str) -> str:
    """读取某资产在某下载源上的固定 SHA256。

    返回空串表示该来源尚未记录，由调用方按 TOFU 处理。
    来源不在清单里属于配置错误：必须拒绝下载，否则新增镜像会绕过校验。
    """
    entry = (doc.get("assets") or {}).get(asset)
    if not isinstance(entry, dict):
        raise IntegrityError(f"校验和清单缺少资产：{asset}")
    sources = entry.get("sources")
    if not isinstance(sources, dict) or source not in sources:
        raise IntegrityError(f"校验和清单缺少来源：{source}（资产 {asset}）")
    return str(sources.get(source) or "").strip().lower()


def record(doc: dict, asset: str, source: str, digest: str) -> None:
    """把首次下载算出的 SHA256 写进清单（TOFU）。"""
    entry = doc.setdefault("assets", {}).setdefault(asset, {})
    entry.setdefault("sources", {})[source] = digest


def verify(data: bytes, expected: str, asset: str, source: str) -> str:
    """比对 SHA256；不符时抛 IntegrityError（调用方不得继续换源）。"""
    actual = sha256_bytes(data)
    if expected and actual != expected:
        raise IntegrityError(
            f"{asset} 从 {source} 下载的内容 SHA256 不符\n"
            f"  期望：{expected}\n"
            f"  实际：{actual}\n"
            "已停止下载，且不会尝试其他镜像（防止静默换源）。\n"
            "请检查该镜像是否被篡改/返回了错误版本；确认无误后更新 "
            "tools/ 下的校验和清单再重试。")
    return actual
