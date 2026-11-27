# -*- coding: utf-8 -*-
"""winreg 封装：枚举已安装软件、读写键、备份。"""
import os
import subprocess
import winreg

UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

# 视图标志
KEY_WOW64_64KEY = winreg.KEY_WOW64_64KEY
KEY_WOW64_32KEY = winreg.KEY_WOW64_32KEY


def _read_values(key) -> dict:
    d = {}
    try:
        n_sub, n_val, _ = winreg.QueryInfoKey(key)
    except OSError:
        return d
    for i in range(n_val):
        try:
            name, value, _ = winreg.EnumValue(key, i)
            d[name] = value
        except OSError:
            continue
    return d


def enum_uninstall():
    """枚举所有已安装的 Win32 软件（含 64/32 位、HKLM/HKCU）。返回 dict 列表。"""
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, 0),
        (winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, KEY_WOW64_32KEY),
        (winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0),
        (winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, KEY_WOW64_32KEY),
    ]
    items = []
    seen = set()
    for root, sub, view in roots:
        try:
            base = winreg.OpenKey(root, sub, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        try:
            n_sub = winreg.QueryInfoKey(base)[0]
        except OSError:
            winreg.CloseKey(base)
            continue
        for i in range(n_sub):
            try:
                name = winreg.EnumKey(base, i)
            except OSError:
                continue
            path = sub + "\\" + name
            try:
                k = winreg.OpenKey(root, path, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            d = _read_values(k)
            winreg.CloseKey(k)
            display = d.get("DisplayName")
            if not display or not str(display).strip():
                continue
            # 过滤系统组件 / 补丁
            if d.get("SystemComponent") == 1:
                continue
            if d.get("ParentKeyName"):
                continue
            rel = str(d.get("ReleaseType", "")).lower()
            if rel in ("hotfix", "security update", "update rollup", "update"):
                continue
            sig = (display, d.get("DisplayVersion"))
            if sig in seen:
                continue
            seen.add(sig)
            hive = "HKLM" if root == winreg.HKEY_LOCAL_MACHINE else "HKCU"
            view_name = "64" if view == 0 else "32"
            items.append({
                "name": str(display).strip(),
                "version": str(d.get("DisplayVersion", "")).strip(),
                "publisher": str(d.get("Publisher", "")).strip(),
                "install_location": str(d.get("InstallLocation", "")).strip(),
                "uninstall_string": str(d.get("UninstallString", "")).strip(),
                "quiet_uninstall": str(d.get("QuietUninstallString", "")).strip(),
                "size_kb": _to_int(d.get("EstimatedSize")),
                "install_date": str(d.get("InstallDate", "")).strip(),
                "key_path": path,
                "hive": hive,
                "view": view_name,
                "kind": "win32",
            })
        winreg.CloseKey(base)
    items.sort(key=lambda x: x["name"].lower())
    return items


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def enum_appx():
    """枚举 UWP/Store 应用（Get-AppxPackage）。返回 dict 列表。"""
    from .winapi import run_powershell
    ps = (
        "Get-AppxPackage | Where-Object { $_.IsFramework -eq $false -and "
        "$_.SignatureKind -ne 'System' } | Select-Object Name, PackageFullName, "
        "Version, InstallLocation, PackageFamilyName | "
        "ConvertTo-Json -Compress"
    )
    ok, out, _ = run_powershell(ps)
    if not ok or not out.strip():
        return []
    import json
    try:
        data = json.loads(out.strip())
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    items = []
    for a in data:
        items.append({
            "name": a.get("Name", ""),
            "package_full_name": a.get("PackageFullName", ""),
            "version": str(a.get("Version", "")),
            "install_location": a.get("InstallLocation", ""),
            "package_family_name": a.get("PackageFamilyName", ""),
            "kind": "appx",
            "publisher": "",
            "key_path": "",
        })
    items.sort(key=lambda x: x["name"].lower())
    return items


def backup_key(key_path: str, hive: str, out_file: str) -> bool:
    """用 reg export 备份一个键（隐藏窗口）。返回是否成功。"""
    from .winapi import run_hidden
    reg_root = "HKEY_LOCAL_MACHINE" if hive == "HKLM" else "HKEY_CURRENT_USER"
    full = reg_root + "\\" + key_path
    r = run_hidden(["reg", "export", full, out_file, "/y"], timeout=60)
    return r.returncode == 0


def delete_key(key_path: str, hive: str) -> bool:
    root = winreg.HKEY_LOCAL_MACHINE if hive == "HKLM" else winreg.HKEY_CURRENT_USER
    try:
        winreg.DeleteKey(root, key_path)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        # 子键存在时 DeleteKey 失败，递归删除
        return _delete_tree(root, key_path)


def _delete_tree(root, path):
    try:
        k = winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except OSError:
        return False
    try:
        while True:
            try:
                sub = winreg.EnumKey(k, 0)
            except OSError:
                break
            if not _delete_tree(root, path + "\\" + sub):
                return False
    finally:
        winreg.CloseKey(k)
    try:
        winreg.DeleteKey(root, path)
        return True
    except OSError:
        return False
