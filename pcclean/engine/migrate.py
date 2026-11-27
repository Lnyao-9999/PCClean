# -*- coding: utf-8 -*-
"""微信 / QQ / 剪映 数据迁移（询问式）+ 教用户改默认存储位置。

原则：
  1. 优先推荐「应用内改设置」（最安全）；
  2. 已有大量数据且应用内不搬旧数据时，用「robocopy 复制 → 改名留备份 → mklink /J → 验证」四步。
"""
import os
import subprocess

from ..config import expand_env, USERPROFILE, LOCALAPPDATA
from ..utils import winapi

# 每个迁移目标：src=默认数据目录（可含 %VAR%），guard=必须关闭的进程名
MIGRATE_SPECS = [
    {
        "app": "微信",
        "src": r"%USERPROFILE%\Documents\xwechat_files",
        "alt_src": r"%USERPROFILE%\Documents\WeChat Files",
        "guard": ["Weixin.exe", "WeChat.exe"],
        "guide": (
            "微信（新版 4.x）：左下角「≡」→ 设置 →「账号与存储」→ 点「更改聊天记录位置」，"
            "选 D 盘新文件夹 → 确认后重新扫码登录，微信会自动迁移。\n"
            "微信（旧版 3.x）：设置 →「文件管理」→ 点「更改」→ 选新文件夹，自动迁移。\n"
            "注意：若界面里找不到「更改聊天记录位置」，说明版本过旧，请先升级微信。"
        ),
    },
    {
        "app": "QQ",
        "src": r"%USERPROFILE%\Documents\Tencent Files",
        "guard": ["QQ.exe", "QQNT.exe", "QQScLauncher.exe"],
        "guide": (
            "QQ（新版 NT）：左下角「≡」→ 设置 →「存储管理」→「保存位置」→ 更改到 D 盘。\n"
            "QQ（旧版）：设置 →「文件管理」→「个人文件夹保存位置」→ 选「自定义」→ 选 D 盘目录。\n"
            "若菜单里没有「保存位置」，请改用本工具的「一键迁移」。"
        ),
    },
    {
        "app": "剪映",
        "src": r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft",
        "guard": ["JianyingPro.exe", "Jianying.exe"],
        "guide": (
            "剪映：右上角「设置」→「全局设置」→「草稿」标签 → 改「草稿位置」和「素材下载位置」到 D 盘；\n"
            "「性能」标签 → 改「缓存目录 / 文件渲染位置 / 代理位置」到 D 盘，并勾选「退出时清理缓存」。\n"
            "注意：剪映改「草稿位置」通常不会自动搬旧草稿，需先把旧草稿复制到新位置再指向它（本工具的「一键迁移」可代劳）。"
        ),
    },
]

GUIDES = {s["app"]: s["guide"] for s in MIGRATE_SPECS}


def detect():
    """检测各迁移目标是否存在及体积。返回列表。"""
    results = []
    for s in MIGRATE_SPECS:
        src = expand_env(s["src"])
        real = src
        if not os.path.isdir(src):
            alt = expand_env(s.get("alt_src", ""))
            if alt and os.path.isdir(alt):
                src = alt
        if not os.path.isdir(src):
            results.append({"app": s["app"], "src": src, "exists": False,
                            "size": 0, "guard": s["guard"]})
            continue
        from .scanner import dir_size
        size, _ = dir_size(src)
        results.append({"app": s["app"], "src": src, "exists": True,
                        "size": size, "guard": s["guard"]})
    return results


def is_running(guards):
    """检测某应用是否有残留进程（ctypes 快照，无窗口）。返回运行中的进程名列表。"""
    return winapi.running_processes(guards)


def do_migrate(src, dest, log_cb=None):
    """安全四步迁移。返回 (ok, message)。绝不删除源数据（改名保留为 *_backup）。"""
    src = os.path.abspath(src)
    dest = os.path.abspath(dest)
    if not os.path.isdir(src):
        return False, f"源目录不存在：{src}"
    if os.path.exists(dest):
        return False, f"目标已存在：{dest}"
    parent = os.path.dirname(src)
    backup = os.path.join(parent, os.path.basename(src) + "_backup")
    if os.path.exists(backup):
        return False, f"检测到上次的备份目录仍在：{backup}（请先处理）"

    def _log(m):
        if log_cb:
            log_cb(m)

    _log(f"① 复制 {src} → {dest}（可能需要几分钟）")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    r = winapi.run_hidden(
        ["robocopy", src, dest, "/E", "/COPY:DAT", "/R:1", "/W:1", "/MT:16",
         "/NFL", "/NDL", "/NP", "/NJH"],
        timeout=3600)
    if r.returncode >= 8:
        return False, f"复制失败（robocopy 退出码 {r.returncode}）：{(r.stdout + r.stderr)[-500:]}"

    _log("② 原目录改名为备份")
    os.rename(src, backup)

    _log("③ 在原路径建立目录联接")
    ok, msg = winapi.create_junction(src, dest)
    if not ok:
        # 回滚
        os.rename(backup, src)
        return False, f"建立联接失败，已回滚：{msg}"

    _log("④ 验证")
    if not os.path.isdir(src) or not os.path.isdir(dest):
        os.rename(backup, src)
        return False, "验证失败，已回滚"
    return True, (f"迁移完成。原数据已保留为备份：{backup}\n"
                  f"请启动应用确认数据正常后，再手动删除备份目录以释放 C 盘空间。")
