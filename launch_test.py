# -*- coding: utf-8 -*-
"""GUI 启动自检：验证 DPI 感知与缩放是否生效（不执行任何清理）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcclean.utils import winapi

winapi.enable_dpi_awareness()
from pcclean.ui.app import App  # noqa: E402

app = App()
for _ in range(12):
    app.update()
    time.sleep(0.25)
tabs = [app.nb.tab(t, "text") for t in app.nb.tabs()]
print("dpi =", app._dpi, " scale =", round(app.scale, 2),
      " screen =", app.winfo_screenwidth(), "x", app.winfo_screenheight())
print("tree rowheight =", app.tk.call("ttk::style", "configure", "Treeview", "-rowheight"))
print("GUI OK, tabs =", tabs)
app.destroy()
print("CLOSED OK")
