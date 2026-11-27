# -*- coding: utf-8 -*-
"""执行器：把 ScanItem 落地为 隔离/删除/系统 API 清理。

返回逐条结构化结果，包含「跳过原因」和「解决办法」，供界面向用户解释。
所有子进程一律隐藏窗口，避免弹 cmd。
"""
import os
import shutil
import subprocess

from ..config import SYSTEMROOT, SYSTEMDRIVE, ensure_app_dirs
from ..utils import winapi
from . import safety


def _guard_check(item):
    """返回运行中的进程名，或 None（用 ctypes 快照，无窗口、无 tasklist）。"""
    if item.guard:
        return winapi.is_process_running(item.guard)
    return None


def _reason_for(msg):
    """把失败/跳过消息归类成「原因 + 解决办法」。"""
    m = msg or ""
    if "管理员" in m:
        return ("需要管理员权限",
                "双击 PCClean.exe 启动（会自动申请管理员）；或右键程序选“以管理员身份运行”后重试")
    if "仍在运行" in m:
        return ("相关程序正在运行",
                "完全退出该程序（含托盘图标）后重新清理；或重启电脑后再试")
    if "占用" in m or "未完全删除" in m:
        return ("文件被占用",
                "关闭占用该文件的程序，或重启电脑后再清理")
    if "符号链接" in m or "云端" in m:
        return ("系统保护 / 云端占位",
                "属于目录联接或 OneDrive 云端占位文件，删除会误伤其它盘或云端数据，按安全策略跳过（无需处理）")
    if "受保护" in m:
        return ("系统保护项",
                "系统关键内容，本工具不清理（无需处理）")
    return ("其它原因", "可重启后重试；若持续失败请查看日志（%LOCALAPPDATA%\\PCClean\\Logs）")


def perform(items, mode="quarantine", log_cb=None, ask_cb=None):
    """执行清理。mode: quarantine（隔离区） / delete（直接删除，释放空间）。

    返回 dict: {cleaned, skipped, freed, results:[{item,status,msg,reason,solution}]}
    """
    results = []
    cleaned = skipped = freed = 0
    ensure_app_dirs()

    def _log(m):
        if log_cb:
            log_cb(m)

    for it in items:
        status, msg, freed_n = "ok", "", 0
        if it.risk == "D":
            status, msg = "skip", "受保护，已跳过"
        else:
            running = _guard_check(it)
            if running:
                status, msg = "skip", f"相关程序仍在运行（{running}），请先退出"
            else:
                action = it.action
                try:
                    if action == "wu_clean":
                        ok, msg, freed_n = _wu_clean()
                    elif action == "recycle":
                        ok, msg, freed_n = _empty_recycle_bin()
                    elif action == "dism":
                        ok, msg, freed_n = _dism_component_cleanup()
                    elif action in ("quarantine", "delete", "reboot-delete"):
                        ok, msg, freed_n = _remove_path(it, mode)
                    else:
                        ok, msg, freed_n = False, "该类型需在界面上单独确认", 0
                    status = "ok" if ok else "skip"
                except Exception as e:  # noqa: BLE001
                    status, msg = "skip", f"出错：{e}"

        if status == "ok":
            cleaned += 1
            freed += freed_n
            _log(f"✓ {it.label}: {msg}")
        else:
            skipped += 1
            _log(f"✗ {it.label}: {msg}")

        reason, solution = (None, None) if status == "ok" else _reason_for(msg)
        results.append({"item": it, "status": status, "msg": msg,
                        "reason": reason, "solution": solution})

    return {"cleaned": cleaned, "skipped": skipped, "freed": freed, "results": results}


def _remove_path(item, mode):
    # 通配符合并项可能包含多个目标
    targets = item.targets if item.targets else [item.path]
    existing = [t for t in targets if os.path.exists(t)]
    if not existing:
        return True, "不存在（已清理）", item.size
    ok_n = fail_n = unsafe_n = 0
    for t in existing:
        if not safety.is_safe_to_touch(t):
            unsafe_n += 1
            continue
        if mode == "quarantine":
            try:
                safety.quarantine(t, item.evidence, 0)
                ok_n += 1
            except Exception:  # noqa: BLE001
                fail_n += 1
        elif _robust_delete(t):
            ok_n += 1
        else:
            fail_n += 1
    if fail_n == 0 and unsafe_n == 0:
        msg = "已彻底删除" if mode == "delete" else "已移入隔离区（C盘空间暂未释放）"
        return True, msg, item.size
    parts = ([f"成功 {ok_n}"] if ok_n else []) + ([f"被占用 {fail_n}"] if fail_n else []) + \
            ([f"安全跳过 {unsafe_n}"] if unsafe_n else [])
    return False, "部分未清理（" + "，".join(parts) + "）", 0


def _robust_delete(path):
    """删除文件或目录，遇到只读/占用时尽量重试。"""
    def _onerr(func, p, exc):
        try:
            os.chmod(p, 0o666)
            func(p)
        except OSError:
            pass
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, onerror=_onerr)
        else:
            os.chmod(path, 0o666)
            os.remove(path)
    except OSError:
        pass
    return not os.path.exists(path)


def clear_quarantine():
    """清空隔离区（真正释放空间）。返回 (成功, 失败)。"""
    return safety.purge_all_quarantine()


def _wu_clean():
    if not winapi.is_admin():
        return False, "需管理员权限", 0
    d = os.path.join(SYSTEMROOT, "SoftwareDistribution", "Download")
    for svc in ("wuauserv", "bits", "dosvc"):
        winapi.run_hidden(["net", "stop", svc], timeout=60)
    try:
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        return False, f"清理失败：{e}", 0
    finally:
        for svc in ("wuauserv", "bits"):
            winapi.run_hidden(["net", "start", svc], timeout=60)
    return True, "Windows 更新缓存已清理", 0


def _empty_recycle_bin():
    if not winapi.is_admin():
        return False, "需管理员权限", 0
    ok, out, err = winapi.run_powershell(
        "Clear-RecycleBin -Force -ErrorAction SilentlyContinue", 60)
    return ok, (out or err).strip() or "回收站已清空", 0


def _dism_component_cleanup():
    if not winapi.is_admin():
        return False, "需管理员权限", 0
    r = winapi.run_hidden(["dism", "/Online", "/Cleanup-Image", "/StartComponentCleanup"],
                          timeout=1800)
    ok = r.returncode == 0
    return ok, ("组件存储已清理" if ok else f"DISM 返回 {r.returncode}"), 0
