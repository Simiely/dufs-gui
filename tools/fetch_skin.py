"""下载 dufs 官方 assets，并生成"只覆盖 CSS 变量"的深色皮肤。

为什么这样做（官方推荐路径，见 dufs README "Customize UI"）：

    dufs --assets my-assets-dir/
    "If you only need to make slight adjustments to the current UI, you copy
     dufs's assets directory and modify it accordingly."

自己另写一套 index.html / index.js 意味着要猜测 dufs 的内部契约：
数据节点写法、IndexData 字段、DOM 结构与 class 名、权限判定逻辑……
任何一处对不上就表现为"上传 / 下载 / 预览全部失效"，而且 dufs 端不报错。

改为：完整搬运官方 assets，只重写 CSS 变量。
这样所有交互逻辑都是官方 JS，功能正确性由官方保证，我们只负责配色。

版本固定在校验和清单里（tools/skin_checksums.json），不再"探测本机已安装的
dufs 版本"：GUI 自带的 dufs 与皮肤必须同版本，否则 HTML / JS 契约可能不一致。
每个下载源都要通过 SHA256 比对；哈希不符立即失败且不会静默换源。

用法：
    python tools/fetch_skin.py            # 使用清单中固定的版本
    python tools/fetch_skin.py 0.47.0     # 显式指定；必须与清单一致
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _integrity  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CHECKSUMS = Path(__file__).resolve().parent / "skin_checksums.json"
FILES = ("index.html", "index.css", "index.js", "favicon.ico")

# 源的名字必须与校验和清单里的 sources 键严格对应。
# jsDelivr 是 GitHub 的公共 CDN，比 raw.githubusercontent 更容易访问。
MIRRORS = [
    ("jsdelivr", "https://cdn.jsdelivr.net/gh/sigoden/dufs@{tag}/assets/{name}"),
    ("raw.githubusercontent.com",
     "https://raw.githubusercontent.com/sigoden/dufs/{tag}/assets/{name}"),
]

DARK_OVERRIDE = """
/* ==========================================================================
   DufsGui 深色皮肤 —— 只覆盖变量，不改动结构
   --------------------------------------------------------------------------
   本文件 = dufs 官方 index.css + 末尾的变量覆盖。
   官方 assets 目录里 index.css / index.js / favicon.ico 缺失时会自动回退内置版本，
   但 index.html 必须存在，且 HTML 与 JS 必须同版本，所以这里三者一并随包提供。

   官方本来就有一套 @media (prefers-color-scheme: dark) 的暗色配色，
   这里在末尾无条件重写同样的变量，使网页恒为深色（与桌面端默认深色一致），
   不再依赖访问者的系统偏好。

   升级 dufs 时请先更新 tools/skin_checksums.json，再执行
   python tools/fetch_skin.py（显式版本必须与清单一致）
   ========================================================================== */

:root {
  color-scheme: dark;
  --bg-primary: #14171c;
  --bg-secondary: #1b1e23;
  --bg-tertiary: #1b1e23;
  --bg-hover: #28303c;
  --text-primary: #e6e8ec;
  --text-secondary: #9aa4b2;
  --text-tertiary: #7d8794;
  --text-accent: #4f9cf9;
  --svg-primary: #e6e8ec;
  --svg-secondary: #9aa4b2;
  --svg-tertiary: #7d8794;
  --border-primary: #2e3540;
  --border-secondary: #3a4250;
}
"""

VISUAL_OVERRIDE = r"""/* ==========================================================================
   DufsGui 视觉增强 —— 只改样式，不动结构与脚本
   --------------------------------------------------------------------------
   官方界面偏朴素（GitHub 早期风格）：贴边表格、无圆角、控件直接贴在栏上。
   这里在**不触碰 HTML / JS 的前提下**做视觉改造：卡片化表格、胶囊面包屑、
   圆形控件、渐变顶条、发光搜索框、自定义滚动条。

   之所以能放心改：所有交互（上传/下载/预览/编辑/搜索/权限）都由官方
   index.js 提供，CSS 只影响观感，不影响任何功能路径。
   ========================================================================== */

