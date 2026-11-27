# -*- coding: utf-8 -*-
"""空间分析页自检：布局可见性 + 勾选交互（不执行删除）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcclean.utils import winapi

winapi.enable_dpi_awareness()
from pcclean.ui.app import App  # noqa: E402

app = App()
app.nb.select(app.tab_space)
for _ in range(15):
    app.update()
    time.sleep(0.1)

t = app.tab_space
print("SpaceTab: %dx%d" % (t.winfo_width(), t.winfo_height()))
for ch in t.winfo_children():
    print("  child %-12s mapped=%-5s y=%-5d h=%-5d" % (
        ch.__class__.__name__, ch.winfo_ismapped(), ch.winfo_y(), ch.winfo_height()))
print("tree_big columns:", t.tree_big["columns"])
print("tree_dup columns:", t.tree_dup["columns"])

# 模拟插入 3 行并测试勾选
for i in range(3):
    t.tree_big.insert("", "end", iid=str(i), values=("☐", f"f{i}.bin", "10.0 MB", f"D:\\tmp\\f{i}.bin"))
t.big = [("D:\\tmp\\f0.bin", 10 * 1024 * 1024), ("D:\\tmp\\f1.bin", 20 * 1024 * 1024),
         ("D:\\tmp\\f2.bin", 30 * 1024 * 1024)]
t._checked_big = set(t.tree_big.get_children())
t._refresh_checks(t.tree_big, t._checked_big)
app.update()
marks = [t.tree_big.item(i, "values")[0] for i in t.tree_big.get_children()]
print("after select_all, check marks:", marks)
print("bar_hint:", t.bar_hint.cget("text"))
t.select_none_big()
app.update()
marks2 = [t.tree_big.item(i, "values")[0] for i in t.tree_big.get_children()]
print("after select_none, check marks:", marks2)
app.destroy()
print("DIAG OK")
