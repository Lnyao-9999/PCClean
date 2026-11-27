# GitHub Actions CI

本项目 CI **已启用**，配置位于 `.github/workflows/ci.yml`，每次 push / PR 自动运行：

- **Byte-compile**：对 `pcclean/` 全量字节码编译
- **Import check**：导入 UI 与全部引擎模块（含 tkinter）
- **Space analysis smoke test**：运行 `space_test.py`（盘符枚举 / 大文件 / 重复文件）

运行记录：https://github.com/Lnyao-9999/PCClean/actions

当前配置内容（如需修改，直接编辑该文件并提交）：

```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Byte-compile all sources
        run: python -m compileall -q pcclean

      - name: Import check (UI + engines)
        run: python -c "import sys; sys.path.insert(0,'.'); import pcclean.ui.app; from pcclean.engine import scanner, rules, safety, executor, drivers, migrate, uninstall, ram, space; print('import ok')"

      - name: Space analysis smoke test
        run: python space_test.py
```
