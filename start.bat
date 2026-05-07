@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title 易Agent 一键启动

echo ============================================
echo       易Agent 启动程序 v1.4
echo ============================================
echo.

:: ═══ 1. 检测 Python ═══
python --version >nul 2>&1
if %errorlevel% neq 0 (
    python3 --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo [错误] 未检测到 Python，请安装 Python 3.10+ 并添加到 PATH
        echo        下载地址: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)
echo [√] Python 环境正常

:: ═══ 2. 创建虚拟环境（如不存在） ═══
if not exist "venv\Scripts\activate.bat" (
    echo [初始化] 正在创建虚拟环境...
    %PYTHON% -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [√] 虚拟环境创建完成
)

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: ═══ 3. 国内镜像加速 ═══
set PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
set PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
echo [√] 使用清华大学 pip 镜像

:: ═══ 4. 安装/更新依赖（跳过已安装） ═══
if exist "requirements.txt" (
    :: 用 Python 检查所有依赖是否已满足，满足则跳过
    %PYTHON% -c "import importlib,sys;MAP={'python-dotenv':'dotenv'};[importlib.import_module(MAP.get((p:=l.strip().split('>=')[0].split('==')[0].split('[')[0]),p.replace('-','_'))) for l in open('requirements.txt') if l.strip() and not l.startswith('#')]" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [√] 依赖已安装，跳过
    ) else (
        echo [检查] 正在安装/更新依赖...
        pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
        if !errorlevel! neq 0 (
            echo [警告] 部分依赖安装失败，尝试逐个安装...
            for /f "tokens=1" %%p in (requirements.txt) do (
                pip install %%p --quiet --disable-pip-version-check 2>nul
            )
        )
        echo [√] 依赖就绪
    )
) else (
    echo [跳过] 未找到 requirements.txt
)

:: ═══ 5. 自动创建 .env（如不存在） ═══
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [√] 已从 .env.example 创建 .env 配置文件
    ) else (
        (
            echo # 易Agent 配置文件
            echo # 填入你的 API Key（必填）
            echo LLM_API_KEY=your-api-key-here
            echo LLM_BASE_URL=https://api.deepseek.com
            echo LLM_MODEL=deepseek-chat
            echo.
            echo # Ollama 本地模型（可选）
            echo OLLAMA_ENABLED=false
            echo OLLAMA_BASE_URL=http://localhost:11434/v1
            echo OLLAMA_MODEL=qwen2.5:7b
        ) > .env
        echo [√] 已创建默认 .env 配置文件
        echo [!] 请编辑 .env 填入你的 LLM_API_KEY
    )
)

:: ═══ 6. 选择启动模式 ═══
echo.
echo ============================================
echo   请选择启动界面:
echo     1. Web 界面（Flask + HTML，推荐）
echo     2. CLI 命令行模式
echo     3. Streamlit 管理界面
echo     0. 退出
echo ============================================
set /p choice=请输入数字 (0-3): 

if "%choice%"=="1" goto web
if "%choice%"=="2" goto cli
if "%choice%"=="3" goto streamlit
if "%choice%"=="0" goto quit
echo 无效选择，默认启动 Web 界面
goto web

:web
echo.
echo [启动] Web 界面...
echo [地址] http://localhost:8080
echo [提示] 浏览器将自动打开，按 Ctrl+C 停止服务
echo.
start "" "http://localhost:8080"
python server.py --port 8080
goto end

:cli
echo.
echo [启动] CLI 命令行模式...
echo.
python main.py
goto end

:streamlit
echo.
echo [启动] Streamlit 管理界面...
echo [地址] http://localhost:8501
echo.
streamlit run app.py --server.port 8501
goto end

:quit
echo 已退出
exit /b 0

:end
echo.
echo 服务已停止
pause
