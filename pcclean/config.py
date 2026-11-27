# -*- coding: utf-8 -*-
"""全局配置、常量、路径。"""
import os
import sys

APP_NAME = "全能磁盘清理专家"
VERSION = "1.3.0"

# ---- 应用自身数据目录（状态、历史、隔离区都在这里）----
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
APPDATA = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
USERPROFILE = os.environ.get("USERPROFILE", os.path.expanduser("~"))
PROGRAMDATA = os.environ.get("PROGRAMDATA", "C:\\ProgramData")
SYSTEMROOT = os.environ.get("SystemRoot", "C:\\Windows")
SYSTEMDRIVE = os.environ.get("SystemDrive", "C:")

APP_DIR = os.path.join(LOCALAPPDATA, "PCClean")
HISTORY_DIR = os.path.join(APP_DIR, "History")
LOG_DIR = os.path.join(APP_DIR, "Logs")


def ensure_app_dirs():
    for d in (APP_DIR, HISTORY_DIR, LOG_DIR):
        os.makedirs(d, exist_ok=True)
    return APP_DIR


# ---- 隔离区：与被清理文件同卷，保证 rename 秒级移动 ----
def quarantine_root_for(path: str) -> str:
    """返回 path 所在卷的隔离区根目录（C 盘用 LOCALAPPDATA 下，避免需要管理员）。"""
    abs_p = os.path.abspath(path)
    drive = os.path.splitdrive(abs_p)[0] or SYSTEMDRIVE
    if drive[:1].upper() == SYSTEMDRIVE[:1].upper():
        return os.path.join(APP_DIR, "Quarantine")
    return os.path.join(drive + os.sep, "PCClean", "Quarantine")


# ---- 绝不自动删除的保护名单（规范化后前缀匹配）----
NEVER_DELETE_PREFIXES = [
    os.path.join(SYSTEMROOT, "System32").lower(),
    os.path.join(SYSTEMROOT, "SysWOW64").lower(),
    os.path.join(SYSTEMROOT, "WinSxS").lower(),
    os.path.join(SYSTEMROOT, "Installer").lower(),
    os.path.join(SYSTEMROOT, "System Volume Information").lower(),
    os.path.join(SYSTEMROOT, "boot").lower(),
    os.path.join(SYSTEMROOT, "Boot").lower(),
    os.path.join(SYSTEMROOT, "Fonts").lower(),
    os.path.join(SYSTEMDRIVE, "EFI").lower(),
    os.path.join(SYSTEMROOT).lower() + "\\",      # C:\Windows 本身
    os.path.join("C:\\Program Files").lower(),
    os.path.join("C:\\Program Files (x86)").lower(),
    os.path.join(USERPROFILE, "Documents").lower(),
    os.path.join(USERPROFILE, "Desktop").lower(),
    os.path.join(USERPROFILE, "Pictures").lower(),
    os.path.join(USERPROFILE, "Videos").lower(),
    os.path.join(USERPROFILE, "Music").lower(),
    os.path.join(USERPROFILE, "Downloads").lower(),  # 只建议、绝不自动删
]

# 文件/目录名黑名单（无论路径，直接拒绝删除）
NEVER_DELETE_NAMES = {
    ".git", "node_modules", "hiberfil.sys", "pagefile.sys", "swapfile.sys",
    "ntuser.dat", "sam", "system", "software", "security", "default",
    "desktop.ini", "thumbs.db", "autorun.inf",
}

# 目录联接/符号链接：一律不跟随、不删除目标（只删链接本身需显式确认）
REPARSE_SKIP = True

# ---- 环境变量展开 ----
def expand_env(path: str) -> str:
    p = os.path.expandvars(path)
    p = p.replace("%USERPROFILE%", USERPROFILE)
    p = p.replace("%LOCALAPPDATA%", LOCALAPPDATA)
    p = p.replace("%APPDATA%", APPDATA)
    p = p.replace("%PROGRAMDATA%", PROGRAMDATA)
    p = p.replace("%SystemRoot%", SYSTEMROOT)
    p = p.replace("%SYSTEMROOT%", SYSTEMROOT)
    return p


def p(s: str) -> str:
    return expand_env(s)
