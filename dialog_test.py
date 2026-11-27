# -*- coding: utf-8 -*-
"""对话框自检：打开「隔离区管理」，确认列表/体积统计不报错。"""
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcclean.ui.app import App

app = App()
for _ in range(10):
    app.update()
    time.sleep(0.2)
app.tab_clean.quarantine_dialog()
for _ in range(30):
    app.update()
    time.sleep(0.12)
for w in list(app.winfo_children()):
    if isinstance(w, tk.Toplevel):
        w.destroy()
app.destroy()
print("QUARANTINE DIALOG OK")
