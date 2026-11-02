"""网页皮肤的端到端验证（依赖 node + jsdom，缺失则跳过）。

桌面 GUI 无法在无浏览器环境渲染，但网页皮肤可以用 jsdom 真实执行，
因此这些断言是确定性可判定的，不能因为"跑不了浏览器"就放弃验证。
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("node"), "需要 node")
class SkinE2ETest(unittest.TestCase):
    def test_skin_check_passes(self):
        script = ROOT / "tools" / "check_skin.js"
        self.assertTrue(script.is_file(), "缺少 tools/check_skin.js")
        r = subprocess.run(["node", str(script)], capture_output=True,
                           text=True, timeout=120, cwd=str(ROOT))
        if "SKIP" in r.stdout:
            self.skipTest("jsdom 未安装")
        self.assertEqual(r.returncode, 0,
                         f"皮肤检查未通过：\n{r.stdout}\n{r.stderr}")

    def test_placeholder_is_unique_and_in_data_node(self):
        """占位符必须唯一，且落在 #index-data 里。

        若同时出现在注释中，任何"只替换第一处"的实现都会漏掉真正的数据节点，
        表现为空表格 + 上传下载全部失效。
        """
        html = (ROOT / "assets" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("__INDEX_DATA__"), 1, "占位符必须全文唯一")
        i = html.find('id="index-data"')
        self.assertGreater(i, 0)
        seg = html[i:i + 120]
        self.assertIn("__INDEX_DATA__", seg, "占位符必须在 #index-data 节点内")
