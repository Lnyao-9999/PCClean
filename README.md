# 全能磁盘清理专家（PCClean）

![CI](https://github.com/Lnyao-9999/PCClean/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%20x64-blue)
![Python](https://img.shields.io/badge/python-3.10%2B%20(stdlib%20only)-blue)

面向普通用户的 Windows 磁盘/系统清理工具，中文界面。**纯 Python 标准库实现，零第三方依赖**；内置便携运行时，安装包双击即用，无需先装 Python。

**四大模块：磁盘清理 / 软件卸载 / 内存优化 / 空间分析**

---

## 功能总览

| 模块 | 能做什么 |
|---|---|
| **① 磁盘清理** | 系统缓存、临时文件、浏览器缓存、开发缓存、更新包残留、**AI 客户端缓存**（豆包/DeepSeek/ChatGPT/Claude/Codex/Kimi/千问/元宝/Copilot/Cursor…）、**NVIDIA 旧驱动**、**Claude 虚拟机镜像**、**微信/QQ/剪映数据迁移**、默认存储位置教程 |
| **② 软件卸载** | 枚举全部已装软件（含 64/32 位、每用户、UWP），调用自带卸载器 → 验证 → 深度扫描**文件 + 注册表残留** → 备份后清理；支持强制移除损坏的卸载 |
| **③ 内存优化** | 实时内存占用、一键加速（后台工作集让位 + 刷新 DNS）、游戏模式、高级清空备用内存（诚实提示：内存优化作用常被高估） |
| **④ 空间分析** | **任意盘符**的大文件查找（阈值可选）与**重复文件**查找（只保留一份），补齐 C 盘之外的清理/迁移需求 |

---

## 一、安装与启动

### 方式一（推荐）：安装包
1. 到 [Releases](https://github.com/Lnyao-9999/PCClean/releases) 下载 `PCClean_Setup.exe`；
2. 双击 → UAC 选"是" → 自动装到 `C:\Program Files\PCClean`，创建桌面/开始菜单快捷方式；
3. 卸载：`设置 → 应用 → 已安装的应用 → 全能磁盘清理专家 → 卸载`。

> 安装包**已内置便携 Python 运行时**，目标电脑无需安装 Python；支持静默安装：
> `PCClean_Setup.exe /silent /target="D:\Apps\PCClean"`

### 方式二：绿色便携
发行版里的 `PCClean` 文件夹直接拷走，双击 `PCClean.exe` 即可（自动申请管理员）。

### 方式三：从源码运行
```bash
python main.py          # 需要 Python 3.10+（含 tkinter）
```
或双击 `run.bat`（优先使用 `python\` 下的便携运行时）/ `run-debug.bat`（带控制台，便于排错）。

---

## 二、① 磁盘清理（重点 C 盘）

1. 点 **「开始扫描」**，列表按体积从大到小显示可清理项；
2. 选择**清理方式**：
   - **直接删除（推荐）**：真正释放磁盘空间，删除不可恢复；
   - **移入隔离区**：仅把文件挪到 C 盘内的隔离区（**不释放空间**，但可回滚）；
3. 单击行勾选/取消，或点「全选安全项(A)」；
4. 点「开始清理」→ 完成后列表**立即移除已清理项**，并弹窗显示「C 盘实际释放」。

**风险分级**：A·安全（默认勾选）/ B·建议 / C·需确认 / D·禁止。

**体验细节**
- 相关程序正在运行时，该项目**标红提示「⚠ 程序运行中」**；点清理时会询问是否**自动结束这些程序**再清理（否则缓存删不掉、下次还会出现）。
- 被跳过的项目会弹出**「跳过详情」**，逐项给出「原因 + 解决办法」。
- 顶部显示**「上次清理」**记录（时间/成功/跳过），并说明"缓存会随程序使用自动重生属正常"。
- 通配符规则（如缩略图/图标缓存）**自动合并成一行**（「共 N 项」），并默认隐藏 <0.1MB 的极小项（工具栏可显示）。

**专项功能**
- **NVIDIA 旧驱动清理**：只删除当前未使用的旧 oem 驱动包（`pnputil /delete-driver`，不带 `/force`），保护当前驱动；可先创建还原点；同时清理 `C:\NVIDIA` 等安装缓存。
- **Claude 虚拟机**：`Claude-3p\vm_bundles`（约 8.6GB，C 级）单独列出，确认不用 Cowork 才删。
- **微信/QQ/剪映迁移**：勾选 → 选目标盘 → 一键迁移（复制 → 改名备份 → 目录联接 → 验证，不删数据）。
- **改默认存储位置**：逐条教程，从根上防止 C 盘被占满。

**隔离区**
- 位置：`%LOCALAPPDATA%\PCClean\Quarantine`，顶部「隔离区管理」可打开、恢复、彻底删除或**清空全部（释放空间）**。

---

## 三、② 软件卸载

- **刷新列表**：枚举所有已装软件，自动过滤系统组件/补丁/运行库。
- **卸载**：调自带卸载程序 → 等待 → 验证注册表键是否消失。
- **卸载并清理残留**：深度扫描文件（安装目录、AppData、ProgramData、开始菜单、桌面快捷方式）+ 注册表（厂商键、App Paths、Run 等），弹清单确认后清理（文件进隔离区、注册表先备份 `.reg`）。
- **强制移除**：针对卸载程序损坏/卸载失败的情况。
- **导出列表**：CSV。

---

## 四、③ 内存优化（诚实版）

- 实时显示物理内存总量/已用/可用/占用率；
- **一键加速**：刷新 DNS + 让后台程序工作集让位（不真删数据）；
- **开启游戏模式**；高级选项可清空备用内存（需管理员）；
- 明确不做「清注册表」「关虚拟内存」这类有害操作。

---

## 五、④ 空间分析（所有盘符）

- 选择任意固定磁盘（自动显示剩余/总容量）；
- **分析大文件**：按阈值（100MB ~ 5GB）扫描，列出最大的文件，可勾选删除；
- **查找重复文件**：只比较 ≥10MB 的文件（先按体积分组，再头部哈希、再全量哈希，避免全盘哈希），按组列出，可「每组保留一份，删除其余」；
- 支持「停止」；系统受保护目录（WinSxS、DriverStore 等）自动跳过。

---

## 六、安全设计

- **隔离区 + 可回滚**：默认模式为直接删除前明确确认；隔离区模式可 30 天内恢复；
- **硬保护名单**：`System32 / WinSxS / Installer / Program Files / 用户文档/桌面/图片/下载` 等绝不自动删；
- **不跟随 junction/符号链接**，OneDrive 云端占位文件跳过，应用运行中不清理；
- **操作日志**：`%LOCALAPPDATA%\PCClean\History`；注册表清理前自动 `reg export` 备份；
- **无网络、无遥测**：不联网、不上传任何文件或路径。

---

## 七、项目结构

```
PCClean/
├─ main.py                  # 入口（自动提权）
├─ PCClean.exe              # 启动器（自动管理员，优先用便携运行时）
├─ run.bat / run-debug.bat
├─ install.bat / uninstall.bat
├─ app.manifest / launcher.cs
├─ installer/               # 单文件安装包构建源码
│  ├─ Setup.cs  Uninstall.cs
│  ├─ setup.manifest  uninstall.manifest  setup_asinvoker.manifest
│  └─ build_setup.ps1
├─ pcclean/
│  ├─ config.py
│  ├─ utils/   winapi.py(ctypes)  registry.py(winreg)
│  ├─ engine/  scanner / rules / safety / executor / drivers / migrate / uninstall / ram / space
│  └─ ui/      app.py（tkinter，高 DPI 适配）
├─ smoke_test.py  collect_test.py  launch_test.py  executor_test.py  dialog_test.py  space_test.py
└─ README.md  CHANGELOG.md  LICENSE
```

---

## 八、开发与构建

环境：Windows 10/11 x64，Python 3.10+（标准库，无 pip 依赖）。

```bat
rem 直接运行
python main.py

rem 自检
python smoke_test.py
python collect_test.py
python space_test.py

rem 生成单文件安装包（需系统自带 csc.exe）
powershell -ExecutionPolicy Bypass -File installer\build_setup.ps1
```

安装包构建原理：把程序目录（含便携 Python 运行时）打成 zip 内嵌进 C# 安装器，安装时用系统 `tar.exe` 解压，然后建快捷方式与卸载登记。

---

## 九、常见问题

- **清理后 C 盘没变？** → 检查清理方式是否选了「移入隔离区」；隔离区模式不释放空间，选「直接删除」或到「隔离区管理 → 清空全部」。
- **某些项每次扫描都在？** → 多为程序正在运行（列表已标红），或缓存随使用自动重建。清理时选「自动结束相关程序」即可清掉。
- **隔离区在哪？** → `%LOCALAPPDATA%\PCClean\Quarantine`。
- **UWP 应用没列出来？** → 极少数受限环境下 `Get-AppxPackage` 会被拒；正常桌面双击运行即可。
- **大文件/重复文件扫描慢？** → 全盘遍历耗时正常；可点「停止」，或换更小的范围/阈值。

---

## 十、更新记录

见 [CHANGELOG.md](CHANGELOG.md)。当前版本 **v1.3.0**。

---

## 十一、License

[MIT](LICENSE) © 2026 Lnyao-9999
