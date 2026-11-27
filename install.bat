@echo off
chcp 65001 >nul
rem ============================================================
rem  安装到本机：复制到 本用户程序目录 + 创建桌面/开始菜单快捷方式
rem  （纯绿色，不写注册表、不附带任何捆绑）
rem ============================================================
setlocal
set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\Programs\PCClean"
echo 正在安装到：%DEST%
if not exist "%DEST%" mkdir "%DEST%"
robocopy "%SRC%." "%DEST%" /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ build dist >nul
if errorlevel 8 (
    echo 复制失败，请以管理员身份重试，或手动复制文件夹。
    pause
    exit /b 1
)
echo 正在创建快捷方式…
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ws=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $s=$ws.CreateShortcut((Join-Path $d 'PCClean 全能磁盘清理.lnk')); $s.TargetPath='%DEST%\PCClean.exe'; $s.WorkingDirectory='%DEST%'; $s.Save(); $sm=[Environment]::GetFolderPath('StartMenu')+'\Programs\PCClean 全能磁盘清理.lnk'; $s2=$ws.CreateShortcut($sm); $s2.TargetPath='%DEST%\PCClean.exe'; $s2.WorkingDirectory='%DEST%'; $s2.Save()"
echo.
echo 安装完成！桌面和开始菜单已创建「PCClean 全能磁盘清理」快捷方式。
echo 双击它会自动申请管理员权限并启动。
pause
