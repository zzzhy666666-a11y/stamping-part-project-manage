@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: 定义源文件和备份目录
set "SRC=projects.json"
set "BACKUP_DIR=backups"

:: 进入当前脚本所在目录（保证U盘路径没问题）
cd /d "%~dp0"

:: 判断源文件是否存在
if not exist "%SRC%" (
    echo ? 找不到 projects.json，无法备份！
    pause
    exit /b 1
)

:: 建立备份文件夹（不存在就创建）
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

:: 生成时间戳：yyyyMMdd_HHmmss
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do set D=%%c%%a%%b
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set T=%%a%%b
set "TS=%D%_%T%"

:: 备份文件名
set "DEST=%BACKUP_DIR%\projects_%TS%.json"

:: 执行复制
copy "%SRC%" "%DEST%" >nul
if !errorlevel! equ 0 (
    echo ? 备份成功：
    echo    !DEST!
) else (
    echo ? 备份失败！
)

pause