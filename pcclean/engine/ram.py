# -*- coding: utf-8 -*-
"""运行内存优化（诚实版）。

要点（调研结论）：
  - EmptyWorkingSet 只是把页移出工作集（进 Standby），不真释放物理 RAM，
    但能让后台程序"让位"，副作用是切回时可能软缺页卡一下；
  - 清 Standby 列表默认是安慰剂，仅作高级/激进选项；
  - 内存压缩默认已开，保持；页面文件保持系统托管，绝不提供"关闭"。
"""
import ctypes
import subprocess
from ctypes import wintypes

from ..utils import winapi

# 不 trim 的关键进程（小写）
EXCLUDE_PROCESSES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
    "dwm.exe", "explorer.exe", "audiodg.exe", "fontdrvhost.exe",
    "memcompression", "conhost.exe", "msmpeng.exe", "ntoskrnl.exe",
    "python.exe", "pythonw.exe", "ctfmon.exe", "textinputhost.exe",
    "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
    "gamebar.exe", "gamebarftr.exe",
}

# 内存状态
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def ram_info():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {"total": m.ullTotalPhys, "avail": m.ullAvailPhys, "load_pct": m.dwMemoryLoad}


def enum_processes():
    """返回 [{id, name}]。"""
    ok, out, _ = winapi.run_powershell(
        "Get-Process | Select-Object Id,ProcessName | ConvertTo-Json -Compress", 60)
    if not ok or not out.strip():
        return []
    import json
    try:
        data = json.loads(out.strip())
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    return [{"id": int(p.get("Id", 0)), "name": str(p.get("ProcessName", ""))}
            for p in data]


def trim_working_sets(exclude=None, progress_cb=None, cancel_cb=None):
    """整理后台进程工作集。返回 (done, failed, skipped)。"""
    exclude = {e.lower() for e in (EXCLUDE_PROCESSES | set(exclude or []))}
    procs = enum_processes()
    done = failed = skipped = 0
    for p in procs:
        if cancel_cb and cancel_cb():
            break
        name = p["name"].lower()
        if name in exclude:
            skipped += 1
            continue
        if winapi.empty_working_set(p["id"]):
            done += 1
        else:
            failed += 1
        if progress_cb:
            progress_cb()
    return done, failed, skipped


# ---- Standby 列表（高级，需管理员）----
def _set_memory_command(cmd: int) -> bool:
    if not winapi.is_admin():
        return False
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    fn = ntdll.NtSetSystemInformation
    fn.restype = ctypes.c_long
    fn.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    val = ctypes.c_int(cmd)
    status = fn(80, ctypes.byref(val), ctypes.sizeof(val))  # SystemMemoryListInformation
    return status == 0


def clear_standby(priority0_only=True):
    """清空备用内存（MemoryPurgeStandbyList=4 / 温和=5）。需管理员。"""
    cmd = 5 if priority0_only else 4
    return _set_memory_command(cmd)


# ---- 内存压缩状态（需管理员读）----
def memory_compression_enabled():
    ok, out, _ = winapi.run_powershell(
        "(Get-MMAgent).MemoryCompression", 60)
    if ok and out.strip():
        return out.strip().lower() == "true"
    return None


# ---- 游戏模式 ----
def enable_game_mode():
    ok1, _, _ = winapi.run_powershell(
        r'reg add "HKCU\Software\Microsoft\GameBar" /v AutoGameModeEnabled /t REG_DWORD /d 1 /f', 30)
    ok2, _, _ = winapi.run_powershell(
        r'reg add "HKCU\Software\Microsoft\GameBar" /v AllowAutoGameMode /t REG_DWORD /d 1 /f', 30)
    return ok1 and ok2


# ---- 其它安全动作 ----
def flush_dns():
    r = winapi.run_hidden(["ipconfig", "/flushdns"], timeout=30)
    return r.returncode == 0, (r.stdout + r.stderr).strip()
