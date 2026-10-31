@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".runtime\python\python.exe" (
 if not exist ".runtime" mkdir ".runtime"
 tar -xzf "assets\runtimes\windows-x64.tar.gz" -C ".runtime"
 if errorlevel 1 exit /b 1
)
".runtime\python\python.exe" -I -X utf8 "scripts\launch.py" %*
if errorlevel 1 pause
