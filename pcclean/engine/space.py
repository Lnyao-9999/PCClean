# -*- coding: utf-8 -*-
"""空间分析：盘符枚举、大文件查找、重复文件查找。

用于补齐「所有盘符」的清理能力：C 盘之外的盘也能分析大文件/重复文件，
帮助用户判断哪些内容可以迁移或删除。
"""
import ctypes
import os
from ctypes import wintypes

from ..utils import winapi
from . import safety

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetLogicalDriveStringsW.restype = wintypes.DWORD
kernel32.GetLogicalDriveStringsW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
kernel32.GetDriveTypeW.restype = wintypes.UINT
kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]

DRIVE_FIXED = 3
FILE_ATTR_REPARSE = 0x400

# 这些目录文件极多且无清理意义，遍历时跳过以提速
SKIP_DIR_NAMES = {"winsxs", "servicing", "assembly", "$recycle.bin", "driverstore",
                  "system volume information", "config.msi", "windows.old",
                  "recovery", "boot"}


def list_drives():
    """列出本机固定磁盘。返回 [{letter, total, free}]。"""
    buf = ctypes.create_unicode_buffer(1024)
    n = kernel32.GetLogicalDriveStringsW(1024, buf)
    raw = buf[:n] if n else ""
    out = []
    for d in raw.split("\x00"):
        d = d.strip()
        if not d:
            continue
        try:
            if kernel32.GetDriveTypeW(d) != DRIVE_FIXED:
                continue
        except Exception:  # noqa: BLE001
            continue
        sp = winapi.get_free_space(d)
        total = sp[1] if sp else 0
        free = sp[0] if sp else 0
        out.append({"letter": d.rstrip("\\"), "total": total, "free": free})
    out.sort(key=lambda x: x["letter"])
    return out


def walk_files(root, min_size, progress_cb=None, cancel_cb=None,
               max_files=0, skip_names=None):
    """遍历目录，产出 >= min_size 的 (path, size)。不跟随 junction。"""
    skip = {n.lower() for n in (skip_names or SKIP_DIR_NAMES)}
    found = 0
    dirs_done = 0
    stack = [root]
    while stack:
        if cancel_cb and cancel_cb():
            return
        cur = stack.pop()
        dirs_done += 1
        if progress_cb and (dirs_done % 200 == 0):
            progress_cb(dirs_done)
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        with it:
            for e in it:
                if cancel_cb and cancel_cb():
                    return
                try:
                    st = e.stat(follow_symlinks=False)
                    if st.st_file_attributes & FILE_ATTR_REPARSE:
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if e.name.lower() in skip:
                            continue
                        stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        if st.st_size >= min_size:
                            yield e.path, st.st_size
                            found += 1
                            if max_files and found >= max_files:
                                return
                except OSError:
                    continue


def find_large_files(root, min_size=200 * 1024 * 1024, limit=300,
                     progress_cb=None, cancel_cb=None):
    """查找大文件。返回 [(path, size)]，按大小降序。"""
    items = list(walk_files(root, min_size, progress_cb=progress_cb, cancel_cb=cancel_cb))
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:limit]


def find_duplicates(root, min_size=10 * 1024 * 1024, max_candidates=3000,
                    progress_cb=None, cancel_cb=None):
    """查找重复文件（大文件优先）。返回 [{size, files:[...]}]，按体积降序。

    策略：先按体积分组（只有同体积才可能重复）→ 头部哈希 → 全量哈希，
    避免对全盘做全量哈希，速度可接受。
    """
    by_size = {}
    for path, size in walk_files(root, min_size, progress_cb=progress_cb,
                                 cancel_cb=cancel_cb, max_files=max_candidates):
        by_size.setdefault(size, []).append(path)
        if cancel_cb and cancel_cb():
            return []

    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_head = {}
        for p in paths:
            if cancel_cb and cancel_cb():
                return groups
            _, head, _ = safety._file_sig(p, 64 * 1024)
            if not head:
                continue
            by_head.setdefault(head, []).append(p)
        for _head, ps in by_head.items():
            if len(ps) < 2:
                continue
            by_full = {}
            for p in ps:
                if cancel_cb and cancel_cb():
                    return groups
                _, _, full = safety._file_sig(p)
                if not full:
                    continue
                by_full.setdefault(full, []).append(p)
            for _f, fs in by_full.items():
                if len(fs) >= 2:
                    groups.append({"size": size, "files": fs})
    groups.sort(key=lambda g: g["size"], reverse=True)
    return groups
