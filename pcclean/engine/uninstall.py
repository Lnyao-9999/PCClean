# -*- coding: utf-8 -*-
"""软件卸载 + 残留清理（参照 Geek Uninstaller 的 A→B 两阶段）。

阶段 A：读注册表 → 调卸载程序 → 等待 → 验证注册表键是否消失
阶段 B：以 DisplayName/Publisher/InstallLocation 为锚点，扫描文件与注册表残留，
        弹清单让用户确认后清理（文件进隔离区、注册表先备份 .reg）
"""
import os
import re
import shlex
import subprocess
import time
import winreg

from ..config import (LOCALAPPDATA, APPDATA, PROGRAMDATA, USERPROFILE,
                      SYSTEMROOT, HISTORY_DIR, ensure_app_dirs)
from ..utils import registry, winapi

GUID_RE = re.compile(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}")

# 卸载中 MSI 退出码
MSI_OK = {0, 3010, 1605}


def list_apps():
    """枚举所有已装软件（Win32 + UWP）。"""
    apps = registry.enum_uninstall()
    try:
        apps += registry.enum_appx()
    except Exception:  # noqa: BLE001
        pass
    return apps


# ---------- 阶段 A：卸载 ----------
def _parse(s):
    try:
        parts = shlex.split(s, posix=False)
    except ValueError:
        parts = s.split()
    if not parts:
        return "", []
    return parts[0].strip('"'), parts[1:]


def _msiexec(u, silent):
    m = GUID_RE.search(u)
    if not m:
        return None
    guid = m.group(0)
    if silent:
        return ["msiexec.exe", "/x", guid, "/qn", "/norestart"]
    return ["msiexec.exe", "/x", guid]


def uninstall_appx(app):
    name = app.get("name", "")
    if not name:
        return False, "缺少包名", False
    ok, out, err = winapi.run_powershell(
        f'Get-AppxPackage -Name "{name}" | Remove-AppxPackage')
    return ok, (out or err).strip() or "已卸载", False


def run_uninstaller(app, silent=False, log_cb=None):
    """运行卸载程序。返回 (ok, message, need_reboot)。"""
    def _log(m):
        if log_cb:
            log_cb(m)
    if app.get("kind") == "appx":
        _log(f"卸载 UWP 应用：{app.get('name')}")
        return uninstall_appx(app)

    u = (app.get("uninstall_string") or "").strip()
    if not u:
        u = (app.get("quiet_uninstall") or "").strip()
    if not u:
        return False, "未找到卸载命令（可能是绿色软件或卸载器已损坏，可用「强制移除」）", False

    exe, args = _parse(u)
    if "msiexec" in exe.lower():
        m = _msiexec(u, silent)
        if m:
            exe, args = m[0], m[1:]
    _log(f"运行卸载：{exe} {' '.join(args)}")
    try:
        proc = subprocess.Popen([exe] + args, close_fds=True)
    except OSError as e:
        return False, f"无法启动卸载程序（可能需要管理员权限）：{e}", False
    try:
        rc = proc.wait(timeout=1200)
    except subprocess.TimeoutExpired:
        return False, "卸载超时（卸载程序可能仍在运行）", False
    need_reboot = rc == 3010
    if rc in MSI_OK:
        return True, ("卸载完成（建议重启）" if need_reboot else "卸载完成"), need_reboot
    if rc == 1602:
        return False, "用户取消了卸载", False
    return False, f"卸载程序退出码 {rc}（可能未完全卸载）", False


# ---------- 阶段 B：残留扫描 ----------
def _tokens(s):
    s = re.sub(r"\b(v?\d+(\.\d+)+[\w.\-]*)\b", " ", s.lower())
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return {t for t in s.split() if len(t) >= 2}


def _name_hits(name, tokens):
    """目录名归一化后是否命中应用 token。"""
    nt = _tokens(name)
    if not nt:
        return False
    # 任意 token 完全命中，或目录名包含主 token
    if nt & tokens:
        return True
    joined = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", name.lower())
    for t in tokens:
        if len(t) >= 3 and t in joined:
            return True
    return False


