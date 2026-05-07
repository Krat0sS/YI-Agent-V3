@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM 查找 Python 并启动
py -3.12 启动.py 2>nul || py -3.13 启动.py 2>nul || py -3.14 启动.py 2>nul || py -3 启动.py 2>nul || python 启动.py 2>nul || python3 启动.py 2>nul || (
    echo.
    echo   [错误] 未检测到 Python！
    echo   请安装 Python 3.12: https://www.python.org/downloads/
    echo   安装时请勾选 "Add Python to PATH"！
    echo.
    pause
)
