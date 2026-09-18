# -*- coding: utf-8 -*-
"""Rename the ASCII PyInstaller result using UTF-8 Python paths.

Passing Chinese text in a PyInstaller --name argument is unreliable on some
Windows console code pages.  Rename only after the build has completed.
"""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
dist = root / "release-dist"
source_dir = dist / "option_seller_ledger"
target_dir = dist / "期权卖方算账神器"
source_exe = source_dir / "option_seller_ledger.exe"
target_exe_name = "期权卖方算账神器.exe"

if not source_exe.is_file():
    raise SystemExit(f"Build output missing: {source_exe}")
if target_dir.exists():
    raise SystemExit(f"Target release folder already exists: {target_dir}")

# Antivirus scanners can temporarily lock a just-created PyInstaller folder.
# Copying is reliable in that window and leaves the ASCII build cache intact.
shutil.copytree(source_dir, target_dir)
(target_dir / "option_seller_ledger.exe").rename(target_dir / target_exe_name)
print(target_dir / target_exe_name)