/* 顶部渐变装饰条 */
body::before {
  content: "";
  position: fixed;
  inset: 0 0 auto 0;
  height: 3px;
  background: linear-gradient(90deg, #4f9cf9, #7c5cff, #3fb950);
  z-index: 100;
}

/* ---------- 顶栏 ---------- */
.head {
  padding: 14px 22px;
  gap: 12px;
  background-color: rgba(27, 30, 35, 0.92) !important;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 1px 0 var(--border-primary), 0 8px 24px rgba(0, 0, 0, 0.28);
}

/* ---------- 面包屑：胶囊化 ---------- */
.breadcrumb {
  font-size: 1.05em;
  font-weight: 600;
}

.breadcrumb > a,
.breadcrumb > b {
  padding: 4px 10px;
  border-radius: 8px;
  transition: background .15s ease, color .15s ease;
}

.breadcrumb > a:hover {
  background: rgba(79, 156, 249, 0.14);
  text-decoration: none;
}

.breadcrumb > b {
  background: rgba(79, 156, 249, 0.14);
  color: var(--text-accent) !important;
}

.breadcrumb > .separator { opacity: .5; }
.breadcrumb svg { fill: var(--text-accent); }

/* ---------- 工具按钮：圆形化 ---------- */
.toolbox { gap: 2px; }

.toolbox .control {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  padding: 0;
  transition: background .15s ease;
}

.toolbox .control:hover { background: rgba(79, 156, 249, 0.16); }
.toolbox > a, .toolbox > div { height: auto; }

/* ---------- 搜索框 ---------- */
.searchbar {
  width: 264px;
  height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  align-items: center;
  border: 1px solid var(--border-primary);
  transition: border-color .15s ease, box-shadow .15s ease;
}

.searchbar:focus-within {
  border-color: var(--text-accent);
  box-shadow: 0 0 0 3px rgba(79, 156, 249, 0.15);
}

.searchbar #search { font-size: 14px; padding: 0 0 0 6px; }

/* ---------- 主体留白 ---------- */
.main {
  padding: 18px 22px 40px;
  max-width: 1280px;
  margin: 0 auto;
}

/* ---------- 文件表格：卡片化 ---------- */
.paths-table {
  border-collapse: separate;
  border-spacing: 0 6px;
  width: 100%;
}

.paths-table th {
  padding: 6px 14px;
  font-size: 11px;
  letter-spacing: .06em;
  text-transform: uppercase;
  opacity: .75;
}

.paths-table tbody tr {
  background: var(--bg-secondary);
  transition: background .13s ease;
}

.paths-table tbody tr:hover { background: var(--bg-hover); }

.paths-table tbody td {
  padding: 11px 14px;
  border-top: 1px solid var(--border-primary);
  border-bottom: 1px solid var(--border-primary);
}

.paths-table tbody td:first-child {
  border-left: 1px solid var(--border-primary);
  border-top-left-radius: 10px;
  border-bottom-left-radius: 10px;
}

.paths-table tbody td:last-child {
  border-right: 1px solid var(--border-primary);
  border-top-right-radius: 10px;
  border-bottom-right-radius: 10px;
}

/* 文件名链接 */
.path a { color: var(--text-primary) !important; }
.path a:hover { color: var(--text-accent) !important; text-decoration: none; }
.path svg { height: 18px; }

/* 操作按钮 */
.paths-table .cell-actions { gap: 4px; }

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  padding: 0;
  transition: background .13s ease;
}

.action-btn:hover { background: rgba(79, 156, 249, 0.16); }

/* ---------- 空文件夹 ---------- */
.empty-folder {
  font-style: normal;
  padding: 52px 20px;
  text-align: center;
  color: var(--text-secondary);
  border: 1px dashed var(--border-primary);
  border-radius: 12px;
}

.empty-folder::before {
  content: "📭";
  display: block;
  font-size: 32px;
  margin-bottom: 10px;
  opacity: .75;
}

/* ---------- 上传进度 ---------- */
.uploaders-table { border-collapse: separate; border-spacing: 0 4px; }
.uploaders-table th { padding: 6px 12px; font-size: 11px; opacity: .75; }
.uploader {
  background: var(--bg-secondary);
  border-radius: 10px;
}

/* ---------- 编辑器 ---------- */
.editor {
  border-radius: 10px;
  padding: 14px;
  font-family: Consolas, "SF Mono", Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
}

