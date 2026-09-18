# -*- coding: utf-8 -*-
"""Create a UTF-8 named ZIP from the finished Chinese release folder."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
dist = root / "release-dist"
folder = dist / "期权卖方算账神器"
zip_base = dist / "期权卖方算账神器-Windows"
if not folder.is_dir():
    raise SystemExit(f"Release folder missing: {folder}")
zip_path = zip_base.with_suffix(".zip")
if zip_path.exists():
    zip_path.unlink()
shutil.make_archive(str(zip_base), "zip", root_dir=dist, base_dir=folder.name)
print(zip_path)
