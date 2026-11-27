# -*- coding: utf-8 -*-
"""清理规则目录：AI 客户端 / 系统 / 浏览器 / 开发 / 更新包。

每个规则是一个 dict：
  path: 含 %环境变量% 与可选通配符的路径（scanner 会展开并测体积）
  category/label/risk/action/evidence/app/guard/needs_admin
风险：A 可自动 / B 建议确认 / C 需确认（大件或会丢状态）/ D 禁止
"""

# ---- 分类名 ----
CAT_AI = "AI 缓存"
CAT_SYS = "系统缓存"
CAT_BROWSER = "浏览器缓存"
CAT_DEV = "开发缓存"
CAT_UPDATER = "更新包/安装缓存"
CAT_TEMP = "临时文件"
CAT_BIN = "回收站"
CAT_JUNK = "其它垃圾"

# ---- Chromium/Electron 标准可删缓存叶子目录 ----
CHROMIUM_CACHE_LEAVES = [
    "Cache", "Code Cache", "GPUCache", "GrShaderCache",
    "ShaderCache", "GraphiteDawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
    "DawnCache", "GPUPersistentCache", "blob_storage", "Crashpad",
    "logs", "Session Storage",
    "Service Worker\\CacheStorage", "Service Worker\\ScriptCache", "Shared Dictionary",
]

# 应用 → 进程名（清理前需先退出）
PROC_GUARDS = {
    "doubao": ["Doubao.exe"],
    "deepseek": ["DeepSeek Harness.exe", "dsh.exe"],
    "chatgpt": ["ChatGPT.exe", "Codex.exe"],
    "claude": ["Claude.exe", "claude.exe"],
    "kimi": ["Kimi.exe", "kimi.exe"],
    "qianwen": ["Qianwen.exe", "Qwen.exe", "tongyi.exe"],
    "yuanbao": ["Yuanbao.exe", "TencentYuanbao.exe"],
    "cursor": ["Cursor.exe"],
    "cherry": ["Cherry Studio.exe", "CherryStudio.exe"],
    "chatbox": ["Chatbox.exe"],
    "jianying": ["JianyingPro.exe", "Jianying.exe"],
}


def _chromium(base_glob, app, category=CAT_AI, risk="A"):
    """为某个 Chromium userData 根生成标准缓存规则。"""
    rules = []
    for leaf in CHROMIUM_CACHE_LEAVES:
        rules.append({
            "path": base_glob + "\\" + leaf,
            "kind": "dir",
            "category": category,
            "label": f"{app} · {leaf}",
            "risk": risk,
            "action": "quarantine",
            "evidence": f"{app} 的 Chromium 缓存，关闭后可安全清理，应用会自行重建",
            "app": app,
            "guard": PROC_GUARDS.get(app, []),
        })
    return rules