/* ---------- 滚动条 ---------- */
::-webkit-scrollbar { width: 11px; height: 11px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb {
  background: #39414f;
  border-radius: 6px;
  border: 2px solid var(--bg-primary);
}
::-webkit-scrollbar-thumb:hover { background: #4a5464; }

::selection { background: rgba(79, 156, 249, 0.3); }

/* ---------- 窄屏 ---------- */
@media (max-width: 640px) {
  .head { padding: 10px 12px; }
  .main { padding: 12px 12px 32px; }
  .searchbar { width: 160px; }
  .paths-table .cell-mtime { display: none; }
}
"""



def http_get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "dufs-gui"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def normalize_tag(version: str) -> str:
    v = (version or "").strip()
    return v if v.startswith("v") else "v" + v


def fetch(tag: str, name: str, doc: dict, checksums: Path | None = None) -> bytes:
    """按源下载并校验单个官方 assets 文件。

    网络失败可以换下一个源（逐条打印原因）；SHA256 不符属于硬失败，
    立即抛出 IntegrityError，不尝试其他镜像（避免静默换源）。
    """
    checksums = checksums or CHECKSUMS
    errs = []
    for source, tpl in MIRRORS:
        url = tpl.format(tag=tag, name=name)
        try:
            data = http_get(url)
        except Exception as e:  # noqa: BLE001
            msg = f"[{source}] {url}: {e}"
            print(f"  [{source}] 下载失败：{type(e).__name__}: {e}")
            errs.append(msg)
            continue

        if data[:200].lstrip().startswith(b"<"):
            # 404 / 代理错误页通常以 <html 或 <!doctype 开头；不能把这种内容
            # 当成皮肤文件，否则 TOFU 会把错误页的哈希记进清单
            msg = f"[{source}] 返回的不是原始文件（可能是 HTML 错误页）"
            print("  " + msg)
            errs.append(msg)
            continue

        expected = _integrity.source_sha256(doc, name, source)
        # 哈希不符直接抛 IntegrityError，不进入下一个镜像
        digest = _integrity.verify(data, expected, name, source)

        if not expected:
            # 首次信任（TOFU）：记录哈希后再写入仓库
            _integrity.record(doc, name, source, digest)
            try:
                _integrity.save(checksums, doc)
            except OSError as e:
                raise RuntimeError(
                    f"已下载 {name} 但无法写回校验和文件：{checksums}（{e}）") from e
            print(f"  [!] TOFU：已记录 {name} / {source} 的 SHA256 {digest}\n"
                  "      该策略只能发现后续下载被替换，不能证明本次下载未被投毒。")

        print(f"  [ok] {name} <- {url}")
        return data
    raise RuntimeError(f"下载 {name} 失败：\n  " + "\n  ".join(errs))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?", default="",
                    help="dufs 版本号，如 0.47.0；省略则使用校验和清单里的固定版本")
    args = ap.parse_args()

    try:
        doc = _integrity.load(CHECKSUMS)
    except _integrity.IntegrityError as e:
        print(f"[X] {e}")
        return 1

    pinned = normalize_tag(str(doc.get("pinned_version") or ""))
    if not pinned:
        print(f"[X] 校验和清单缺少 pinned_version：{CHECKSUMS}")
        return 1
    tag = normalize_tag(args.version) if args.version else pinned
    if tag != pinned:
        print(f"[X] 校验和清单只覆盖 {pinned}，拒绝使用 {tag}。\n"
              "    升级 dufs 请先更新 tools/skin_checksums.json（含官方 SHA256）。")
        return 1
    print(f"[1/3] 目标版本：{tag}")

    ASSETS.mkdir(parents=True, exist_ok=True)
    print("[2/3] 下载官方 assets")
    try:
        for name in FILES:
            data = fetch(tag, name, doc)
            if name == "index.css":
                (ASSETS / name).write_text(
                    data.decode("utf-8") + DARK_OVERRIDE + VISUAL_OVERRIDE,
                    encoding="utf-8")
            else:
                (ASSETS / name).write_bytes(data)
    except (_integrity.IntegrityError, RuntimeError) as e:
        print(f"[X] {e}")
        return 1

    print("[3/3] 写入版本标记并校验")
    (ASSETS / "ASSETS_VERSION").write_text(tag.lstrip("v") + "\n",
                                           encoding="utf-8")
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    ok = True
    for must in ('<template id="index-data">', "__ASSETS_PREFIX__index.js"):
        if must not in html:
            print(f"  [X] index.html 缺少 {must}")
            ok = False
    print(f"  皮肤就绪：{ASSETS}（{', '.join(FILES)}）" if ok else "  校验未通过")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
