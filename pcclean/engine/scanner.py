# -*- coding: utf-8 -*-
"""扫描原语：目录/文件体积统计、ScanItem、候选收集。"""
import glob
import os
from dataclasses import dataclass, field

from ..config import expand_env
from ..utils import winapi


@dataclass
class ScanItem:
    path: str
    kind: str            # dir / file / sys / app / driver / migrate
    category: str
    label: str
    size: int            # bytes
    files: int
    risk: str            # A 自动 / B 建议 / C 需确认 / D 禁止
    action: str          # quarantine / delete / dism / migrate / app / prompt / powercfg / reboot-delete
    evidence: str
    app: str = ""
    guard: list = field(default_factory=list)   # 运行中进程名（有则需先退出）
    needs_admin: bool = False
    real_path: str = ""  # 若为 junction，记录真实目标
    checked: bool = True
    targets: list = field(default_factory=list)  # 通配符合并后的多个目标路径
    guard_running: bool = False                  # 相关程序当前是否在运行

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)

    def human_size(self) -> str:
        b = self.size
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if b < 1024 or unit == "TB":
                return f"{b:.1f} {unit}" if unit != "B" else f"{int(b)} B"
            b /= 1024
        return f"{self.size} B"


FILE_ATTR_REPARSE = 0x400


def _is_reparse(entry) -> bool:
    try:
        st = entry.stat(follow_symlinks=False)
        return bool(st.st_file_attributes & FILE_ATTR_REPARSE)
    except OSError:
        return False


def dir_size(path: str, progress_cb=None):
    """统计目录体积与文件数；不跟随 junction/符号链接（返回时单独处理）。"""
    total = 0
    files = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        if _is_reparse(e):
                            continue  # 不跟随 junction/symlink
                        stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        total += e.stat(follow_symlinks=False).st_size
                        files += 1
                except OSError:
                    continue
        if progress_cb:
            progress_cb(cur)
    return total, files


def measure(path: str):
    """统一测体积：目录→递归；文件→单个；junction→解析目标后测。"""
    if winapi.is_reparse_point(path):
        real = winapi.resolve_reparse(path)
        if real and real != path and os.path.isdir(real):
            size, files = dir_size(real)
            return size, files, real
    if os.path.isdir(path):
        size, files = dir_size(path)
        return size, files, ""
    if os.path.isfile(path):
        try:
            return os.path.getsize(path), 1, ""
        except OSError:
            return 0, 0, ""
    return 0, 0, ""


def expand_glob(pattern: str):
    """展开含环境变量的 glob，返回匹配的绝对路径列表。"""
    pat = expand_env(pattern)
    if any(ch in pat for ch in "*?["):
        return [os.path.abspath(x) for x in glob.glob(pat)]
    if os.path.exists(pat):
        return [os.path.abspath(pat)]
    return []


def collect(candidates, progress_cb=None, cancel_cb=None, include_tiny=False):
    """把候选 dict 列表转成 ScanItem 列表。

    - 通配符匹配到多个目标时合并为一个条目（显示总大小与项数），避免几十行刷屏；
    - 默认隐藏小于 0.1MB 的极小项目（include_tiny=True 可显示）。
    """
    from .safety import is_protected
    min_size = 0 if include_tiny else 100 * 1024
    items = []
    for c in candidates:
        if cancel_cb and cancel_cb():
            break
        pattern = c["path"]
        matches = expand_glob(pattern)
        has_wild = any(ch in pattern for ch in "*?[")
        if has_wild and len(matches) > 1:
            total = files = 0
            targets = []
            for m in matches:
                if is_protected(m):
                    continue
                size, cnt, _ = measure(m)
                if size <= 0:
                    continue
                total += size
                files += cnt
                targets.append(m)
            if targets and total >= min_size:
                label = c.get("label", "")
                if len(targets) > 1:
                    label = f"{label}（{len(targets)} 项）"
                items.append(ScanItem(
                    path=targets[0],
                    kind=c.get("kind", "dir"),
                    category=c.get("category", "其它"),
                    label=label,
                    size=total,
                    files=files,
                    risk=c.get("risk", "B"),
                    action=c.get("action", "quarantine"),
                    evidence=c.get("evidence", ""),
                    app=c.get("app", ""),
                    guard=c.get("guard", []),
                    needs_admin=c.get("needs_admin", False),
                    targets=targets,
                ))
        else:
            for m in matches:
                if is_protected(m):
                    continue
                size, files, real = measure(m)
                if size <= 0 or size < min_size:
                    continue
                items.append(ScanItem(
                    path=m,
                    real_path=real,
                    kind=c.get("kind", "dir"),
                    category=c.get("category", "其它"),
                    label=c.get("label", os.path.basename(m)),
                    size=size,
                    files=files,
                    risk=c.get("risk", "B"),
                    action=c.get("action", "quarantine"),
                    evidence=c.get("evidence", ""),
                    app=c.get("app", ""),
                    guard=c.get("guard", []),
                    needs_admin=c.get("needs_admin", False),
                ))
        if progress_cb:
            progress_cb(pattern)
    items.sort(key=lambda x: x.size, reverse=True)
    return items
