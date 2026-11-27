# -*- coding: utf-8 -*-
"""空间分析自检：盘符枚举、大文件、重复文件（在临时目录里验证）。"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcclean.engine import space

print("drives:", [(d["letter"], round(d["total"] / 1024 ** 3, 1), round(d["free"] / 1024 ** 3, 1))
                  for d in space.list_drives()])

d = tempfile.mkdtemp(prefix="space_test_")
with open(os.path.join(d, "big.bin"), "wb") as f:
    f.write(os.urandom(5 * 1024 * 1024))
data = os.urandom(2 * 1024 * 1024)
for n in ("dup1.bin", "dup2.bin"):
    with open(os.path.join(d, n), "wb") as f:
        f.write(data)

large = space.find_large_files(d, 1 * 1024 * 1024)
print("large:", [(os.path.basename(p), s) for p, s in large])
dups = space.find_duplicates(d, 1 * 1024 * 1024)
print("dups:", [(g["size"], len(g["files"])) for g in dups])
shutil.rmtree(d, ignore_errors=True)
print("SPACE OK")
