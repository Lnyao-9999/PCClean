@echo off
chcp 65001 >nul
rem ============================================================
rem  卸载：删除已安装目录与快捷方式（不会删除隔离区数据）
rem ============================================================
setlocal
set "DEST=%LOCALAPPDATA%\Programs\PCClean"
echo 正在删除安装目录：%DEST%
if exist "%DEST%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath '%DEST%' -Recurse -Force -ErrorAction SilentlyContinue"
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ws=New-Object -ComObject WScript.Shell; foreach($p in @([Environment]::GetFolderPath('Desktop')+'\PCClean 全能磁盘清理.lnk', [Environment]::GetFolderPath('StartMenu')+'\Programs\PCClean 全能磁盘清理.lnk')){ if(Test-Path $p){ Remove-Item $p -Force } }"
echo.
echo 已卸载。隔离区数据位于 %LOCALAPPDATA%\PCClean，如不需要可手动删除。
pause