def build_rules():
    """返回静态规则列表（不含动态探测）。"""
    R = []

    # ============ AI 客户端 ============
    # 豆包
    R += _chromium(r"%LOCALAPPDATA%\Doubao\User Data\*", "doubao")
    # 豆包这些目录直接位于 User Data 下（非 profile 子目录）
    for _base in (r"%LOCALAPPDATA%\Doubao\User Data", r"%LOCALAPPDATA%\Doubao\User Data\*"):
        R += [
            {"path": _base + r"\update\update_download", "kind": "dir",
             "category": CAT_UPDATER, "label": "豆包 · 旧版本安装包", "risk": "A", "action": "quarantine",
             "evidence": "旧版本升级包，保留会持续占用空间", "app": "doubao", "guard": PROC_GUARDS["doubao"]},
            {"path": _base + r"\gecko_cache", "kind": "dir",
             "category": CAT_AI, "label": "豆包 · 内嵌浏览器缓存", "risk": "A", "action": "quarantine",
             "evidence": "内嵌浏览器缓存，可安全清理", "app": "doubao"},
            {"path": _base + r"\component_crx_cache", "kind": "dir",
             "category": CAT_AI, "label": "豆包 · 组件缓存", "risk": "A", "action": "quarantine",
             "evidence": "组件安装包缓存", "app": "doubao"},
            {"path": _base + r"\extensions_crx_cache", "kind": "dir",
             "category": CAT_AI, "label": "豆包 · 扩展缓存", "risk": "A", "action": "quarantine",
             "evidence": "扩展安装包缓存", "app": "doubao"},
            {"path": _base + r"\sdk_storage\log", "kind": "dir",
             "category": CAT_AI, "label": "豆包 · 运行日志", "risk": "A", "action": "quarantine",
             "evidence": "运行日志，可能体积很大（数百 MB）且无用", "app": "doubao"},
            {"path": _base + r"\sandbox_runtime", "kind": "dir",
             "category": CAT_AI, "label": "豆包 · 端侧沙箱运行时", "risk": "B", "action": "quarantine",
             "evidence": "端侧沙箱运行环境，删除后豆包会重新下载（约 1GB）", "app": "doubao"},
        ]

    # DeepSeek Harness
    R += _chromium(r"%APPDATA%\@deepseek-ai\dsh-desktop", "deepseek")
    R += [
        {"path": r"%USERPROFILE%\.dsh\cache", "kind": "dir",
         "category": CAT_AI, "label": "DeepSeek · 会话缓存", "risk": "A", "action": "quarantine",
         "evidence": "DeepSeek Harness 的缓存目录", "app": "deepseek"},
        {"path": r"%LOCALAPPDATA%\@deepseek-aidsh-desktop-updater", "kind": "dir",
         "category": CAT_UPDATER, "label": "DeepSeek · 更新包", "risk": "A", "action": "quarantine",
         "evidence": "更新器下载的安装包（installer.exe 与 pending 常重复）", "app": "deepseek"},
    ]

    # ChatGPT / Codex (MSIX)
    for pkg in ["OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0", "OpenAI.Codex_2p2nqsd0c76g0"]:
        R += [
            {"path": rf"%LOCALAPPDATA%\Packages\{pkg}\AC\INetCache", "kind": "dir",
             "category": CAT_AI, "label": "ChatGPT/Codex · 网络缓存", "risk": "A", "action": "quarantine",
             "evidence": "MSIX 应用容器网络缓存", "app": "chatgpt", "guard": PROC_GUARDS["chatgpt"]},
            {"path": rf"%LOCALAPPDATA%\Packages\{pkg}\AC\Temp", "kind": "dir",
             "category": CAT_TEMP, "label": "ChatGPT/Codex · 临时文件", "risk": "A", "action": "quarantine",
             "evidence": "应用容器临时目录", "app": "chatgpt"},
            {"path": rf"%LOCALAPPDATA%\Packages\{pkg}\TempState", "kind": "dir",
             "category": CAT_TEMP, "label": "ChatGPT/Codex · 临时状态", "risk": "A", "action": "quarantine",
             "evidence": "MSIX 临时状态目录", "app": "chatgpt"},
        ]
    R += [
        {"path": r"%LOCALAPPDATA%\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\npm-cache", "kind": "dir",
         "category": CAT_DEV, "label": "Codex · npm 缓存", "risk": "B", "action": "quarantine",
         "evidence": "Codex 沙箱内的 npm 缓存", "app": "chatgpt"},
        {"path": r"%LOCALAPPDATA%\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\pip", "kind": "dir",
         "category": CAT_DEV, "label": "Codex · pip 缓存", "risk": "B", "action": "quarantine",
         "evidence": "Codex 沙箱内的 pip 缓存", "app": "chatgpt"},
    ]

    # Claude (标准版 + 3P 模式) —— 只清已知缓存叶子，绝不整删根目录
    R += _chromium(r"%LOCALAPPDATA%\Claude-Data\claude_*", "claude")
    R += _chromium(r"%LOCALAPPDATA%\Claude-3p", "claude")
    # Claude 虚拟机 / Cowork（用户可能是小白用不到）
    R += [
        {"path": r"%LOCALAPPDATA%\Claude-3p\vm_bundles", "kind": "dir",
         "category": CAT_AI, "label": "Claude · 本地虚拟机镜像(Cowork)", "risk": "C", "action": "prompt",
         "evidence": "Cowork/本地代理的虚拟机磁盘镜像，约 8.8GB；仅在不使用 Cowork 时删除，删后如需用会重新下载",
         "app": "claude", "guard": PROC_GUARDS["claude"]},
        {"path": r"%LOCALAPPDATA%\Claude-3p\claude-code", "kind": "dir",
         "category": CAT_AI, "label": "Claude · Claude Code 引擎", "risk": "B", "action": "quarantine",
         "evidence": "Claude Code 引擎二进制（保留最新版本即可）", "app": "claude"},
        {"path": r"%LOCALAPPDATA%\Claude-3p\claude-code-vm", "kind": "dir",
         "category": CAT_AI, "label": "Claude · Claude Code VM", "risk": "B", "action": "quarantine",
         "evidence": "Claude Code 虚拟机运行文件", "app": "claude"},
    ]

    # Kimi / 千问 / 元宝 / Copilot / Cursor / Chatbox / Cherry / Ollama
    R += _chromium(r"%APPDATA%\kimi-desktop", "kimi")
    R += _chromium(r"%APPDATA%\tongyi", "qianwen")
    R += _chromium(r"%APPDATA%\Cursor", "cursor")
    R += _chromium(r"%APPDATA%\xyz.chatboxapp.app", "chatbox")
    R += _chromium(r"%APPDATA%\CherryStudio", "cherry")
    R += _chromium(r"%APPDATA%\ollama app.exe\EBWebView\Default", "ollama")
    R += [
        {"path": r"%LOCALAPPDATA%\kimi-desktop-updater", "kind": "dir",
         "category": CAT_UPDATER, "label": "Kimi · 更新包", "risk": "A", "action": "quarantine",
         "evidence": "更新包", "app": "kimi"},
        {"path": r"%LOCALAPPDATA%\tongyi-desktop-updater", "kind": "dir",
         "category": CAT_UPDATER, "label": "千问 · 更新包", "risk": "A", "action": "quarantine",
         "evidence": "更新包", "app": "qianwen"},
        {"path": r"%LOCALAPPDATA%\CherryStudio-updater", "kind": "dir",
         "category": CAT_UPDATER, "label": "Cherry Studio · 更新包", "risk": "A", "action": "quarantine",
         "evidence": "更新包", "app": "cherry"},
        {"path": r"%LOCALAPPDATA%\com.tencent.yuanbao", "kind": "dir",
         "category": CAT_AI, "label": "腾讯元宝 · 内嵌浏览器数据", "risk": "B", "action": "quarantine",
         "evidence": "元宝内嵌浏览器缓存（删除后需重新登录）", "app": "yuanbao"},
        {"path": r"%LOCALAPPDATA%\Packages\Microsoft.Copilot_8wekyb3d8bbwe\AC\INetCache", "kind": "dir",
         "category": CAT_AI, "label": "Copilot · 网络缓存", "risk": "A", "action": "quarantine",
         "evidence": "MSIX 网络缓存", "app": "copilot"},
        {"path": r"%LOCALAPPDATA%\Packages\Microsoft.Copilot_8wekyb3d8bbwe\TempState", "kind": "dir",
         "category": CAT_TEMP, "label": "Copilot · 临时状态", "risk": "A", "action": "quarantine",
         "evidence": "MSIX 临时状态", "app": "copilot"},
    ]

    # ============ 剪映 ============
    R += [
        {"path": r"%LOCALAPPDATA%\JianyingPro\User Data\Download", "kind": "dir",
         "category": CAT_UPDATER, "label": "剪映 · 更新包", "risk": "A", "action": "quarantine",
         "evidence": "剪映下载的更新安装包（常数百 MB~1GB）", "app": "jianying", "guard": PROC_GUARDS["jianying"]},
        {"path": r"%LOCALAPPDATA%\JianyingPro\User Data\cache", "kind": "dir",
         "category": CAT_AI, "label": "剪映 · 缓存", "risk": "A", "action": "quarantine",
         "evidence": "剪映运行缓存", "app": "jianying"},
        {"path": r"%LOCALAPPDATA%\JianyingPro\User Data\custom_agent\user-data\remote-skills\.staging-*", "kind": "dir",
         "category": CAT_AI, "label": "剪映 · 旧模型(staging)", "risk": "B", "action": "quarantine",
         "evidence": "技能模型的暂存旧版本，保留 current 即可", "app": "jianying"},
        {"path": r"%LOCALAPPDATA%\JianyingPro\User Data\custom_agent\user-data\remote-skills\next", "kind": "dir",
         "category": CAT_AI, "label": "剪映 · 旧模型(next)", "risk": "B", "action": "quarantine",
         "evidence": "技能模型的旧版本副本", "app": "jianying"},
    ]

    # ============ 浏览器 ============
    edge = r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default"
    chrome = r"%LOCALAPPDATA%\Google\Chrome\User Data\Default"
    for base, name in [(edge, "Edge"), (chrome, "Chrome")]:
        R += [
            {"path": base + r"\Cache", "kind": "dir", "category": CAT_BROWSER,
             "label": f"{name} · 页面缓存", "risk": "A", "action": "quarantine",
             "evidence": "浏览器 HTTP 缓存", "app": name.lower(), "guard": [f"{name.lower()}.exe" if name == "Chrome" else "msedge.exe"]},
            {"path": base + r"\Code Cache", "kind": "dir", "category": CAT_BROWSER,
             "label": f"{name} · 代码缓存", "risk": "A", "action": "quarantine",
             "evidence": "JS/WASM 字节码缓存", "app": name.lower()},
            {"path": base + r"\GPUCache", "kind": "dir", "category": CAT_BROWSER,
             "label": f"{name} · GPU 缓存", "risk": "A", "action": "quarantine",
             "evidence": "GPU 着色器缓存", "app": name.lower()},
            {"path": base + r"\Service Worker\CacheStorage", "kind": "dir", "category": CAT_BROWSER,
             "label": f"{name} · Service Worker 缓存", "risk": "A", "action": "quarantine",
             "evidence": "站点离线资源缓存", "app": name.lower()},
            {"path": base + r"\Service Worker\ScriptCache", "kind": "dir", "category": CAT_BROWSER,
             "label": f"{name} · SW 脚本缓存", "risk": "A", "action": "quarantine",
             "evidence": "SW 脚本字节码缓存", "app": name.lower()},
        ]
    R += [
        {"path": r"%APPDATA%\Mozilla\Firefox\Profiles\*\cache2", "kind": "dir",
         "category": CAT_BROWSER, "label": "Firefox · 缓存", "risk": "A", "action": "quarantine",
         "evidence": "Firefox 磁盘缓存", "app": "firefox", "guard": ["firefox.exe"]},
    ]

    # ============ 系统缓存 ============
    R += [
        {"path": r"%LOCALAPPDATA%\Temp", "kind": "dir", "category": CAT_TEMP,
         "label": "用户临时文件", "risk": "A", "action": "quarantine",
         "evidence": "各程序的临时文件（被占用文件会自动跳过）", "app": "system"},
        {"path": r"C:\Windows\Temp", "kind": "dir", "category": CAT_TEMP,
         "label": "系统临时文件", "risk": "A", "action": "quarantine", "needs_admin": True,
         "evidence": "系统临时目录（需管理员）", "app": "system"},
        {"path": r"C:\Windows\SoftwareDistribution\Download", "kind": "dir",
         "category": CAT_SYS, "label": "Windows 更新下载缓存", "risk": "A", "action": "wu_clean",
         "needs_admin": True,
         "evidence": "已安装更新的下载缓存，可安全清理（会停止并重启更新服务）", "app": "system"},
        {"path": r"%LOCALAPPDATA%\Microsoft\Windows\INetCache", "kind": "dir",
         "category": CAT_SYS, "label": "IE/WinINet 缓存", "risk": "A", "action": "quarantine",
         "evidence": "系统网络缓存", "app": "system"},
        {"path": r"%LOCALAPPDATA%\Microsoft\Windows\Explorer\thumbcache_*", "kind": "dir",
         "category": CAT_SYS, "label": "缩略图缓存", "risk": "A", "action": "quarantine",
         "evidence": "资源管理器缩略图缓存", "app": "system"},
        {"path": r"%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*", "kind": "dir",
         "category": CAT_SYS, "label": "图标缓存", "risk": "A", "action": "quarantine",
         "evidence": "资源管理器图标缓存", "app": "system"},
        {"path": r"%LOCALAPPDATA%\CrashDumps", "kind": "dir", "category": CAT_SYS,
         "label": "崩溃转储", "risk": "A", "action": "quarantine",
         "evidence": "程序崩溃产生的 .dmp 转储", "app": "system"},
        {"path": r"%LOCALAPPDATA%\D3DSCache", "kind": "dir", "category": CAT_SYS,
         "label": "Direct3D 着色器缓存", "risk": "A", "action": "quarantine",
         "evidence": "D3D 着色器缓存，可安全重建", "app": "system"},
        {"path": r"%LOCALAPPDATA%\NVIDIA\DXCache", "kind": "dir", "category": CAT_SYS,
         "label": "NVIDIA DX 缓存", "risk": "A", "action": "quarantine",
         "evidence": "显卡着色器缓存", "app": "nvidia"},
        {"path": r"%LOCALAPPDATA%\NVIDIA\GLCache", "kind": "dir", "category": CAT_SYS,
         "label": "NVIDIA GL 缓存", "risk": "A", "action": "quarantine",
         "evidence": "显卡着色器缓存", "app": "nvidia"},
    ]

    # ============ 开发缓存 ============
    R += [
        {"path": r"%LOCALAPPDATA%\npm-cache", "kind": "dir", "category": CAT_DEV,
         "label": "npm 缓存", "risk": "A", "action": "quarantine", "evidence": "npm 下载缓存", "app": "dev"},
        {"path": r"%LOCALAPPDATA%\pip\Cache", "kind": "dir", "category": CAT_DEV,
         "label": "pip 缓存", "risk": "A", "action": "quarantine", "evidence": "pip 下载缓存", "app": "dev"},
        {"path": r"%LOCALAPPDATA%\Yarn\Cache", "kind": "dir", "category": CAT_DEV,
         "label": "Yarn 缓存", "risk": "A", "action": "quarantine", "evidence": "Yarn 下载缓存", "app": "dev"},
        {"path": r"%LOCALAPPDATA%\pnpm\store", "kind": "dir", "category": CAT_DEV,
         "label": "pnpm 缓存", "risk": "B", "action": "quarantine", "evidence": "pnpm 内容寻址存储", "app": "dev"},
        {"path": r"%USERPROFILE%\.nuget\packages", "kind": "dir", "category": CAT_DEV,
         "label": "NuGet 缓存", "risk": "B", "action": "quarantine", "evidence": "NuGet 包缓存", "app": "dev"},
        {"path": r"%USERPROFILE%\.gradle\caches", "kind": "dir", "category": CAT_DEV,
         "label": "Gradle 缓存", "risk": "B", "action": "quarantine", "evidence": "Gradle 依赖缓存", "app": "dev"},
        {"path": r"%USERPROFILE%\.m2\repository", "kind": "dir", "category": CAT_DEV,
         "label": "Maven 本地仓库", "risk": "B", "action": "quarantine", "evidence": "Maven 依赖（删除需重新下载）", "app": "dev"},
        {"path": r"%USERPROFILE%\.cargo\registry", "kind": "dir", "category": CAT_DEV,
         "label": "Cargo 缓存", "risk": "B", "action": "quarantine", "evidence": "Rust 依赖缓存", "app": "dev"},
        {"path": r"%USERPROFILE%\go\pkg\mod", "kind": "dir", "category": CAT_DEV,
         "label": "Go module 缓存", "risk": "B", "action": "quarantine", "evidence": "Go 依赖缓存", "app": "dev"},
        {"path": r"%LOCALAPPDATA%\ms-playwright", "kind": "dir", "category": CAT_DEV,
         "label": "Playwright 浏览器", "risk": "B", "action": "quarantine", "evidence": "Playwright 下载的浏览器", "app": "dev"},
    ]

    return R


