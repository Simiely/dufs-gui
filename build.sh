#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x "bin/dufs" ]; then
  echo "[!] 未找到 bin/dufs，请先执行: python3 tools/fetch_dufs.py"
  exit 1
fi

python3 -m PyInstaller --version >/dev/null 2>&1 || python3 -m pip install -U pyinstaller
# DUFS_GUI_MODE=onefile|onedir   DUFS_GUI_CONSOLE=1 诊断版   DUFS_GUI_COLLECT_TK=1 强制收集 Tcl/Tk
python3 -m PyInstaller --noconfirm --clean DufsGui.spec
echo "[√] 完成：dist/DufsGui"
