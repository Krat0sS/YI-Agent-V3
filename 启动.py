# -*- coding: utf-8 -*-
"""
YI-Agent V4 启动器 — 替代启动.bat，避免 Windows bat 的 errorlevel 坑
"""
import os
import sys
import subprocess
import shutil
import venv
from pathlib import Path

# ── 配置 ──
PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / "venv"
REQUIREMENTS = PROJECT_DIR / "requirements.txt"
ENV_FILE = PROJECT_DIR / ".env"
ENV_EXAMPLE = PROJECT_DIR / ".env.example"

# 优先选择的 Python 版本
PREFERRED_VERSIONS = ["3.12", "3.11", "3.13", "3.10"]

# pip 镜像源（国内加速）
PIP_MIRRORS = [
    ("https://mirrors.aliyun.com/pypi/simple/", "mirrors.aliyun.com"),
    ("https://pypi.tuna.tsinghua.edu.cn/simple/", "pypi.tuna.tsinghua.edu.cn"),
]


def banner():
    print()
    print("  ========================================")
    print("         YI-Agent v4.0 启动程序")
    print("  ========================================")
    print()


def find_python():
    """查找系统中最好的 Python"""
    # 优先 py launcher
    for ver in PREFERRED_VERSIONS:
        try:
            r = subprocess.run(
                ["py", f"-{ver}", "--version"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                ver_str = r.stdout.strip().split()[-1] if r.stdout else ver
                print(f"  [√] Python: py -{ver} ({ver_str})")
                return ["py", f"-{ver}"], ver_str
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # fallback: python / python3
    for cmd in ["python", "python3"]:
        try:
            r = subprocess.run(
                [cmd, "--version"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                ver_str = r.stdout.strip().split()[-1]
                print(f"  [√] Python: {cmd} ({ver_str})")
                return [cmd], ver_str
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return None, None


def get_venv_python():
    """获取 venv 中的 Python 路径"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def get_venv_pip():
    """获取 venv 中的 pip 路径"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def venv_python():
    """用 venv 的 Python 执行命令，返回 CompletedProcess"""
    py = get_venv_python()
    def run(args, **kwargs):
        return subprocess.run([str(py)] + args, **kwargs)
    return run


def check_venv_version(python_cmd):
    """检查 venv 的 Python 版本是否与系统匹配"""
    py = get_venv_python()
    if not py.exists():
        return False
    try:
        # 获取 venv 版本
        r = subprocess.run([str(py), "--version"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return False
        venv_ver = r.stdout.strip().split()[-1]
        venv_major_minor = ".".join(venv_ver.split(".")[:2])
        print(f"  [i] 已有虚拟环境: Python {venv_ver}")

        # 获取系统 Python 版本
        r2 = subprocess.run(python_cmd + ["--version"], capture_output=True, text=True, timeout=5)
        if r2.returncode != 0:
            return True  # 无法检测系统版本，保留现有 venv
        sys_ver = r2.stdout.strip().split()[-1]
        sys_major_minor = ".".join(sys_ver.split(".")[:2])

        # 主版本号必须匹配（3.12 vs 3.14 不兼容）
        if venv_major_minor != sys_major_minor:
            print(f"  [!] venv 版本 ({venv_major_minor}) 与系统 ({sys_major_minor}) 不匹配，需重建")
            return False
        return True
    except Exception:
        return False


def create_venv(python_cmd, ver_str):
    """创建虚拟环境"""
    print(f"  [1/4] 创建虚拟环境 (Python {ver_str}) ...")
    try:
        venv.create(str(VENV_DIR), with_pip=True)
        print("  [√] 虚拟环境创建完成")
        print()
        return True
    except Exception as e:
        print(f"\n  [错误] 虚拟环境创建失败: {e}")
        return False


def upgrade_pip():
    """升级 pip（使用国内镜像，失败不阻塞）"""
    py = get_venv_python()
    for url, host in PIP_MIRRORS:
        try:
            r = subprocess.run(
                [str(py), "-m", "pip", "install", "--upgrade", "pip",
                 "-i", url, "--trusted-host", host, "--quiet", "--no-cache-dir"],
                capture_output=True, timeout=30
            )
            if r.returncode == 0:
                return
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue
    # 所有镜像都失败，跳过（不影响后续安装）
    print("  [!] pip 升级跳过（网络问题，不影响使用）")


def check_deps():
    """检查核心依赖是否已安装"""
    py = get_venv_python()
    try:
        r = subprocess.run(
            [str(py), "-c", "import flask, openai, dotenv, git"],
            capture_output=True, shell=True, text=True, timeout=10
        )
        return r.returncode == 0
    except Exception:
        return False


def install_deps():
    """安装依赖"""
    py = get_venv_python()
    pip = get_venv_pip()

    print("  [2/4] 安装依赖（首次需要 1-2 分钟） ...")
    print()

    for url, host in PIP_MIRRORS:
        print(f"  [i] 使用镜像: {host} ...")
        try:
            r = subprocess.run(
                [str(pip), "install", "-r", str(REQUIREMENTS),
                 "--no-cache-dir", "-i", url, "--trusted-host", host,
                 "--timeout", "30"],
                cwd=str(PROJECT_DIR),
                timeout=300
            )
            if r.returncode == 0:
                print()
                print("  [√] 依赖安装完成")
                return True
        except subprocess.TimeoutExpired:
            print(f"\n  [!] {host} 超时，尝试下一个镜像 ...")
        except Exception as e:
            print(f"\n  [!] {host} 失败: {e}")
        print(f"\n  [!] {host} 失败，尝试下一个镜像 ...")

    # 最后尝试默认源
    print("  [i] 尝试默认源 ...")
    try:
        r = subprocess.run(
            [str(pip), "install", "-r", str(REQUIREMENTS), "--no-cache-dir"],
            cwd=str(PROJECT_DIR),
            timeout=300
        )
        if r.returncode == 0:
            print("  [√] 依赖安装完成")
            return True
    except Exception:
        pass

    print("\n  [错误] 依赖安装失败，请检查网络连接")
    print("  手动安装: pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/")
    return False


def fix_core_packages():
    """修复核心包"""
    py = get_venv_python()
    pip = get_venv_pip()

    print("  [!] 核心包导入失败，尝试重新安装 ...")
    print()

    for url, host in PIP_MIRRORS:
        try:
            r = subprocess.run(
                [str(pip), "install", "flask", "openai", "python-dotenv", "gitpython",
                 "--no-cache-dir", "-i", url, "--trusted-host", host],
                timeout=120
            )
            if r.returncode == 0:
                break
        except Exception:
            continue

    # 验证
    r = subprocess.run(
        [str(py), "-c", "import flask, openai, dotenv"],
        capture_output=True, text=True, timeout=10
    )
    if r.returncode == 0:
        print("  [√] 核心包修复成功")
        return True

    print(f"  [错误] 核心包安装失败，请手动执行:\n    {py} -m pip install -r requirements.txt")
    return False


def create_env():
    """创建 .env 配置文件"""
    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        shutil.copy(str(ENV_EXAMPLE), str(ENV_FILE))
        print("  [√] 已创建 .env 配置文件")


def check_ollama():
    """检查 Ollama"""
    try:
        r = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True, timeout=3
        )
        if r.returncode == 0:
            print("  [√] 检测到 Ollama — 本地模型可用")
        else:
            print("  [i] Ollama 未运行 — 将使用云端模型")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [i] Ollama 未运行 — 将使用云端模型")


def check_playwright():
    """检查并安装 Playwright 浏览器自动化"""
    py = get_venv_python()

    # 1. 检查 playwright Python 包
    try:
        r = subprocess.run(
            [str(py), "-c", "import playwright"],
            capture_output=True, timeout=10
        )
        if r.returncode == 0:
            print("  [√] Playwright 已安装")
        else:
            raise ImportError
    except (ImportError, Exception):
        print("  [3/4] 安装 Playwright ...")
        for url, host in PIP_MIRRORS:
            try:
                r = subprocess.run(
                    [str(py), "-m", "pip", "install", "playwright",
                     "-i", url, "--trusted-host", host, "--quiet", "--no-cache-dir"],
                    capture_output=True, timeout=120
                )
                if r.returncode == 0:
                    print("  [√] Playwright 安装完成")
                    break
            except Exception:
                continue
        else:
            # 尝试默认源
            try:
                r = subprocess.run(
                    [str(py), "-m", "pip", "install", "playwright", "--quiet"],
                    capture_output=True, timeout=120
                )
                if r.returncode == 0:
                    print("  [√] Playwright 安装完成")
                else:
                    print("  [!] Playwright 安装失败，浏览器工具不可用")
                    print("      手动安装: pip install playwright && playwright install chromium")
                    return False
            except Exception:
                print("  [!] Playwright 安装失败，浏览器工具不可用")
                return False

    # 2. 检查 Chromium 浏览器
    print("  [3/4] 检查 Chromium 浏览器 ...")
    try:
        r = subprocess.run(
            [str(py), "-m", "playwright", "install", "--dry-run"],
            capture_output=True, text=True, timeout=10
        )
        # 如果 dry-run 输出包含 chromium 且没有报错，说明已安装
        if "chromium" not in r.stdout.lower() and r.returncode != 0:
            raise Exception("未安装")
        print("  [√] Chromium 浏览器已就绪")
    except Exception:
        print("  [i] 正在下载 Chromium 浏览器（首次需要几分钟）...")
        try:
            r = subprocess.run(
                [str(py), "-m", "playwright", "install", "chromium"],
                capture_output=True, timeout=300
            )
            if r.returncode == 0:
                print("  [√] Chromium 下载完成")
            else:
                print("  [!] Chromium 下载失败，首次使用浏览器工具时会自动下载")
        except subprocess.TimeoutExpired:
            print("  [!] Chromium 下载超时，请手动运行: playwright install chromium")
        except Exception as e:
            print(f"  [!] Chromium 下载失败: {e}")
            print("      手动运行: playwright install chromium")

    return True


def check_gitpython():
    """检查 GitPython 是否已安装（Git 工具依赖）"""
    py = get_venv_python()
    try:
        r = subprocess.run(
            [str(py), "-c", "import git"],
            capture_output=True, timeout=10
        )
        if r.returncode == 0:
            print("  [√] GitPython 已安装 — Git 工具可用")
            return True
    except Exception:
        pass

    print("  [i] 安装 GitPython ...")
    pip = get_venv_pip()
    for url, host in PIP_MIRRORS:
        try:
            r = subprocess.run(
                [str(pip), "install", "gitpython",
                 "-i", url, "--trusted-host", host, "--quiet", "--no-cache-dir"],
                capture_output=True, timeout=60
            )
            if r.returncode == 0:
                print("  [√] GitPython 安装完成")
                return True
        except Exception:
            continue

    # 默认源兜底
    try:
        r = subprocess.run(
            [str(pip), "install", "gitpython", "--quiet"],
            capture_output=True, timeout=60
        )
        if r.returncode == 0:
            print("  [√] GitPython 安装完成")
            return True
    except Exception:
        pass

    print("  [!] GitPython 安装失败，Git 工具不可用")
    print("      手动安装: pip install gitpython")
    return False


def check_pytest():
    """检查 pytest 是否已安装（测试门禁依赖）"""
    py = get_venv_python()
    try:
        r = subprocess.run(
            [str(py), "-m", "pytest", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            ver = r.stdout.strip().split("\n")[0] if r.stdout else ""
            print(f"  [√] pytest 已安装 — {ver}")
            return True
    except Exception:
        pass

    print("  [i] 安装 pytest ...")
    pip = get_venv_pip()
    for url, host in PIP_MIRRORS:
        try:
            r = subprocess.run(
                [str(pip), "install", "pytest",
                 "-i", url, "--trusted-host", host, "--quiet", "--no-cache-dir"],
                capture_output=True, timeout=60
            )
            if r.returncode == 0:
                print("  [√] pytest 安装完成")
                return True
        except Exception:
            continue

    # 默认源兜底
    try:
        r = subprocess.run(
            [str(pip), "install", "pytest", "--quiet"],
            capture_output=True, timeout=60
        )
        if r.returncode == 0:
            print("  [√] pytest 安装完成")
            return True
    except Exception:
        pass

    print("  [!] pytest 安装失败，测试门禁不可用")
    print("      手动安装: pip install pytest")
    return False


def check_server():
    """检查 server.py"""
    if not (PROJECT_DIR / "server.py").exists():
        print("  [错误] 未找到 server.py，请确认在正确的目录下")
        return False
    return True


def menu():
    """显示菜单并返回选择"""
    print()
    print("  ========================================")
    print("         请选择启动模式")
    print("  ========================================")
    print("    1. Web 界面（浏览器，推荐）")
    print("    2. 命令行模式（终端交互）")
    print("    3. Streamlit 管理台")
    print("    0. 退出")
    print("  ========================================")
    print()

    while True:
        try:
            choice = input("  请输入数字 (0-3): ").strip()
        except (EOFError, KeyboardInterrupt):
            return "0"
        if choice in ("1", "2", "3", "0"):
            return choice
        print("  无效输入，请重试")


def launch_web():
    """启动 Web 界面"""
    py = get_venv_python()
    print()
    print("  [启动] Web 界面 ...")
    print("  地址: http://localhost:8080")
    print("  按 Ctrl+C 停止服务")
    print()
    try:
        import webbrowser
        webbrowser.open("http://localhost:8080")
    except Exception:
        pass
    r = subprocess.run([str(py), "server.py", "--port", "8080"], cwd=str(PROJECT_DIR))
    if r.returncode != 0:
        print("\n  [错误] Web 服务启动失败！")
        print("  请检查端口 8080 是否被占用")


def launch_cli():
    """启动命令行模式"""
    py = get_venv_python()
    print()
    print("  [启动] 命令行模式 ...")
    print()
    r = subprocess.run([str(py), "main.py"], cwd=str(PROJECT_DIR))
    if r.returncode != 0:
        print("\n  [错误] 命令行模式异常退出")


def launch_streamlit():
    """启动 Streamlit"""
    py = get_venv_python()
    print()
    print("  [启动] Streamlit 管理台 ...")
    print("  地址: http://localhost:8501")
    print()
    r = subprocess.run(
        [str(py), "-m", "streamlit", "run", "app.py", "--server.port", "8501"],
        cwd=str(PROJECT_DIR)
    )
    if r.returncode != 0:
        print("\n  [错误] Streamlit 启动失败！")
        print("  请检查端口 8501 是否被占用")


def main():
    banner()

    # Step 1: 找 Python
    python_cmd, ver_str = find_python()
    if not python_cmd:
        print("  [错误] 未检测到 Python！")
        print("  请安装 Python 3.12: https://www.python.org/downloads/")
        print("  安装时请勾选 'Add Python to PATH'！")
        input("\n  按回车退出 ...")
        return

    # Step 2: 检查/创建 venv
    if VENV_DIR.exists() and check_venv_version(python_cmd):
        pass  # venv 版本匹配，继续
    else:
        if VENV_DIR.exists():
            print("  [!] 虚拟环境版本不匹配，正在重建 ...")
            shutil.rmtree(str(VENV_DIR))
        if not create_venv(python_cmd, ver_str):
            input("\n  按回车退出 ...")
            return

    # Step 3: 升级 pip
    upgrade_pip()

    # Step 4: 检查/安装依赖
    if check_deps():
        print("  [2/4] 依赖已安装，跳过")
    else:
        if not install_deps():
            input("\n  按回车退出 ...")
            return

    # Step 5: 验证核心包
    if not check_deps():
        if not fix_core_packages():
            input("\n  按回车退出 ...")
            return

    # Step 6: 检查 Playwright & GitPython & pytest
    check_playwright()
    check_gitpython()
    check_pytest()

    # Step 7: 创建 .env
    create_env()

    # Step 8: 环境检查
    print()
    print("  [4/4] 环境检查 ...")
    if not check_server():
        input("\n  按回车退出 ...")
        return
    check_ollama()

    # Step 9: 菜单
    while True:
        choice = menu()
        if choice == "1":
            launch_web()
        elif choice == "2":
            launch_cli()
        elif choice == "3":
            launch_streamlit()
        elif choice == "0":
            print("  已退出")
            return

        # 启动模式退出后回到菜单
        print()
        input("  按回车返回菜单 ...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  已退出")
    except Exception as e:
        print(f"\n  [致命错误] {e}")
        import traceback
        traceback.print_exc()
        input("\n  按回车退出 ...")
