# -*- coding: utf-8 -*-
"""PCClean 入口。

启动时自动申请管理员权限（弹一次 UAC 即可，无需手动点“重启”）：
  - 若用打包好的 PCClean.exe 启动，exe 自带管理员清单，Windows 会直接弹 UAC；
  - 若用 python 直接跑，本文件会调用 ShellExecuteW(runas) 重新以管理员启动自身。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pcclean.config import ensure_app_dirs  # noqa: E402
from pcclean.utils import winapi  # noqa: E402


def _auto_elevate():
    """非管理员时尝试自动提权。返回 True 表示已提权并应由子进程继续。"""
    if winapi.is_admin():
        return False
    try:
        if winapi.elevate():
            return True   # 已拉起管理员进程，当前进程退出
    except Exception:  # noqa: BLE001
        pass
    return False


def main():
    ensure_app_dirs()
    if _auto_elevate():
        sys.exit(0)
    from pcclean.ui.app import run  # 延迟导入，提权失败也尽量能启动
    run()


if __name__ == "__main__":
    main()
