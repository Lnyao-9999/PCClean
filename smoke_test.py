# -*- coding: utf-8 -*-
"""只读冒烟测试：验证各引擎能正确导入与运行（不删除/不卸载/不动驱动）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pcclean import config
from pcclean.engine import rules, scanner, safety, drivers, ram, migrate, uninstall
from pcclean.utils import winapi

print("== import ok, admin =", winapi.is_admin())

r = rules.build_rules()
print("rules count:", len(r))
print("expand sample:", scanner.expand_glob(r[0]["path"])[:3])

print("protected System32:", safety.is_protected(r"C:\Windows\System32"))
print("protected Installer:", safety.is_protected(r"C:\Windows\Installer"))
print("not protected Temp:", safety.is_protected(r"%s\AppData\Local\Temp" % os.environ["USERPROFILE"]))

print("ram:", ram.ram_info())
print("memory compression:", ram.memory_compression_enabled())

print("nv driver:", drivers.current_driver_version())
print("nv current inf:", sorted(drivers.current_inf_paths()))
olds = drivers.old_packages()
print("nv old packages:", len(olds), [(p["published"], p["original"]) for p in olds][:10])
print("nv cache targets:", len(drivers.nvidia_cache_targets()))

det = migrate.detect()
print("migrate:", [(d["app"], d["exists"], round(d["size"]/1024/1024, 1)) for d in det])

apps = uninstall.list_apps()
print("apps:", len(apps))
for a in apps[:5]:
    print("  -", a["name"], a.get("kind"), a.get("size_kb"))

print("== ALL OK ==")
