# -*- coding: utf-8 -*-
"""PCClean 图形界面（tkinter/ttk，中文，面向新手优化）。

三大标签页：磁盘清理 / 软件卸载 / 内存优化。
本版重点修复：
  1. 清理方式可选「直接删除」（真正释放空间）或「移入隔离区」（可回滚但不在C盘释放空间）；
  2. 隔离区位置可见、可打开、可清空；
  3. 清理后立即从列表移除已完成项，并给出实际释放空间；
  4. 启动时若隔离区有残留，提示占用并提供清空入口。
"""
import os
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog

from .. import config
from ..utils import winapi
from ..engine import scanner, rules, safety, executor, drivers, migrate, uninstall, ram


RISK_TEXT = {"A": "A·安全", "B": "B·建议", "C": "C·需确认", "D": "D·禁止"}


def _fmt(n):
    if n >= 1024 ** 4:
        return f"{n/1024**4:.2f} TB"
    if n >= 1024 ** 3:
        return f"{n/1024**3:.2f} GB"
    return f"{n/1024**2:.1f} MB"


def _open_folder(path):
    try:
        os.makedirs(path, exist_ok=True)
        os.startfile(path)  # noqa: S606
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("无法打开", f"{path}\n{e}")


def _fit(win, w, h):
    """按当前 DPI 缩放窗口尺寸，避免在高缩放下窗口过小。"""
    try:
        s = win.winfo_fpixels("1i") / 96.0
    except tk.TclError:
        s = 1.0
    s = max(1.0, s)
    win.geometry(f"{int(w * s)}x{int(h * s)}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self._jobs = []
        self._alive = True
        # ---- 高 DPI：按真实 DPI 缩放，文字清晰不糊 ----
        self._dpi = winapi.get_system_dpi()
        self.scale = max(1.0, self._dpi / 96.0)
        try:
            self.tk.call("tk", "scaling", self._dpi / 72.0)
        except tk.TclError:
            pass
        self.title(f"{config.APP_NAME}  v{config.VERSION}")
        s = self.scale
        self.geometry(f"{int(1120 * s)}x{int(760 * s)}")
        self.minsize(int(940 * s), int(640 * s))
        try:
            ttk.Style(self).theme_use("vista")
        except tk.TclError:
            pass
        try:
            # 字号用「点」，Tk 会按 tk scaling 自动换算像素，不能再乘 scale
            tkfont.nametofont("TkDefaultFont").configure(size=10)
        except tk.TclError:
            pass
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=int(26 * s))
        style.configure("Card.TFrame", relief="solid", borderwidth=1)
        style.configure("Big.TButton", font=("", 11, "bold"), padding=int(6 * s))
        style.configure("Head.TLabel", font=("", 13, "bold"))
        self._build_banner()
        self._build_status()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        self.tab_clean = CleanupTab(self.nb)
        self.tab_uninstall = UninstallTab(self.nb)
        self.tab_ram = RamTab(self.nb)
        self.nb.add(self.tab_clean, text="  ① 磁盘清理  ")
        self.nb.add(self.tab_uninstall, text="  ② 软件卸载  ")
        self.nb.add(self.tab_ram, text="  ③ 内存优化  ")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._poll_jobs)

    # ---------- 通用 ----------
    def _build_banner(self):
        if not winapi.is_admin():
            bar = ttk.Frame(self, padding=6)
            bar.pack(fill="x")
            ttk.Label(bar, foreground="#b26a00",
                      text="⚠ 当前为非管理员权限：清理系统缓存、卸载、驱动清理等功能受限。").pack(side="left")
            ttk.Button(bar, text="以管理员身份重启", command=self._elevate).pack(side="right")
            self.banner = bar

    def _elevate(self):
        if winapi.elevate():
            self.destroy()
        else:
            messagebox.showinfo("提示", "已取消提权，部分功能将不可用。")

    def _build_status(self):
        bar = ttk.Frame(self, padding=4)
        bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bar, textvariable=self.status_var, anchor="w").pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=180)
        self.progress.pack(side="right")

    def set_status(self, text):
        self.status_var.set(text)

    def busy(self, on=True):
        if on:
            self.progress.start(12)
        else:
            self.progress.stop()

    def run_async(self, fn, on_done=None, on_error=None):
        q = queue.Queue()
        self._jobs.append((q, on_done, on_error))

        def worker():
            try:
                q.put(("ok", fn()))
            except Exception as e:  # noqa: BLE001
                q.put(("err", e))
        threading.Thread(target=worker, daemon=True).start()

    def _poll_jobs(self):
        for job in list(self._jobs):
            q, od, oe = job
            try:
                kind, val = q.get_nowait()
            except queue.Empty:
                continue
            self._jobs.remove(job)
            if kind == "ok":
                if od:
                    od(val)
            else:
                if oe:
                    oe(val)
                else:
                    self.set_status(f"出错：{val}")
        if self._alive:
            self.after(80, self._poll_jobs)

    def _on_close(self):
        self._alive = False
        self.destroy()


class CleanupTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.items = []
        self.checked = set()
        self._qsize = 0
        self.mode_var = tk.StringVar(value="delete")  # delete / quarantine
        self.show_tiny = tk.BooleanVar(value=False)
        self._build()
        self._measure_quarantine()

    def _build(self):
        # 顶部：摘要卡片
        head = ttk.Frame(self, padding=(4, 6, 4, 2))
        head.pack(fill="x")
        ttk.Label(head, text="磁盘清理", style="Head.TLabel").pack(side="left")
        self.sum_clean = ttk.Label(head, text="可清理：--", foreground="#2e7d32")
        self.sum_clean.pack(side="left", padx=16)
        self.sum_sel = ttk.Label(head, text="已选：--", foreground="#1565c0")
        self.sum_sel.pack(side="left", padx=8)
        self.sum_quar = ttk.Label(head, text="隔离区：--", foreground="#b26a00")
        self.sum_quar.pack(side="left", padx=8)
        ttk.Button(head, text="隔离区管理", command=self.quarantine_dialog).pack(side="right", padx=3)

        # 工具栏
        top = ttk.Frame(self, padding=(4, 4))
        top.pack(fill="x")
        ttk.Button(top, text="开始扫描", command=self.scan).pack(side="left", padx=3)
        ttk.Button(top, text="全选安全项(A)", command=lambda: self.select_risk("A")).pack(side="left", padx=3)
        ttk.Button(top, text="全不选", command=self.select_none).pack(side="left", padx=3)
        ttk.Checkbutton(top, text="显示 <0.1MB 小项", variable=self.show_tiny,
                        command=self.scan).pack(side="left", padx=3)
        ttk.Button(top, text="NVIDIA 旧驱动", command=self.nvidia_dialog).pack(side="left", padx=3)
        ttk.Button(top, text="微信/QQ/剪映迁移", command=self.migrate_dialog).pack(side="left", padx=3)
        ttk.Button(top, text="改默认存储位置", command=self.guide_dialog).pack(side="left", padx=3)

        # 清理方式
        modebar = ttk.LabelFrame(self, text="清理方式", padding=6)
        modebar.pack(fill="x", padx=4)
        ttk.Radiobutton(modebar, text="直接删除（推荐，真正释放磁盘空间）",
                        variable=self.mode_var, value="delete").pack(side="left", padx=6)
        ttk.Radiobutton(modebar, text="移入隔离区（可回滚，但不释放空间）",
                        variable=self.mode_var, value="quarantine").pack(side="left", padx=6)
        ttk.Label(modebar, foreground="#777",
                  text="提示：隔离区只是把文件移到 C 盘的另一个文件夹，需在「隔离区管理」中清空才会释放空间。").pack(side="left", padx=10)

        # 上次清理记录 + 缓存会重建说明
        self.last_lbl = ttk.Label(self, foreground="#1565c0", padding=(6, 2))
        self.last_lbl.pack(fill="x")
        ttk.Label(self, foreground="#666", padding=(6, 0), justify="left",
                  text="说明：缓存类项目会随程序使用自动重新生成（属正常现象）。豆包/DeepSeek 等若正在运行，其缓存无法清理，"
                       "清理前会询问是否自动结束它们。").pack(fill="x")
        self._refresh_last_clean()

        # 列表
        sc = getattr(self.master.master, "scale", 1.0)
        cols = ("check", "label", "cat", "size", "risk", "evidence")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for c, t, w, a in (("check", "勾选", 46, "center"), ("label", "清理项", 300, "w"),
                           ("cat", "分类", 110, "w"), ("size", "大小", 92, "e"),
                           ("risk", "风险", 84, "center"), ("evidence", "说明", 380, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=int(w * sc), anchor=a, stretch=(c in ("label", "evidence")))
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=(4, 4))
        vsb.pack(side="right", fill="y", pady=(4, 4))
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.tag_configure("running", foreground="#c62828")

        # 底部操作
        bottom = ttk.Frame(self, padding=(4, 4))
        bottom.pack(fill="x", side="bottom")
        ttk.Button(bottom, text="开始清理", style="Big.TButton", command=self.clean).pack(side="left", padx=3)
        self.hint = ttk.Label(bottom, text="", foreground="#555")
        self.hint.pack(side="left", padx=12)

    # ---------- 扫描 ----------
    def _dynamic_candidates(self):
        cands = []
        la = os.environ.get("LOCALAPPDATA", "")
        if la and os.path.isdir(la):
            for name in os.listdir(la):
                if "updater" not in name.lower():
                    continue
                p = os.path.join(la, name)
                if os.path.isdir(p) and not winapi.is_reparse_point(p):
                    cands.append({"path": p, "kind": "dir", "category": "更新包/安装缓存",
                                  "label": f"更新器缓存 · {name}", "risk": "B",
                                  "action": "delete", "evidence": "应用更新器下载的安装包，可安全删除"})
        cands += rules.detect_versioned_dirs(r"%LOCALAPPDATA%\Claude-3p\claude-code", r"\d+\.\d+", "Claude")
        cands += rules.detect_versioned_dirs(r"%LOCALAPPDATA%\OpenAI\Codex\bin", r"[0-9a-f]{8,}", "Codex")
        cands += rules.detect_versioned_dirs(r"%LOCALAPPDATA%\OpenAI\Codex\runtimes\cua_node", r"[0-9a-f]{8,}", "Codex")
        return cands

    def scan(self):
        self.set_status("正在扫描，请稍候…")
        self.busy(True)

        def work():
            cands = rules.build_rules() + drivers.nvidia_cache_targets() + self._dynamic_candidates()
            return scanner.collect(cands, include_tiny=self.show_tiny.get())

        def done(items):
            self.busy(False)
            seen, uniq = set(), []
            for it in items:
                k = os.path.normcase(it.path)
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(it)
            self.items = uniq
            self.checked = {os.path.normcase(it.path) for it in uniq if it.risk == "A"}
            # 标记「相关程序正在运行」的项目
            live = set(winapi.list_process_names())
            for it in uniq:
                if it.guard:
                    it.guard_running = any(g.lower() in live for g in it.guard)
            self._render()
            self._update_summary()
            self.set_status("扫描完成")
            self._refresh_quarantine_hint()

        self.run_async(work, done)

    def _render(self):
        self.tree.delete(*self.tree.get_children())
        for it in self.items:
            k = os.path.normcase(it.path)
            mark = "☑" if k in self.checked else "☐"
            ev = it.evidence
            tags = ()
            if getattr(it, "guard_running", False):
                ev = "⚠ 程序运行中，需先退出　" + ev
                tags = ("running",)
            self.tree.insert("", "end", iid=k, values=(
                mark, it.label, it.category, _fmt(it.size),
                RISK_TEXT.get(it.risk, it.risk), ev), tags=tags)

    def _on_click(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        if row in self.checked:
            self.checked.discard(row)
        else:
            self.checked.add(row)
        self._render()
        self._update_summary()

    def select_risk(self, risk):
        self.checked = {os.path.normcase(it.path) for it in self.items if it.risk == risk}
        self._render()
        self._update_summary()

    def select_none(self):
        self.checked = set()
        self._render()
        self._update_summary()

    def selected_items(self):
        return [it for it in self.items if os.path.normcase(it.path) in self.checked]

    def _update_summary(self):
        total = sum(i.size for i in self.items)
        auto = sum(i.size for i in self.items if i.risk == "A")
        sel = sum(i.size for i in self.selected_items())
        hidden = "" if self.show_tiny.get() else " · 已隐藏<0.1MB小项"
        self.sum_clean.config(text=f"可清理：{_fmt(total)}（安全项 {_fmt(auto)}）{hidden}")
        self.sum_sel.config(text=f"已选：{_fmt(sel)}")
        self.sum_quar.config(text=f"隔离区：{_fmt(self._qsize)}")

    def _measure_quarantine(self):
        """后台测量隔离区体积，完成后刷新摘要与提示（避免阻塞 UI）。"""
        def w():
            total = 0
            for r in safety.quarantine_roots():
                s, _ = scanner.dir_size(r)
                total += s
            return total

        def d(total):
            self._qsize = total
            self._update_summary()
            self._refresh_quarantine_hint()

        self.run_async(w, d)

    def _refresh_quarantine_hint(self):
        if self._qsize > 0:
            self.hint.config(
                text=f"⚠ 隔离区当前占用 {_fmt(self._qsize)}（位于 C 盘，未释放空间）。点『隔离区管理』→『清空全部』可立即释放。",
                foreground="#b26a00")
        else:
            self.hint.config(text="", foreground="#555")

    # ---------- 清理 ----------
    def clean(self):
        sel = self.selected_items()
        if not sel:
            messagebox.showinfo("提示", "请先勾选要清理的项目（可点『全选安全项(A)』）。")
            return
        # 1) 先处理「相关程序正在运行」：询问是否自动结束
        sel = self._resolve_running(sel)
        if sel is None:
            return
        if not sel:
            messagebox.showinfo("提示", "选中的项目都需要先退出相关程序，已全部跳过。\n可先退出豆包/DeepSeek 等程序后再清理。")
            return
        mode = self.mode_var.get()
        size = sum(i.size for i in sel)
        if mode == "delete":
            tip = (f"将【彻底删除】{len(sel)} 项，共 {_fmt(size)}。\n"
                   "删除后不可恢复，但会真正释放磁盘空间。\n\n确认继续？")
        else:
            tip = (f"将把 {len(sel)} 项（{_fmt(size)}）移入隔离区。\n"
                   "注意：隔离区在 C 盘，此操作【不会释放空间】，只保证可回滚。\n\n确认继续？")
        if not messagebox.askyesno("确认清理", tip):
            return

        free_before = winapi.get_free_space(config.SYSTEMDRIVE + "\\")

        def work():
            return executor.perform(sel, mode=mode, log_cb=self._log)

        def done(r):
            self.busy(False)
            free_after = winapi.get_free_space(config.SYSTEMDRIVE + "\\")
            delta = (free_after[0] - free_before[0]) if (free_before and free_after) else 0
            # 立即从列表移除已完成项（新版结果为 dict）
            ok_paths = {os.path.normcase(x["item"].path) for x in r["results"] if x["status"] == "ok"}
            self.items = [it for it in self.items if os.path.normcase(it.path) not in ok_paths]
            self.checked -= ok_paths
            self._render()
            self._update_summary()
            safety.history_append({"op": "clean", "mode": mode, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                   "cleaned": r["cleaned"], "skipped": r["skipped"], "freed": r["freed"]})
            self._refresh_last_clean()
            if mode == "delete":
                msg = (f"清理完成：成功 {r['cleaned']} 项，跳过 {r['skipped']} 项。\n"
                       f"C 盘实际释放：{_fmt(max(delta, 0))}")
            else:
                msg = (f"已移入隔离区：{r['cleaned']} 项，跳过 {r['skipped']} 项。\n"
                       f"C 盘可释放空间：{_fmt(max(delta, 0))}（隔离区未清空前不释放）\n\n"
                       "可到『隔离区管理』中清空以立即释放空间。")
            if r["skipped"]:
                msg += "\n\n有项目被跳过，接下来会显示「跳过详情」，逐项说明原因与解决办法。"
            messagebox.showinfo("完成", msg)
            self.set_status("清理完成")
            self._measure_quarantine()
            self.scan()  # 后台重新扫描，确认剩余项
            if r["skipped"]:
                self._show_skipped(r["results"])

        self.busy(True)
        self.set_status("正在清理…")
        self.run_async(work, done)

    def _refresh_last_clean(self):
        """显示上次清理结果，便于判断"是不是又回来了"。"""
        rec = safety.last_record()
        if not rec or rec.get("op") != "clean":
            self.last_lbl.config(text="上次清理：暂无记录")
            return
        txt = (f"上次清理：{rec.get('time', '')}　成功 {rec.get('cleaned', 0)} 项"
               f"，跳过 {rec.get('skipped', 0)} 项")
        if rec.get("skipped"):
            txt += "（跳过多为程序占用；刚清理的缓存随程序使用会再次生成，属正常）"
        self.last_lbl.config(text=txt)

    def _resolve_running(self, sel):
        """检测选中项的相关程序是否在运行；询问是否自动结束。返回处理后的选项或 None。"""
        guards = set()
        for it in sel:
            for g in (it.guard or []):
                guards.add(g)
        running = winapi.running_processes(sorted(guards)) if guards else []
        if not running:
            return sel
        ans = messagebox.askyesnocancel(
            "需要先退出程序",
            "检测到以下程序正在运行，它们的缓存无法清理：\n\n"
            + "\n".join("• " + n for n in running)
            + "\n\n【是】自动结束这些程序后清理（未保存内容可能丢失）\n"
              "【否】只清理其余项目，跳过它们的缓存\n"
              "【取消】不清理")
        if ans is None:
            return None
        if ans:
            winapi.kill_processes(running)
            time.sleep(1.2)  # 等句柄释放
            return sel
        rl = {x.lower() for x in running}
        return [it for it in sel if not (set(g.lower() for g in (it.guard or [])) & rl)]

    def _show_skipped(self, results):
        """展示跳过项的原因与解决办法。"""
        skipped = [x for x in results if x["status"] != "ok"]
        if not skipped:
            return
        win = tk.Toplevel(self)
        win.title("跳过详情 —— 原因与解决办法")
        _fit(win, 1020, 540)
        win.transient(self)
        ttk.Label(win, foreground="#b26a00", padding=8, justify="left",
                  text=(f"有 {len(skipped)} 项被跳过。最常见的原因是「程序正在运行」或「需要管理员权限」，"
                        "按下面的「解决办法」处理后点『重新扫描』即可再次清理。")).pack(fill="x")
        cols = ("label", "size", "reason", "solution", "path")
        sc = getattr(self.master.master, "scale", 1.0)
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c, t, w in (("label", "项目", 200), ("size", "大小", 76),
                        ("reason", "跳过原因", 140), ("solution", "解决办法", 400),
                        ("path", "路径", 300)):
            tree.heading(c, text=t)
            tree.column(c, width=int(w * sc), anchor=("e" if c == "size" else "w"))
        vsb = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4)
        for x in skipped:
            it = x["item"]
            tree.insert("", "end", values=(it.label, _fmt(it.size),
                                           x.get("reason") or "其它原因",
                                           x.get("solution") or "", it.path))
        bar = ttk.Frame(win, padding=8)
        bar.pack(fill="x", side="bottom")
        ttk.Button(bar, text="重新扫描", command=lambda: (win.destroy(), self.scan())).pack(side="right", padx=2)
        ttk.Button(bar, text="知道了", command=win.destroy).pack(side="right", padx=2)

    # ---------- 隔离区管理 ----------
    def quarantine_dialog(self):
        win = tk.Toplevel(self)
        win.title("隔离区管理")
        _fit(win, 880, 520)
        win.transient(self)
        path_lbl = ttk.Entry(win)
        path_lbl.pack(fill="x", padx=8, pady=(8, 2))
        root = os.path.join(config.APP_DIR, "Quarantine")
        path_lbl.insert(0, root)
        path_lbl.config(state="readonly")
        bar = ttk.Frame(win, padding=(8, 2))
        bar.pack(fill="x")
        ttk.Button(bar, text="打开文件夹", command=lambda: _open_folder(root)).pack(side="left", padx=2)
        ttk.Button(bar, text="刷新", command=lambda: self._load_quarantine(tree, info)).pack(side="left", padx=2)

        info = ttk.Label(win, text="", padding=6)
        info.pack(fill="x")
        cols = ("time", "orig", "reason")
        sc = getattr(self.master.master, "scale", 1.0)
        tree = ttk.Treeview(win, columns=cols, show="headings")
        tree.heading("time", text="时间")
        tree.heading("orig", text="原路径")
        tree.heading("reason", text="说明")
        tree.column("time", width=int(150 * sc))
        tree.column("orig", width=int(520 * sc))
        tree.column("reason", width=int(180 * sc))
        tree.pack(fill="both", expand=True, padx=8, pady=4)
        self._qtree = tree

        bottom = ttk.Frame(win, padding=8)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="恢复所选", command=lambda: self._q_restore(tree)).pack(side="left", padx=2)
        ttk.Button(bottom, text="彻底删除所选", command=lambda: self._q_delete(tree, info)).pack(side="left", padx=2)
        ttk.Button(bottom, text="清空全部（释放空间）", command=lambda: self._q_purge(info, win)).pack(side="left", padx=2)

        self._load_quarantine(tree, info, win)

    def _load_quarantine(self, tree, info, win=None):
        tree.delete(*tree.get_children())
        entries = safety.quarantine_entries()
        for i, e in enumerate(entries):
            tree.insert("", "end", iid=str(i),
                        values=(e.get("time", ""), e.get("original", ""), e.get("reason", "")))
        self._qentries = entries
        if not entries:
            info.config(text="隔离区为空。")
            return
        info.config(text=f"共 {len(entries)} 项，正在统计占用…")

        def w():
            total = 0
            for e in entries:
                p = e.get("quarantined")
                if p and os.path.exists(p):
                    if os.path.isdir(p):
                        s, _ = scanner.dir_size(p)
                    else:
                        try:
                            s = os.path.getsize(p)
                        except OSError:
                            s = 0
                    total += s
                else:
                    total += e.get("size", 0)
            return total

        def d(total):
            info.config(text=f"共 {len(entries)} 项，约 {_fmt(total)}。彻底删除/清空后才会真正释放空间。")

        self.run_async(w, d)

    def _q_restore(self, tree):
        sel = [self._qentries[int(i)] for i in tree.selection()]
        if not sel:
            return
        ok = sum(1 for e in sel if safety.restore(e))
        messagebox.showinfo("回滚", f"已恢复 {ok} 项。")
        self.quarantine_refresh(tree)
        self._measure_quarantine()

    def _q_delete(self, tree):
        sel = [self._qentries[int(i)] for i in tree.selection()]
        if not sel:
            return
        if not messagebox.askyesno("彻底删除", "将彻底删除所选隔离文件（不可恢复），并释放空间。确认？"):
            return
        ok = sum(1 for e in sel if safety.delete_quarantined(e))
        messagebox.showinfo("完成", f"已彻底删除 {ok} 项。")
        self.quarantine_refresh(tree)
        self._measure_quarantine()

    def _q_purge(self, info, win):
        if not messagebox.askyesno("清空隔离区", "将彻底删除隔离区中的所有文件（不可恢复），立即释放 C 盘空间。确认？"):
            return
        self.set_status("正在清空隔离区…")
        self.busy(True)

        def w():
            return safety.purge_all_quarantine()

        def d(res):
            self.busy(False)
            ok, bad = res
            messagebox.showinfo("完成", f"已清空 {ok} 项（失败 {bad} 项）。C 盘空间已释放。")
            self._measure_quarantine()
            self._update_summary()
            win.destroy()

        self.run_async(w, d)

    def quarantine_refresh(self, tree):
        entries = safety.quarantine_entries()
        self._qentries = entries
        tree.delete(*tree.get_children())
        for i, e in enumerate(entries):
            tree.insert("", "end", iid=str(i),
                        values=(e.get("time", ""), e.get("original", ""), e.get("reason", "")))
        self._update_summary()

    # ---------- NVIDIA ----------
    def nvidia_dialog(self):
        win = tk.Toplevel(self)
        win.title("NVIDIA 旧驱动清理")
        _fit(win, 720, 480)
        info = ttk.Label(win, text="正在读取…", padding=8)
        info.pack(fill="x")
        tree = ttk.Treeview(win, columns=("name", "ver"), show="headings")
        tree.heading("name", text="驱动包 (oemNN.inf)")
        tree.heading("ver", text="版本/日期")
        sc = getattr(self.master.master, "scale", 1.0)
        tree.column("name", width=int(360 * sc))
        tree.column("ver", width=int(260 * sc))
        tree.pack(fill="both", expand=True, padx=8)
        bar = ttk.Frame(win, padding=8)
        bar.pack(fill="x")
        ttk.Button(bar, text="创建还原点", command=lambda: self._do_restore_point(info)).pack(side="left", padx=2)
        ttk.Button(bar, text="删除所选旧驱动", command=lambda: self._do_delete_driver(tree, info)).pack(side="left", padx=2)

        def load():
            if not winapi.is_admin():
                info.config(text="⚠ 需要管理员权限才能读取/删除驱动。请先以管理员身份重启本软件。")
                return
            ver = drivers.current_driver_version()
            cur = drivers.current_inf_paths()
            olds = drivers.old_packages()
            info.config(text=f"当前 NVIDIA 驱动版本：{ver}；在用驱动：{', '.join(sorted(cur)) or '无'}；"
                             f"发现可清理旧驱动包 {len(olds)} 个。")
            for p in olds:
                tree.insert("", "end", iid=p["published"],
                            values=(f"{p['published']}  ({p['original']})", p["version"]))
            if not olds:
                tree.insert("", "end", values=("没有可清理的旧驱动包（只有当前一个或无可访问权限）", ""))
        self.run_async(load)

    def _do_restore_point(self, info):
        self.set_status("正在创建还原点…")
        self.run_async(drivers.create_restore_point,
                       lambda r: info.config(text="还原点已创建" if r[0] else f"创建失败：{r[1]}"))

    def _do_delete_driver(self, tree, info):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的旧驱动。")
            return
        if not messagebox.askyesno("确认", f"删除 {len(sel)} 个未被使用的旧 NVIDIA 驱动包（不影响当前驱动）。继续？"):
            return

        def w():
            return [(oem, drivers.delete_package(oem)) for oem in sel]

        def d(logs):
            for oem, (ok, msg) in logs:
                info.config(text=f"{oem}: {'已删除' if ok else '失败 ' + msg}")
            messagebox.showinfo("完成", "旧驱动已清理，建议重启验证（nvidia-smi 版本应不变）。")
            self.set_status("驱动清理完成")
        self.run_async(w, d)

    # ---------- 迁移 ----------
    def migrate_dialog(self):
        win = tk.Toplevel(self)
        win.title("微信 / QQ / 剪映 数据迁移")
        _fit(win, 760, 520)
        ttk.Label(win, text="勾选要迁移到其它盘的数据（不会删除原数据，会保留 *_backup 备份）：",
                  padding=8).pack(fill="x")
        frame = ttk.Frame(win, padding=8)
        frame.pack(fill="both", expand=True)
        rows = migrate.detect()
        vars_ = {}
        for i, r in enumerate(rows):
            var = tk.BooleanVar(value=False)
            vars_[r["app"]] = var
            if r["exists"]:
                text = f"{r['app']}  ——  {_fmt(r['size'])}  ({r['src']})"
            else:
                text = f"{r['app']}  ——  未检测到数据"
            ttk.Checkbutton(frame, text=text, variable=var).grid(row=i, column=0, sticky="w", pady=3)
        ttk.Label(frame, text="迁移到（留空默认 D 盘）：").grid(row=len(rows), column=0, sticky="w", pady=(10, 0))
        dest_var = tk.StringVar(value="")
        ttk.Entry(frame, textvariable=dest_var, width=64).grid(row=len(rows) + 1, column=0, sticky="w")
        log = tk.Text(frame, height=12, state="disabled")
        log.grid(row=len(rows) + 2, column=0, sticky="nsew", pady=6)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(len(rows) + 2, weight=1)

        def log_msg(m):
            log.config(state="normal")
            log.insert("end", m + "\n")
            log.see("end")
            log.config(state="disabled")

        def go():
            chosen = [(r["app"], r["src"], r["guard"]) for r in rows if vars_[r["app"]].get() and r["exists"]]
            if not chosen:
                messagebox.showinfo("提示", "请先勾选要迁移的数据。")
                return
            base = dest_var.get().strip() or "D:\\"
            if not base.endswith("\\"):
                base += "\\"

            def w():
                for app, src, guard in chosen:
                    running = migrate.is_running(guard)
                    if running:
                        log_msg(f"✗ {app} 仍在运行（{','.join(running)}），请先完全退出。")
                        continue
                    dest = os.path.join(base, os.path.basename(src.rstrip("\\/")))
                    log_msg(f"→ 迁移 {app}：{src} → {dest}")
                    ok, msg = migrate.do_migrate(src, dest, log_cb=log_msg)
                    log_msg(("✓ " if ok else "✗ ") + msg)
                log_msg("—— 全部处理完成 ——")
            self.run_async(w)
        ttk.Button(frame, text="开始迁移", command=go).grid(row=len(rows) + 3, column=0, sticky="w", pady=4)
        ttk.Button(frame, text="查看设置教程", command=self.guide_dialog).grid(row=len(rows) + 3, column=0, sticky="e", pady=4)

    def guide_dialog(self):
        win = tk.Toplevel(self)
        win.title("如何修改默认存储位置（防止再次占满 C 盘）")
        _fit(win, 760, 560)
        txt = tk.Text(win, wrap="word", padx=12, pady=12)
        txt.pack(fill="both", expand=True)
        content = "【通用建议】\n把聊天记录、草稿、下载、文档等默认位置改到 D 盘，是治本之法。\n\n"
        for app, g in migrate.GUIDES.items():
            content += f"◆ {app}\n{g}\n\n"
        content += ("【其它】\n"
                    "• 浏览器下载位置：Edge/Chrome 设置 → 下载 → 改为 D:\\Downloads\n"
                    "• 系统存储：设置 → 系统 → 存储 → 高级存储设置 → 新内容保存位置 → 改为 D 盘\n"
                    "• 文档/图片/桌面：资源管理器右键文件夹 → 属性 → 位置 → 移动\n")
        txt.insert("1.0", content)
        txt.config(state="disabled")

    # ---------- 适配 ----------
    def _log(self, m):
        self.set_status(m)

    def set_status(self, m):
        self.master.master.set_status(m)

    def busy(self, on):
        self.master.master.busy(on)

    def run_async(self, fn, on_done=None, on_error=None):
        self.master.master.run_async(fn, on_done, on_error)


class UninstallTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.apps = []
        self._build()

    def _build(self):
        head = ttk.Frame(self, padding=(4, 6, 4, 2))
        head.pack(fill="x")
        ttk.Label(head, text="软件卸载", style="Head.TLabel").pack(side="left")
        top = ttk.Frame(self, padding=(4, 4))
        top.pack(fill="x")
        ttk.Button(top, text="刷新列表", command=self.refresh).pack(side="left", padx=3)
        ttk.Button(top, text="卸载", command=lambda: self._do_uninstall(False)).pack(side="left", padx=3)
        ttk.Button(top, text="卸载并清理残留", command=lambda: self._do_uninstall(True)).pack(side="left", padx=3)
        ttk.Button(top, text="强制移除(残留)", command=self._force).pack(side="left", padx=3)
        ttk.Button(top, text="导出列表", command=self._export).pack(side="left", padx=3)
        ttk.Label(top, foreground="#777", text="提示：卸载/清理残留需要管理员权限。").pack(side="right")

        cols = ("name", "ver", "vendor", "kind", "size")
        sc = getattr(self.master.master, "scale", 1.0)
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("name", "名称", 340), ("ver", "版本", 110),
                        ("vendor", "厂商", 190), ("kind", "类型", 80), ("size", "大小", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=int(w * sc), stretch=(c in ("name", "vendor")))
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=(4, 4))
        vsb.pack(side="right", fill="y", pady=(4, 4))
        self.refresh()

    def refresh(self):
        self.set_status("正在枚举已安装软件…")
        self.busy(True)

        def w():
            apps = uninstall.list_apps()
            skip = ("visual c++", ".net", "directx", "windows sdk", "nvidia physx",
                    "microsoft edge", "microsoft visual")
            return [a for a in apps if not any(s in a["name"].lower() for s in skip)]

        def d(apps):
            self.busy(False)
            self.apps = apps
            self.tree.delete(*self.tree.get_children())
            for a in apps:
                size = f"{a['size_kb']/1024:.0f} MB" if a.get("size_kb") else ""
                kind = "UWP" if a.get("kind") == "appx" else "应用"
                self.tree.insert("", "end", iid=str(id(a)), values=(
                    a["name"], a.get("version", ""), a.get("publisher", ""), kind, size))
            self.set_status(f"共 {len(apps)} 个软件")
        self.run_async(w, d)

    def _selected(self):
        row = self.tree.selection()
        if not row:
            return None
        for a in self.apps:
            if str(id(a)) == row[0]:
                return a
        return None

    def _do_uninstall(self, with_leftover):
        app = self._selected()
        if not app:
            messagebox.showinfo("提示", "请先选择一个软件。")
            return
        if not messagebox.askyesno("卸载", f"将卸载：{app['name']}\n\n继续？"):
            return
        self.set_status(f"正在卸载 {app['name']} …")
        self.busy(True)
        self.run_async(lambda: uninstall.run_uninstaller(app, silent=False, log_cb=self._log),
                       lambda r: self._after_uninstall(r, app, with_leftover))

    def _after_uninstall(self, r, app, with_leftover):
        self.busy(False)
        ok, msg, reboot = r
        self._log(msg)
        messagebox.showinfo("卸载结果", msg + ("（建议重启）" if reboot else ""))
        if ok and with_leftover:
            self._scan_leftovers(app)
        self.refresh()

    def _scan_leftovers(self, app):
        self.set_status(f"正在扫描 {app['name']} 的残留…")
        self.busy(True)

        def d(r):
            self.busy(False)
            files, regs = r["files"], r["registry"]
            if not files and not regs:
                messagebox.showinfo("残留", "未发现明显残留。")
                return
            win = tk.Toplevel(self)
            win.title(f"{app['name']} 的残留")
            win.geometry("800x500")
            lb = tk.Listbox(win, selectmode="extended")
            lb.pack(fill="both", expand=True, padx=8, pady=8)
            for f in files:
                lb.insert("end", f"[文件] {f['path']}  ({f.get('reason','')})")
            for g in regs:
                lb.insert("end", f"[注册表] {g['hive']}\\{g['path']}  ({g.get('reason','')})")
            for i in range(len(files)):
                lb.selection_set(i)
            self._lr = (files, regs)

            def do_clean():
                fi = [files[i] for i in lb.curselection() if i < len(files)]
                ri = [regs[i - len(files)] for i in lb.curselection() if i >= len(files)]
                if messagebox.askyesno("确认", f"清理 {len(fi)} 个文件（进隔离区）和 {len(ri)} 个注册表项（先备份）。继续？"):
                    self.busy(True)
                    self.run_async(lambda: uninstall.clean_leftovers(fi, ri, log_cb=self._log),
                                   lambda res: (self.busy(False),
                                                messagebox.showinfo("完成", f"已清理 {res['files']} 文件、{res['registry']} 注册表项。"),
                                                win.destroy()))
            bar = ttk.Frame(win, padding=8)
            bar.pack(fill="x")
            ttk.Button(bar, text="清理所选", command=do_clean).pack(side="left", padx=2)
            ttk.Button(bar, text="关闭", command=win.destroy).pack(side="left", padx=2)

        self.run_async(lambda: uninstall.scan_leftovers(app), d)

    def _force(self):
        app = self._selected()
        if not app:
            messagebox.showinfo("提示", "请先选择一个软件。")
            return
        if not messagebox.askyesno("强制移除",
                f"跳过卸载程序，直接清理 {app['name']} 的注册表登记与残留文件。\n"
                "仅适用于卸载程序损坏/卸载失败的情况。继续？"):
            return
        self.busy(True)

        def d(res):
            self.busy(False)
            messagebox.showinfo("完成", f"已清理 {res['files']} 个文件、{res['registry']} 个注册表项。")
            self.refresh()
        self.run_async(lambda: uninstall.force_remove(app, log_cb=self._log), d)

    def _export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile="installed_apps.csv")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["名称", "版本", "厂商", "类型", "大小(KB)", "安装位置"])
            for a in self.apps:
                w.writerow([a["name"], a.get("version", ""), a.get("publisher", ""),
                            a.get("kind", ""), a.get("size_kb", ""), a.get("install_location", "")])
        messagebox.showinfo("导出", f"已导出到 {path}")

    def _log(self, m):
        self.set_status(m)

    def set_status(self, m):
        self.master.master.set_status(m)

    def busy(self, on):
        self.master.master.busy(on)

    def run_async(self, fn, on_done=None, on_error=None):
        self.master.master.run_async(fn, on_done, on_error)


class RamTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self._build()
        self.refresh()

    def _build(self):
        head = ttk.Frame(self, padding=(4, 6, 4, 2))
        head.pack(fill="x")
        ttk.Label(head, text="内存优化", style="Head.TLabel").pack(side="left")
        self.info = ttk.Label(self, text="", padding=8, font=("", 12))
        self.info.pack(fill="x")
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Button(top, text="刷新状态", command=self.refresh).pack(side="left", padx=2)
        ttk.Button(top, text="一键加速", style="Big.TButton", command=self.boost).pack(side="left", padx=2)
        ttk.Button(top, text="开启游戏模式", command=self.game_mode).pack(side="left", padx=2)
        ttk.Label(self, foreground="#555", justify="left", padding=8,
                  text=("⚠ 诚实说明：Windows 内存管理已很好，「内存优化」作用常被高估。\n"
                        "真正的提速来自关闭真正占内存的后台程序、物理加内存。本工具只做安全的：\n"
                        "① 让后台程序工作集让位  ② 刷新 DNS  ③ 清理临时文件。不做清注册表/关虚拟内存等有害操作。")).pack(fill="x")
        adv = ttk.LabelFrame(self, text="高级选项（需管理员，谨慎）", padding=8)
        adv.pack(fill="x", padx=6, pady=6)
        ttk.Button(adv, text="清空备用内存(温和)", command=lambda: self._standby(True)).pack(side="left", padx=2)
        ttk.Button(adv, text="清空备用内存(激进)", command=lambda: self._standby(False)).pack(side="left", padx=2)
        self.mmc = ttk.Label(adv, text="内存压缩：检测中…", padding=4)
        self.mmc.pack(side="left", padx=10)

    def refresh(self):
        info = ram.ram_info()
        used = info["total"] - info["avail"]
        self.info.config(text=(f"物理内存：{info['total']/1024**3:.1f} GB    "
                               f"已用：{used/1024**3:.1f} GB    "
                               f"可用：{info['avail']/1024**3:.1f} GB    "
                               f"占用率：{info['load_pct']}%"))
        self.run_async(ram.memory_compression_enabled,
                       lambda v: self.mmc.config(
                           text="内存压缩：" + ("需管理员查看" if v is None else ("已开启(推荐)" if v else "未开启"))))

    def boost(self):
        self.set_status("正在加速…")
        self.busy(True)

        def w():
            ok, msg = ram.flush_dns()
            done, failed, skipped = ram.trim_working_sets(exclude={"python.exe", "pythonw.exe"})
            return [("刷新 DNS", ok, msg), ("整理后台工作集", True, f"成功 {done}，失败 {failed}，跳过 {skipped}")]

        def d(logs):
            self.busy(False)
            for name, ok, msg in logs:
                self._log(f"{name}：{msg}")
            messagebox.showinfo("完成", "一键加速完成。\n提示：重启电脑是最彻底的「清理」。")
            self.refresh()
        self.run_async(w, d)

    def game_mode(self):
        messagebox.showinfo("完成", "游戏模式已开启（个别游戏可改善帧率稳定性）。") if ram.enable_game_mode() \
            else messagebox.showinfo("失败", "开启游戏模式失败。")

    def _standby(self, priority0):
        if not winapi.is_admin():
            messagebox.showinfo("提示", "清空备用内存需要管理员权限。")
            return
        if not messagebox.askyesno("确认", "将清空备用内存列表。这通常是安慰剂且会短暂降低缓存命中。继续？"):
            return
        ok = ram.clear_standby(priority0_only=priority0)
        messagebox.showinfo("完成", "已清空备用内存。" if ok else "操作失败（权限不足？）")

    def _log(self, m):
        self.set_status(m)

    def set_status(self, m):
        self.master.master.set_status(m)

    def busy(self, on):
        self.master.master.busy(on)

    def run_async(self, fn, on_done=None, on_error=None):
        self.master.master.run_async(fn, on_done, on_error)


def run():
    # 必须在创建任何窗口之前声明 DPI 感知，否则高缩放下文字会被系统拉伸发虚
    winapi.enable_dpi_awareness()
    app = App()
    app.mainloop()
