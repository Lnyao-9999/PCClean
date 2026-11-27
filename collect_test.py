# -*- coding: utf-8 -*-
"""完整只读扫描：复现 GUI「开始扫描」的管线（不删除任何东西）。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcclean.engine import rules, scanner, drivers
from pcclean.utils import winapi

def dyn():
    cands = []
    la = os.environ.get("LOCALAPPDATA", "")
    if la and os.path.isdir(la):
        for name in os.listdir(la):
            if "updater" in name.lower():
                p = os.path.join(la, name)
                if os.path.isdir(p) and not winapi.is_reparse_point(p):
                    cands.append({"path": p, "kind": "dir", "category": "更新包/安装缓存",
                                  "label": "更新器缓存", "risk": "B", "action": "quarantine",
                                  "evidence": "更新器安装包"})
    cands += rules.detect_versioned_dirs(r"%LOCALAPPDATA%\Claude-3p\claude-code", r"\d+\.\d+", "Claude")
    cands += rules.detect_versioned_dirs(r"%LOCALAPPDATA%\OpenAI\Codex\bin", r"[0-9a-f]{8,}", "Codex")
    cands += rules.detect_versioned_dirs(r"%LOCALAPPDATA%\OpenAI\Codex\runtimes\cua_node", r"[0-9a-f]{8,}", "Codex")
    return cands

t0 = time.time()
cands = rules.build_rules() + drivers.nvidia_cache_targets() + dyn()
items = scanner.collect(cands)
seen, uniq = set(), []
for it in items:
    k = os.path.normcase(it.path)
    if k in seen:
        continue
    seen.add(k)
    uniq.append(it)
tot = sum(i.size for i in uniq)
auto = sum(i.size for i in uniq if i.risk == "A")
print(f"扫描完成，耗时 {time.time()-t0:.1f}s，共 {len(uniq)} 项，合计 {tot/1024**3:.2f} GB，A级 {auto/1024**3:.2f} GB")
print("--- TOP 20 ---")
for it in uniq[:20]:
    print(f"{it.human_size():>12}  [{it.risk}]  {it.label}  <- {it.path}")
print("--- 按风险统计 ---")
from collections import Counter
print(Counter(it.risk for it in uniq))
