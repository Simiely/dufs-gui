"""P0-1 供应链完整性：固定版本、逐源 SHA256、拒绝静默换源、安全解包。"""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import _integrity  # noqa: E402
import fetch_dufs  # noqa: E402
import fetch_skin  # noqa: E402

PINNED = "v0.47.0"


def _zip_bytes(name: str = "dufs.exe", payload: bytes = b"fake-dufs") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, payload)
    return buf.getvalue()


def _tar_bytes(member: str = "dufs", payload: bytes = b"fake-dufs") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo(member)
        info.size = len(payload)
        t.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _doc_for(target: str, sources: dict[str, str], ext: str) -> dict:
    triple = fetch_dufs.TARGETS[target][0]
    name = f"dufs-{PINNED}-{triple}.{ext}"
    return {"assets": {target: {"filename": name, "sources": dict(sources)}}}


class ManifestTest(unittest.TestCase):
    def test_pinned_version_matches_assets_version(self):
        doc = _integrity.load(TOOLS / "dufs_checksums.json")
        skin = _integrity.load(TOOLS / "skin_checksums.json")
        local = (ROOT / "assets" / "ASSETS_VERSION").read_text(
            encoding="utf-8").strip()
        self.assertEqual(doc["pinned_version"].lstrip("v"), local)
        self.assertEqual(skin["pinned_version"], doc["pinned_version"])
        self.assertEqual(doc["strategy"], "upstream-digest")
        self.assertEqual(skin["strategy"], "upstream-digest")

    def test_every_dufs_asset_has_per_source_sha256(self):
        doc = _integrity.load(TOOLS / "dufs_checksums.json")
        mirrors = {name for name, _ in fetch_dufs.MIRRORS}
        self.assertEqual(set(doc["mirrors"]), mirrors)
        for target, entry in doc["assets"].items():
            triple, ext, _ = fetch_dufs.TARGETS[target]
            expected_name = f"dufs-{doc['pinned_version']}-{triple}.{ext}"
            self.assertEqual(entry["filename"], expected_name)
            self.assertEqual(set(entry["sources"]), mirrors)
            for source, digest in entry["sources"].items():
                self.assertRegex(digest, r"^[0-9a-f]{64}$", (target, source))
                self.assertEqual(digest, entry["sha256"], (target, source))

    def test_every_skin_file_has_per_source_sha256(self):
        doc = _integrity.load(TOOLS / "skin_checksums.json")
        mirrors = {name for name, _ in fetch_skin.MIRRORS}
        self.assertEqual(set(doc["mirrors"]), mirrors)
        self.assertEqual(set(doc["assets"]), set(fetch_skin.FILES))
        for name, entry in doc["assets"].items():
            self.assertEqual(set(entry["sources"]), mirrors, name)
            for source, digest in entry["sources"].items():
                self.assertRegex(digest, r"^[0-9a-f]{64}$", (name, source))

    def test_local_upstream_files_match_skin_manifest(self):
        """未改写的三个文件必须与官方哈希一致；index.css 因覆盖层另行校验。

        Windows 工作区可能被 Git autocrlf 转成 CRLF，文本文件先归一化再比对；
        favicon.ico 是二进制，必须按原字节比对。
        """
        doc = _integrity.load(TOOLS / "skin_checksums.json")
        for name in ("index.html", "index.js"):
            data = (ROOT / "assets" / name).read_bytes()
            self.assertEqual(_integrity.sha256_bytes(data.replace(b"\r\n", b"\n")),
                             doc["assets"][name]["sha256"], name)
        favicon = (ROOT / "assets" / "favicon.ico").read_bytes()
        self.assertEqual(_integrity.sha256_bytes(favicon),
                         doc["assets"]["favicon.ico"]["sha256"], "favicon.ico")
        css = (ROOT / "assets" / "index.css").read_text(encoding="utf-8")
        self.assertIn(fetch_skin.DARK_OVERRIDE, css)
        self.assertIn(fetch_skin.VISUAL_OVERRIDE, css)


