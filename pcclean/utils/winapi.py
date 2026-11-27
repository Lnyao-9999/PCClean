# -*- coding: utf-8 -*-
"""ctypes 封装的 Windows 系统 API（无第三方依赖，含正确原型）。

所有控制台子进程一律使用 CREATE_NO_WINDOW 启动，避免弹黑框。
进程检测使用 Toolhelp32 快照（CTypes），完全不依赖 tasklist，零窗口、零卡顿。
"""
import ctypes
import os
import subprocess
import sys
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

GENERIC_WRITE = 0x40000000
DELETE = 0x00010000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_SHARING_VIOLATION = 32
ERROR_ACCESS_DENIED = 5
ERROR_LOCK_VIOLATION = 33

PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_INFORMATION = 0x0400

# 子进程隐藏窗口：控制台程序不会弹出黑框
CREATE_NO_WINDOW = 0x08000000
TH32CS_SNAPPROCESS = 0x00000002

# ---- 原型 ----
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.SetProcessWorkingSetSize.restype = wintypes.BOOL
kernel32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel32.GetFileAttributesW.restype = wintypes.DWORD
kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
kernel32.GetDiskFreeSpaceExW.restype = wintypes.BOOL
kernel32.GetDiskFreeSpaceExW.argtypes = [wintypes.LPCWSTR,
                                         ctypes.POINTER(ctypes.c_ulonglong),
                                         ctypes.POINTER(ctypes.c_ulonglong),
                                         ctypes.POINTER(ctypes.c_ulonglong)]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def enable_dpi_awareness() -> bool:
    """声明 DPI 感知（必须在创建任何窗口之前调用）。

    否则在 125%/150%/200% 缩放下，Windows 会把 96DPI 的界面整体位图拉伸，
    导致文字发虚。这里优先用「每显示器感知 v2」，逐级回退。
    """
    # PER_MONITOR_AWARE_V2 = -4
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return True
    except Exception:  # noqa: BLE001
        return False


def get_system_dpi() -> int:
    """获取系统 DPI（96 = 100%，144 = 150%，192 = 200%）。"""
    try:
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
        if dpi > 0:
            return dpi
    except Exception:  # noqa: BLE001
        pass
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = int(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi if dpi > 0 else 96
    except Exception:  # noqa: BLE001
        return 96


def elevate() -> bool:
    """以管理员权限重启自身（UAC 弹窗）。成功返回 True（本进程随后应退出）。"""
    if is_admin():
        return True
    script = os.path.abspath(sys.argv[0])
    params = subprocess.list2cmdline(sys.argv[1:])
    args = f'"{script}" {params}'
    ret = shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
    return int(ret) > 32


def is_reparse_point(path: str) -> bool:
    attrs = kernel32.GetFileAttributesW(os.fspath(path))
    if attrs == 0xFFFFFFFF:
        return False
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def is_cloud_placeholder(path: str) -> bool:
    """OneDrive/Dropbox 云端占位文件：删本地=删云端，必须禁止。"""
    attrs = kernel32.GetFileAttributesW(os.fspath(path))
    if attrs == 0xFFFFFFFF:
        return False
    return bool(attrs & FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)


def is_locked(path: str):
    """判断文件是否被其它进程占用。返回 (locked, errno)。"""
    h = kernel32.CreateFileW(
        ctypes.c_wchar_p(os.fspath(path)), GENERIC_WRITE, 0,
        None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE:
        return True, ctypes.get_last_error()
    kernel32.CloseHandle(h)
    return False, 0


def get_free_space(path: str):
    """返回 (free_bytes, total_bytes, avail_bytes)。"""
    free = ctypes.c_ulonglong(0)
    total = ctypes.c_ulonglong(0)
    avail = ctypes.c_ulonglong(0)
    ok = kernel32.GetDiskFreeSpaceExW(
        ctypes.c_wchar_p(os.fspath(path)),
        ctypes.byref(avail), ctypes.byref(total), ctypes.byref(free))
    if not ok:
        return None
    return free.value, total.value, avail.value


def long_path(path: str) -> str:
    ap = os.path.abspath(path)
    if ap.startswith("\\\\"):
        return ap
    return "\\\\?\\" + ap


def list_process_names():
    """用 Toolhelp32 快照列出所有进程名（小写）。零窗口、无需额外进程。"""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return []
    names = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            while True:
                names.append(entry.szExeFile.lower())
                entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return names


def running_processes(names):
    """返回 names 中正在运行的进程名列表（大小写不敏感）。"""
    if isinstance(names, str):
        names = [names]
    targets = {str(n).lower() for n in names if n}
    if not targets:
        return []
    live = set(list_process_names())
    return sorted(targets & live)


def is_process_running(names):
    """返回第一个命中的运行中进程名，或 None。"""
    hits = running_processes(names)
    return hits[0] if hits else None


def kill_processes(names, timeout=20):
    """强制结束指定进程（隐藏窗口）。返回实际结束了进程名列表。"""
    if isinstance(names, str):
        names = [names]
    targets = [n for n in names if n]
    live = set(list_process_names())
    killed = []
    for n in targets:
        if n.lower() not in live:
            continue
        try:
            run_hidden(["taskkill", "/F", "/T", "/IM", n], timeout=timeout)
            killed.append(n)
        except Exception:  # noqa: BLE001
            continue
    return killed


def create_junction(link: str, target: str):
    """创建目录联接（mklink /J），隐藏窗口。返回 (ok, message)。"""
    link = os.path.abspath(link)
    target = os.path.abspath(target)
    if os.path.exists(link):
        return False, f"目标位置已存在：{link}"
    if not os.path.isdir(target):
        return False, f"源目录不存在：{target}"
    r = run_hidden(["cmd", "/c", "mklink", "/J", link, target], timeout=60)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def resolve_reparse(path: str):
    """解析 junction / symlink 的真实目标路径；非 reparse 返回原路径。"""
    if not is_reparse_point(path):
        return path
    try:
        target = os.readlink(path)
        if target.startswith("\\\\?\\"):
            target = target[4:]
        return target
    except (OSError, ValueError):
        return path


def empty_working_set(pid: int) -> bool:
    """整理单个进程的工作集（把可回收页移出工作集）。"""
    h = kernel32.OpenProcess(
        PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, int(pid))
    if not h:
        return False
    try:
        return bool(kernel32.SetProcessWorkingSetSize(
            h, ctypes.c_size_t(-1), ctypes.c_size_t(-1)))
    finally:
        kernel32.CloseHandle(h)


def run_hidden(cmd, timeout=120, cwd=None, capture=True):
    """启动控制台子进程但不弹窗（CREATE_NO_WINDOW）。返回 CompletedProcess。"""
    return subprocess.run(
        cmd, capture_output=capture, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, cwd=cwd,
        creationflags=CREATE_NO_WINDOW)


def run_powershell(script: str, timeout: int = 120):
    """用 Windows PowerShell 5.1 执行脚本（隐藏窗口），返回 (ok, stdout, stderr)。"""
    try:
        r = run_hidden(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            timeout=timeout)
        return r.returncode == 0, r.stdout, r.stderr
    except Exception as e:  # noqa: BLE001
        return False, "", str(e)
