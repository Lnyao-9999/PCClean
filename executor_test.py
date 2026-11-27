# -*- coding: utf-8 -*-
"""执行器安全测试：在临时目录里验证「直接删除」与「隔离区」两条路径（不碰真实数据）。"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcclean.engine import executor, safety, scanner
from pcclean.utils import winapi


def make_dir(n_files=20, size_mb=2):
    d = tempfile.mkdtemp(prefix="pcclean_test_")
    for i in range(n_files):
        with open(os.path.join(d, f"f{i}.bin"), "wb") as f:
            f.write(os.urandom(size_mb * 1024 * 1024 // n_files))
    return d


def size_of(d):
    s, _ = scanner.dir_size(d)
    return s


# ---- 1. 直接删除：应该真正删除、返回成功、并释放空间 ----
d1 = make_dir()
before = winapi.get_free_space("C:\\")[0]
item = scanner.ScanItem(path=d1, kind="dir", category="测试", label="测试直接删除",
                        size=size_of(d1), files=1, risk="A", action="delete", evidence="test")
r = executor.perform([item], mode="delete")
after = winapi.get_free_space("C:\\")[0]
print("[直接删除] 结果:", r["cleaned"], r["skipped"], "| 目录还在?", os.path.exists(d1),
      "| 释放字节(近似):", after - before)

# ---- 2. 隔离区：应该移走、原路径消失、可恢复、可彻底删除 ----
d2 = make_dir()
item2 = scanner.ScanItem(path=d2, kind="dir", category="测试", label="测试隔离",
                         size=size_of(d2), files=1, risk="A", action="quarantine", evidence="test")
r2 = executor.perform([item2], mode="quarantine")
entries = safety.quarantine_entries()
mine = [e for e in entries if e.get("original", "").lower().endswith(os.path.basename(d2).lower())]
print("[隔离区] 结果:", r2["cleaned"], r2["skipped"], "| 原目录还在?", os.path.exists(d2),
      "| 隔离条目:", len(mine))
if mine:
    e = mine[0]
    print("  隔离路径存在?", os.path.exists(e["quarantined"]))
    ok_restore = safety.restore(e)
    print("  恢复成功?", ok_restore, "| 原目录恢复?", os.path.exists(d2))
    # 再隔离一次然后彻底删除
    item3 = scanner.ScanItem(path=d2, kind="dir", category="测试", label="测试隔离2",
                             size=size_of(d2), files=1, risk="A", action="quarantine", evidence="test")
    executor.perform([item3], mode="quarantine")
    mine2 = [x for x in safety.quarantine_entries()
             if x.get("original", "").lower().endswith(os.path.basename(d2).lower())]
    if mine2:
        print("  彻底删除隔离项:", safety.delete_quarantined(mine2[0]), "| 隔离路径还在?", os.path.exists(mine2[0]["quarantined"]))

# ---- 3. 通配符合并项（一个条目含多个目标）----
dirs = [make_dir(n_files=3, size_mb=1) for _ in range(3)]
item4 = scanner.ScanItem(path=dirs[0], kind="dir", category="测试", label="合并项目(3 项)",
                         size=sum(size_of(d) for d in dirs), files=9, risk="A",
                         action="delete", evidence="test", targets=dirs)
r3 = executor.perform([item4], mode="delete")
print("[合并删除] 结果:", r3["cleaned"], r3["skipped"],
      "| 全部删除?", all(not os.path.exists(d) for d in dirs))

print("== 执行器测试完成 ==")
