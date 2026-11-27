@echo off
rem ============================================================
rem  全能磁盘清理专家 PCClean —— 启动脚本
rem  优先使用软件自带的便携 Python（python\pythonw.exe），无需系统安装 Python
rem ============================================================
cd /d "%~dp0"
if exist "%~dp0python\pythonw.exe" (
    "%~dp0python\pythonw.exe" "%~dp0main.py"
    exit /b
)
set "PY=python"
where pythonw >nul 2>nul && set "PY=pythonw"
"%PY%" "%~dp0main.py"