def scan_leftovers(app):
    """扫描一个应用的残留文件与注册表。返回 {'files': [...], 'registry': [...]}。"""
    name = (app.get("name") or "").strip()
    vendor = (app.get("publisher") or "").strip()
    install_loc = (app.get("install_location") or "").strip()
    if not name:
        return {"files": [], "registry": []}

    tokens = _tokens(name) | _tokens(vendor)
    if install_loc:
        tokens.add(os.path.basename(install_loc.rstrip("\\/")).lower())
    # 主 token：DisplayName 里最长者
    primary = max(tokens, key=len) if tokens else name.lower()

    file_roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        LOCALAPPDATA,
        os.path.join(LOCALAPPDATA, "Programs"),
        APPDATA,
        PROGRAMDATA,
        os.path.join(PROGRAMDATA, r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(APPDATA, r"Microsoft\Windows\Start Menu\Programs"),
    ]
    # 已安装软件的名称集合（反向校验，避免误删别的软件目录）
    try:
        installed_names = {a["name"].lower() for a in list_apps()}
    except Exception:  # noqa: BLE001
        installed_names = set()

    files = []
    seen = set()
    # 安装目录必列
    if install_loc and os.path.isdir(install_loc):
        files.append({"path": install_loc, "kind": "dir", "reason": "安装目录"})
        seen.add(os.path.normcase(install_loc))

    for root in file_roots:
        if not os.path.isdir(root):
            continue
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for e in entries:
            full = os.path.join(root, e)
            nk = os.path.normcase(full)
            if nk in seen:
                continue
            if not _name_hits(e, tokens):
                continue
            # 反向校验：目录名等于某仍安装软件的名 → 跳过
            en = e.lower()
            if en in installed_names:
                continue
            if os.path.isdir(full) and not os.path.islink(full):
                files.append({"path": full, "kind": "dir", "reason": "名称匹配残留目录"})
            elif os.path.isfile(full):
                files.append({"path": full, "kind": "file", "reason": "名称匹配残留文件"})
            seen.add(nk)

    # 桌面快捷方式
    for desk in [os.path.join(USERPROFILE, "Desktop"), os.path.join(os.environ.get("PUBLIC", ""), "Desktop")]:
        if not desk or not os.path.isdir(desk):
            continue
        try:
            for e in os.listdir(desk):
                if e.lower().endswith(".lnk") and _name_hits(e[:-4], tokens):
                    files.append({"path": os.path.join(desk, e), "kind": "file", "reason": "桌面快捷方式"})
        except OSError:
            continue

    # 注册表残留
    reg = []
    vendor_tokens = list(_tokens(vendor))
    for tok in (vendor_tokens or [primary]):
        for hive, label in [(winreg.HKEY_CURRENT_USER, "HKCU"),
                            (winreg.HKEY_LOCAL_MACHINE, "HKLM")]:
            base = "Software"
            for sub in (tok, tok + "\\" + primary if tok != primary else None):
                if not sub:
                    continue
                path = f"{base}\\{sub}"
                if _reg_key_exists(hive, path):
                    reg.append({"hive": label, "path": path, "reason": "厂商/应用配置键"})
    # App Paths
    exe_tok = primary.rstrip(".exe") + ".exe"
    for hive, label in [(winreg.HKEY_LOCAL_MACHINE, "HKLM")]:
        path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_tok}"
        if _reg_key_exists(hive, path):
            reg.append({"hive": label, "path": path, "reason": "应用路径键"})

    return {"files": files, "registry": reg}


def _reg_key_exists(hive, path):
    import winreg
    try:
        winreg.OpenKey(hive, path, 0, winreg.KEY_READ).Close()
        return True
    except OSError:
        return False


def clean_leftovers(files, reg_entries, log_cb=None):
    """清理残留：文件进隔离区，注册表先备份 .reg 再删。返回统计。"""
    from . import safety
    ensure_app_dirs()
    removed_files = 0
    for f in files:
        p = f["path"]
        if not os.path.exists(p):
            continue
        try:
            safety.quarantine(p, f"卸载残留：{f.get('reason','')}")
            removed_files += 1
            if log_cb:
                log_cb(f"已隔离文件：{p}")
        except Exception as e:  # noqa: BLE001
            if log_cb:
                log_cb(f"跳过 {p}：{e}")
    removed_reg = 0
    for r in reg_entries:
        hive = r["hive"]
        path = r["path"]
        reg_root = "HKEY_LOCAL_MACHINE" if hive == "HKLM" else "HKEY_CURRENT_USER"
        backup = os.path.join(HISTORY_DIR, time.strftime("%Y%m%d_%H%M%S") +
                              "_" + re.sub(r"[^0-9A-Za-z]", "_", path) + ".reg")
        try:
            registry.backup_key(path, hive, backup)
        except Exception:  # noqa: BLE001
            pass
        if registry.delete_key(path, hive):
            removed_reg += 1
            if log_cb:
                log_cb(f"已删除注册表键：{reg_root}\\{path}")
    return {"files": removed_files, "registry": removed_reg}


def force_remove(app, log_cb=None):
    """强制移除：备份并删除 Uninstall 键 + 清理残留（跳过调用卸载程序）。"""
    result = clean_leftovers(*_scan_tuple(app), log_cb=log_cb)
    kp = app.get("key_path")
    hive = app.get("hive")
    if kp and hive:
        reg_root = "HKEY_LOCAL_MACHINE" if hive == "HKLM" else "HKEY_CURRENT_USER"
        backup = os.path.join(HISTORY_DIR, time.strftime("%Y%m%d_%H%M%S") +
                              "_uninstall_" + re.sub(r"[^0-9A-Za-z]", "_", kp) + ".reg")
        try:
            registry.backup_key(kp, hive, backup)
        except Exception:  # noqa: BLE001
            pass
        registry.delete_key(kp, hive)
        if log_cb:
            log_cb(f"已删除卸载登记：{reg_root}\\{kp}")
    return result


def _scan_tuple(app):
    lr = scan_leftovers(app)
    return lr["files"], lr["registry"]
