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

用法：
    python tools/fetch_skin.py            # 使用当前 dufs 版本
    python tools/fetch_skin.py 0.47.0     # 指定版本
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
FILES = ("index.html", "index.css", "index.js", "favicon.ico")

# jsDelivr 是 GitHub 的公共 CDN，比 raw.githubusercontent 更容易访问
MIRRORS = [
    "https://cdn.jsdelivr.net/gh/sigoden/dufs@{tag}/assets/{name}",
    "https://raw.githubusercontent.com/sigoden/dufs/{tag}/assets/{name}",
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

   升级 dufs 时请同步执行：python tools/fetch_skin.py <版本号>
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


def fetch(tag: str, name: str) -> bytes:
    errs = []
    for tpl in MIRRORS:
        url = tpl.format(tag=tag, name=name)
        try:
            data = http_get(url)
            if data[:200].lstrip().startswith(b"<html"):
                raise ValueError("返回的不是原始文件（可能是 HTML 页面）")
            print(f"  [ok] {name} <- {url}")
            return data
        except Exception as e:  # noqa: BLE001
            errs.append(f"{url}: {e}")
    raise RuntimeError(f"下载 {name} 失败：\n  " + "\n  ".join(errs))


def detect_version() -> str:
    """从已安装的 dufs 读版本号，用于对齐 assets 版本。"""
    from core import dufsbin  # noqa: PLC0415

    found = dufsbin.find_dufs()
    if not found:
        return ""
    v = dufsbin.version(found) or ""
    m = re.search(r"(\d+\.\d+\.\d+)", v)
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?", default="",
                    help="dufs 版本号，如 0.47.0；省略则自动探测已安装的 dufs")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    tag = args.version or detect_version()
    if not tag:
        print("[X] 未指定版本，也未能从已安装的 dufs 探测到版本")
        return 1
    tag = tag if tag.startswith("v") else "v" + tag
    print(f"[1/3] 目标版本：{tag}")

    ASSETS.mkdir(parents=True, exist_ok=True)
    print("[2/3] 下载官方 assets")
    for name in FILES:
        data = fetch(tag, name)
        if name == "index.css":
            (ASSETS / name).write_bytes(
                data.decode("utf-8").encode("utf-8"))
            (ASSETS / name).write_text(
                data.decode("utf-8") + DARK_OVERRIDE + VISUAL_OVERRIDE,
                encoding="utf-8")
        else:
            (ASSETS / name).write_bytes(data)

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
