# -*- coding: utf-8 -*-
"""安全引擎：保护名单、风险分级、隔离区与回滚、重复文件识别。"""
import glob
import hashlib
import json
import os
import shutil
import time

from ..config import (NEVER_DELETE_PREFIXES, NEVER_DELETE_NAMES, APP_DIR,
                      HISTORY_DIR, quarantine_root_for, ensure_app_dirs)
from ..utils import winapi

# 风险 → 是否需要用户确认
RISK_CONFIRM = {"A": False, "B": True, "C": True, "D": True}


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def is_protected(path: str) -> bool:
    """判断路径是否受保护（绝对禁止自动删）。"""
    np = _norm(path)
    for prefix in NEVER_DELETE_PREFIXES:
        pfx = _norm(prefix)
        if np == pfx or np.startswith(pfx.rstrip("\\") + "\\") or np.startswith(pfx + "\\"):
            return True
    base = os.path.basename(np.rstrip("\\"))
    if base.lower() in NEVER_DELETE_NAMES:
        return True
    return False


def is_safe_to_touch(path: str) -> bool:
    """额外护栏：junction 不跟随；OneDrive 占位不删。"""
    if winapi.is_reparse_point(path):
        return False
    if winapi.is_cloud_placeholder(path):
        return False
    return True


def needs_confirm(item) -> bool:
    if item.risk in ("C", "D"):
        return True
    if item.risk == "B":
        return True
    return False


def quarantine(path: str, reason: str, size: int = 0) -> dict:
    """把 path 移动到隔离区，返回清单条目。

    优先放到同卷隔离区（rename 秒级）；若该卷根目录不可写（非系统盘常见），
    自动回退到用户目录下的隔离区（跨卷复制，较慢但可用）。
    """
    ensure_app_dirs()
    default_root = os.path.join(APP_DIR, "Quarantine")
    roots = [quarantine_root_for(path)]
    if os.path.normcase(roots[0]) != os.path.normcase(default_root):
        roots.append(default_root)

    last_err = None
    for root in roots:
        try:
            os.makedirs(root, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            base = os.path.basename(path.rstrip("\\/"))
            dest = os.path.join(root, stamp + "_" + base)
            if os.path.exists(dest):
                dest = os.path.join(root, stamp + "_" + base + "_" + str(int(time.time() % 1000)))
            entry = {
                "original": _norm(path),
                "quarantined": _norm(dest),
                "reason": reason,
                "size": int(size or 0),
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "restored": False,
            }
            shutil.move(path, dest)
            _write_manifest(root, entry)
            return entry
        except OSError as e:
            last_err = e
            continue
    raise last_err if last_err else OSError("隔离失败")


def _manifest_path(root: str) -> str:
    return os.path.join(root, "manifest.json")


def _write_manifest(root: str, entry: dict):
    entries = load_manifest(root)
    entries.append(entry)
    with open(_manifest_path(root), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def load_manifest(root: str):
    try:
        with open(_manifest_path(root), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def restore(entry: dict) -> bool:
    """回滚单个隔离条目。"""
    src = entry.get("quarantined")
    dst = entry.get("original")
    if not src or not dst or not os.path.exists(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        return False
    shutil.move(src, dst)
    entry["restored"] = True
    return True


def delete_quarantined(entry: dict) -> bool:
    """彻底删除隔离区里的条目（释放磁盘空间）。"""
    src = entry.get("quarantined")
    if not src or not os.path.exists(src):
        return True
    if os.path.isdir(src) and not os.path.islink(src):
        def _onerr(func, p, exc):
            try:
                os.chmod(p, 0o666)
                func(p)
            except OSError:
                pass
        shutil.rmtree(src, onerror=_onerr)
    else:
        try:
            os.chmod(src, 0o666)
            os.remove(src)
        except OSError:
            return False
    return not os.path.exists(src)


def quarantine_roots():
    """所有隔离区根目录（C 盘 LOCALAPPDATA 下 + 其它盘的 PCClean\\Quarantine）。"""
    roots = [os.path.join(APP_DIR, "Quarantine")]
    for d in glob.glob("?:\\PCClean\\Quarantine"):
        if d.lower() not in [r.lower() for r in roots]:
            roots.append(d)
    return [r for r in roots if os.path.isdir(r)]


def quarantine_entries(root=None):
    """列出所有未恢复的隔离条目。"""
    roots = [root] if root else quarantine_roots()
    entries = []
    for r in roots:
        for e in load_manifest(r):
            if not e.get("restored"):
                e["_root"] = r
                entries.append(e)
    entries.sort(key=lambda x: x.get("time", ""), reverse=True)
    return entries


def purge_all_quarantine():
    """清空所有隔离条目（真正释放空间），返回 (成功数, 失败数)。"""
    ok = bad = 0
    for r in quarantine_roots():
        entries = load_manifest(r)
        changed = False
        for e in entries:
            if e.get("restored"):
                continue
            if delete_quarantined(e):
                e["restored"] = True
                ok += 1
            else:
                bad += 1
            changed = True
        if changed:
            try:
                with open(_manifest_path(r), "w", encoding="utf-8") as f:
                    json.dump(entries, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
    return ok, bad


# ---- 重复文件识别 ----
def _file_sig(path: str, sample=64 * 1024):
    """返回 (size, head_hash, full_hash)。"""
    size = os.path.getsize(path)
    try:
        with open(path, "rb") as f:
            head = hashlib.md5(f.read(sample)).hexdigest()
    except OSError:
        return size, "", ""
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        full = h.hexdigest()
    except OSError:
        return size, head, ""
    return size, head, full


def find_duplicates(paths, progress_cb=None, cancel_cb=None):
    """按 大小→头部哈希→全量哈希 分层找重复，返回 [[路径...], ...] 每组是重复文件。"""
    by_size = {}
    for p in paths:
        if cancel_cb and cancel_cb():
            return []
        try:
            if not os.path.isfile(p):
                continue
            sz = os.path.getsize(p)
            by_size.setdefault(sz, []).append(p)
        except OSError:
            continue
    groups = []
    for sz, files in by_size.items():
        if len(files) < 2:
            continue
        by_head = {}
        for p in files:
            _, head, _ = _file_sig(p, 16 * 1024)
            by_head.setdefault(head, []).append(p)
        for head, fs in by_head.items():
            if len(fs) < 2:
                continue
            by_full = {}
            for p in fs:
                _, _, full = _file_sig(p)
                by_full.setdefault(full, []).append(p)
            for full, dups in by_full.items():
                if len(dups) >= 2:
                    groups.append(dups)
        if progress_cb:
            progress_cb()
    return groups


def history_append(record: dict):
    ensure_app_dirs()
    fn = os.path.join(HISTORY_DIR, time.strftime("%Y%m%d") + ".jsonl")
    with open(fn, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def last_record():
    """读取最近一次清理/操作记录（用于界面显示「上次清理」）。"""
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.jsonl")))
    if not files:
        return None
    try:
        with open(files[-1], "r", encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (OSError, json.JSONDecodeError):
        return None
