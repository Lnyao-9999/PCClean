@echo off
rem 调试启动：带控制台窗口，能看到报错信息；优先使用自带便携 Python
cd /d "%~dp0"
if exist "%~dp0python\python.exe" (
    "%~dp0python\python.exe" "%~dp0main.py"
) else (
    python "%~dp0main.py"
)
pause
