# 启用 GitHub Actions CI

本项目的 CI 配置见下方。由于通过 GitHub API 创建 `.github/workflows/` 下的文件需要令牌具备 **`workflow`** 权限（当前自动上传使用的令牌只有 `repo` 权限，所以该文件未自动推送），请手动添加一次（约 30 秒）：

1. 打开仓库首页 → **Add file** → **Create new file**
2. 文件名填写：`.github/workflows/ci.yml`
3. 粘贴下面内容 → **Commit changes**

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

提交后，每次 push 都会在 Actions 页自动跑「编译 + 导入检查 + 空间分析自检」，README 顶部的 CI 徽章也会变成通过状态。