class FetchDufsTest(unittest.TestCase):
    def test_hash_mismatch_fails_without_trying_next_mirror(self):
        doc = _doc_for("win64", {name: "0" * 64 for name, _ in fetch_dufs.MIRRORS}, "zip")
        calls: list[str] = []

        def fake_get(url: str, timeout: int = 90) -> bytes:
            calls.append(url)
            return _zip_bytes()

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(fetch_dufs, "_http_get", fake_get):
            with self.assertRaises(SystemExit) as cm:
                fetch_dufs.download(PINNED, "win64", Path(td), doc=doc)
            self.assertIn("SHA256", str(cm.exception))
            self.assertEqual(len(calls), 1, "哈希不符后不得继续尝试其他镜像")

    def test_network_error_tries_next_mirror(self):
        data = _zip_bytes()
        digest = _integrity.sha256_bytes(data)
        doc = _doc_for("win64", {name: digest for name, _ in fetch_dufs.MIRRORS}, "zip")
        calls: list[str] = []

        def fake_get(url: str, timeout: int = 90) -> bytes:
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.URLError("mirror down")
            return data

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(fetch_dufs, "_http_get", fake_get):
            dest = fetch_dufs.download(PINNED, "win64", Path(td), doc=doc)
            self.assertEqual(len(calls), 2)
            self.assertEqual(dest.read_bytes(), b"fake-dufs")

    def test_tar_member_with_traversal_is_rejected(self):
        data = _tar_bytes("../dufs")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                fetch_dufs._extract_tar(data, Path(td) / "dufs", "dufs")

    def test_tar_symlink_is_rejected(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            info = tarfile.TarInfo("dufs")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            t.addfile(info)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                fetch_dufs._extract_tar(buf.getvalue(), Path(td) / "dufs", "dufs")

    def test_tar_extract_uses_data_filter(self):
        src = (TOOLS / "fetch_dufs.py").read_text(encoding="utf-8")
        self.assertIn('filter="data"', src)

    def test_tofu_records_and_persists_checksum(self):
        data = _zip_bytes()
        doc = _doc_for("win64", {name: "" for name, _ in fetch_dufs.MIRRORS}, "zip")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            checksums = out / "checksums.json"
            with mock.patch.object(fetch_dufs, "_http_get", lambda *a, **k: data):
                dest = fetch_dufs.download(PINNED, "win64", out, doc=doc,
                                           checksums=checksums)
            self.assertEqual(dest.read_bytes(), b"fake-dufs")
            expected = _integrity.sha256_bytes(data)
            self.assertEqual(doc["assets"]["win64"]["sources"]["github"], expected)
            saved = _integrity.load(checksums)
            self.assertEqual(saved["assets"]["win64"]["sources"]["github"], expected)

    def test_main_refuses_non_pinned_version(self):
        with mock.patch.object(sys, "argv",
                               ["fetch_dufs.py", "--version", "v0.48.0"]):
            with self.assertRaises(SystemExit) as cm:
                fetch_dufs.main()
            self.assertIn("拒绝下载", str(cm.exception))


class FetchSkinTest(unittest.TestCase):
    def test_hash_mismatch_fails_without_trying_next_mirror(self):
        good = b"body{}"
        bad = b"tampered"
        doc = {"assets": {"index.css": {
            "sha256": _integrity.sha256_bytes(good),
            "sources": {name: _integrity.sha256_bytes(good)
                        for name, _ in fetch_skin.MIRRORS}}}}
        calls: list[str] = []

        def fake_get(url: str, timeout: int = 40) -> bytes:
            calls.append(url)
            return bad

        with mock.patch.object(fetch_skin, "http_get", fake_get):
            with self.assertRaises(_integrity.IntegrityError):
                fetch_skin.fetch(PINNED, "index.css", doc)
        self.assertEqual(len(calls), 1, "哈希不符后不得继续尝试其他镜像")

    def test_network_error_tries_next_mirror(self):
        data = b"body{}"
        digest = _integrity.sha256_bytes(data)
        doc = {"assets": {"index.css": {
            "sha256": digest,
            "sources": {name: digest for name, _ in fetch_skin.MIRRORS}}}}
        calls: list[str] = []

        def fake_get(url: str, timeout: int = 40) -> bytes:
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.URLError("cdn down")
            return data

        with mock.patch.object(fetch_skin, "http_get", fake_get):
            self.assertEqual(fetch_skin.fetch(PINNED, "index.css", doc), data)
        self.assertEqual(len(calls), 2)

    def test_main_refuses_non_pinned_version(self):
        with mock.patch.object(sys, "argv", ["fetch_skin.py", "0.48.0"]):
            self.assertEqual(fetch_skin.main(), 1)


if __name__ == "__main__":
    unittest.main()
