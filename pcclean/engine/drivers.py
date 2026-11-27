# -*- coding: utf-8 -*-
"""NVIDIA 旧驱动清理 + 安装缓存清理。

安全原则：只删除 DriverStore 中「未被当前设备使用」的 NVIDIA 显示类 OEM 包，
绝不碰当前驱动对应的 oemNN.inf，绝不使用 /force。
"""
import os
import re
import subprocess
import winreg
import xml.etree.ElementTree as ET

from ..config import LOCALAPPDATA, PROGRAMDATA, expand_env
from ..utils import winapi

DISPLAY_CLASS_GUID = "{4d36e968-e325-11ce-bfc1-08002be10318}"
CLASS_KEY = r"SYSTEM\CurrentControlSet\Control\Class" + "\\" + DISPLAY_CLASS_GUID


def _run(cmd, timeout=90):
    try:
        r = winapi.run_hidden(cmd, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:  # noqa: BLE001
        return -1, "", str(e)


def current_driver_version() -> str:
    """当前 NVIDIA 驱动版本（nvidia-smi 优先）。"""
    rc, out, _ = _run(["nvidia-smi", "--query-gpu=driver_version",
                       "--format=csv,noheader"], 30)
    if rc == 0 and out.strip():
        return out.strip().splitlines()[0].strip()
    v = _reg_driver_version()
    return v or "未检测到 NVIDIA 驱动"


def _reg_driver_version() -> str:
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLASS_KEY + r"\0000")
        v, _ = winreg.QueryValueEx(k, "DriverVersion")
        winreg.CloseKey(k)
        return str(v)
    except OSError:
        return ""


def current_inf_paths():
    """当前所有显示适配器子键的 InfPath（=当前在用 oemNN.inf），小写集合。"""
    protected = set()
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLASS_KEY)
        n = winreg.QueryInfoKey(k)[0]
        for i in range(n):
            sub = winreg.EnumKey(k, i)
            try:
                sk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLASS_KEY + "\\" + sub)
                v, _ = winreg.QueryValueEx(sk, "InfPath")
                winreg.CloseKey(sk)
                if v:
                    protected.add(str(v).lower())
            except OSError:
                continue
        winreg.CloseKey(k)
    except OSError:
        pass
    return protected


def _txt(node, name):
    c = node.find(name)
    return (c.text or "") if c is not None else ""


def enum_nvidia_packages():
    """枚举 DriverStore 中 NVIDIA 显示类 OEM 包。返回 dict 列表。"""
    rc, out, _ = _run(["pnputil", "/enum-drivers", "/format", "xml"], 90)
    packages = []
    if rc == 0 and out.strip():
        try:
            root = ET.fromstring(out)
            for d in root.findall("Driver"):
                info = {
                    "published": d.get("DriverName", ""),
                    "original": _txt(d, "OriginalName"),
                    "provider": _txt(d, "ProviderName"),
                    "class": _txt(d, "ClassName"),
                    "guid": _txt(d, "ClassGuid"),
                    "version": _txt(d, "DriverVersion"),
                }
                if ("nvidia" in info["provider"].lower()
                        and info["guid"].lower() == DISPLAY_CLASS_GUID.lower()):
                    packages.append(info)
            return packages
        except ET.ParseError:
            pass
    # 文本解析兜底
    return _parse_text(out)


def _parse_text(out):
    packages = []
    cur = {}
    for line in out.splitlines():
        line = line.rstrip()
        low = line.lower()
        if low.startswith("published name:"):
            if cur:
                _add_pkg(packages, cur)
            cur = {"published": line.split(":", 1)[1].strip()}
        elif low.startswith("original name:"):
            cur["original"] = line.split(":", 1)[1].strip()
        elif low.startswith("provider name:"):
            cur["provider"] = line.split(":", 1)[1].strip()
        elif low.startswith("class name:"):
            cur["class"] = line.split(":", 1)[1].strip()
        elif low.startswith("class guid:"):
            cur["guid"] = line.split(":", 1)[1].strip()
        elif low.startswith("driver version:"):
            cur["version"] = line.split(":", 1)[1].strip()
    if cur:
        _add_pkg(packages, cur)
    return packages


def _add_pkg(packages, cur):
    if ("nvidia" in cur.get("provider", "").lower()
            and cur.get("guid", "").lower() == DISPLAY_CLASS_GUID.lower()):
        packages.append(cur)


def old_packages():
    """可安全删除的旧 NVIDIA 包（当前在用之外）。"""
    protected = current_inf_paths()
    return [p for p in enum_nvidia_packages()
            if p["published"].lower() not in protected]


def delete_package(published: str):
    """删除一个未被使用的 OEM 驱动包（不带 /force）。"""
    rc, out, err = _run(["pnputil", "/delete-driver", published], 120)
    return rc == 0, (out + err).strip()


def create_restore_point(name: str = "清理NVIDIA旧驱动前"):
    ok, out, err = winapi.run_powershell(
        f'Checkpoint-Computer -Description "{name}" -RestorePointType MODIFY_SETTINGS')
    return ok, (out or err).strip()


def nvidia_cache_targets():
    """NVIDIA 安装/下载缓存（可安全删）。返回候选 dict（交给 scanner 收集）。"""
    return [
        {"path": r"C:\NVIDIA", "kind": "dir", "category": "NVIDIA 安装缓存",
         "label": "NVIDIA 安装包解压缓存", "risk": "A", "action": "quarantine",
         "needs_admin": True,
         "evidence": "安装器解压缓存，每个版本约 0.6~1GB，删除后仍可重新下载"},
        {"path": r"C:\ProgramData\NVIDIA Corporation\Downloader", "kind": "dir",
         "category": "NVIDIA 安装缓存", "label": "NVIDIA 下载缓存", "risk": "A",
         "action": "quarantine", "needs_admin": True,
         "evidence": "GeForce 下载缓存"},
        {"path": r"C:\ProgramData\NVIDIA Corporation\NetService", "kind": "dir",
         "category": "NVIDIA 安装缓存", "label": "NVIDIA 网络服务缓存", "risk": "A",
         "action": "quarantine", "needs_admin": True,
         "evidence": "安装器副本缓存，可安全删除"},
        {"path": r"%LOCALAPPDATA%\NVIDIA Corporation", "kind": "dir",
         "category": "NVIDIA 安装缓存", "label": "NVIDIA 本地缓存", "risk": "A",
         "action": "quarantine",
         "evidence": "本地缓存/日志，删除后自动重建"},
        {"path": r"%LOCALAPPDATA%\Temp\NVIDIA*", "kind": "dir",
         "category": "NVIDIA 安装缓存", "label": "NVIDIA 临时文件", "risk": "A",
         "action": "quarantine",
         "evidence": "安装过程临时文件"},
    ]