# ---- 动态探测：通用更新器目录（名字含 -updater / updater）----
UPDATER_NAME_RE = r"(?i)(updater|update)"  # 用于 filter

# ---- 动态探测：版本化目录（app-1.2.3 样式，保留最新）----
def detect_versioned_dirs(base: str, prefix_re: str, app: str, category=CAT_AI, risk="B"):
    """在 base 下找形如 <prefix>-<版本> 的目录，返回除最新外的规则列表。"""
    import os
    import re
    base = __import__("pcclean.config", fromlist=["expand_env"]).expand_env(base)
    if not os.path.isdir(base):
        return []
    rx = re.compile(prefix_re, re.IGNORECASE)
    entries = []
    try:
        for name in os.listdir(base):
            if rx.match(name):
                entries.append(os.path.join(base, name))
    except OSError:
        return []
    if len(entries) <= 1:
        return []
    entries.sort()
    old = entries[:-1]  # 保留字典序最后一个（通常是最高版本）
    rules = []
    for p in old:
        rules.append({
            "path": p, "kind": "dir", "category": category,
            "label": f"{app} · 旧版本 {os.path.basename(p)}", "risk": risk,
            "action": "quarantine", "evidence": "旧版本二进制，保留最新版即可",
            "app": app, "guard": PROC_GUARDS.get(app, []),
        })
    return rules
