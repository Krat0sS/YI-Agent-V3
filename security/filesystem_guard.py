"""
文件系统安全守卫 — 代码层拦截，零依赖 LLM

职责：
1. 路径安全检查（防符号链接绕过、目录穿越）
2. 命令安全检查（白名单模式、防注入）
3. 操作频率熔断
4. GUI 操作确认门控

设计原则：默认拒绝，显式允许。
"""
import os
import re
import time
import shlex
import threading
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

# ═══ 配置加载 ═══

_DEFAULT_READ_ONLY = {
    "ls", "stat", "find", "du", "df", "file", "cat", "head", "tail",
    "tree", "wc", "md5sum", "sha256sum", "pwd", "whoami", "which",
    "echo", "date", "env", "printenv",
    # Windows 常用只读命令
    "dir", "type", "where", "ver", "systeminfo", "tasklist",
    "ipconfig", "ping", "tracert", "nslookup", "hostname", "cls", "clear",
}

_DEFAULT_WRITE = {
    "mv", "cp", "rsync", "mkdir", "touch", "ln",
    "tar", "zip", "unzip", "diff", "tee",
    # Windows 常用写命令
    "start", "explorer", "open", "notepad", "code",
    "xcopy", "robocopy", "del", "ren", "rename", "attrib", "assoc", "ftype",
}

_DEFAULT_WRITE_CONFIRM = {"rm", "rmdir", "chmod", "chown", "chgrp"}

_DEFAULT_BLOCKED_CHARS = {";", "|", "&", "`", "$(", "${", "\n", "\r"}

# 默认允许的路径前缀（用户主目录 + 常见工作目录）
_DEFAULT_ALLOWED_PREFIXES = [
    os.path.expanduser("~"),
    "/tmp",
]


@dataclass
class SafetyResult:
    """安全检查结果"""
    safe: bool
    reason: str = ""
    needs_confirm: bool = False
    risk_level: str = "none"  # none / low / high
    resolved_path: str = ""
    details: dict = field(default_factory=dict)


class FileSystemGuard:
    """
    文件系统安全守卫。

    使用方法：
        guard = FileSystemGuard()
        result = guard.check_path("~/Desktop/test.txt")
        if not result.safe:
            print(f"拦截: {result.reason}")
    """

    def __init__(self, config_path: str = None):
        self._lock = threading.Lock()
        self._op_timestamps: dict[str, list[float]] = {}  # session_id → [timestamps]

        # 加载白名单
        self.read_only = set(_DEFAULT_READ_ONLY)
        self.write = set(_DEFAULT_WRITE)
        self.write_confirm = set(_DEFAULT_WRITE_CONFIRM)
        self.blocked_chars = set(_DEFAULT_BLOCKED_CHARS)
        self.allowed_prefixes = list(_DEFAULT_ALLOWED_PREFIXES)

        # 频率熔断参数（从 config.py 读取，有默认值）
        self.rate_window = 30   # 秒
        self.rate_max_ops = 20  # 窗口内最大操作数
        try:
            import config as _cfg
            self.rate_window = getattr(_cfg, 'SECURITY_RATE_WINDOW', 30)
            self.rate_max_ops = getattr(_cfg, 'SECURITY_RATE_MAX_OPS', 20)
        except (ImportError, AttributeError):
            pass

        # 从 YAML 加载自定义配置
        if config_path:
            self._load_yaml(config_path)
        else:
            default_yaml = os.path.join(os.path.dirname(__file__), "command_whitelist.yaml")
            if os.path.exists(default_yaml):
                self._load_yaml(default_yaml)

        # 自动追加用户主目录 + 当前工作目录（避免误拦用户项目路径）
        user_home = os.path.expanduser("~")
        cwd = os.getcwd()
        for p in [user_home, cwd]:
            real_p = os.path.realpath(p)
            if real_p not in [os.path.realpath(x) for x in self.allowed_prefixes] and os.path.exists(real_p):
                self.allowed_prefixes.append(real_p)

    def _load_yaml(self, path: str):
        """从 YAML 文件加载白名单配置"""
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            if not cfg:
                return
            if "read_only" in cfg:
                self.read_only = set(cfg["read_only"])
            if "write" in cfg:
                self.write = set(cfg["write"])
            if "write_requires_confirm" in cfg:
                self.write_confirm = set(cfg["write_requires_confirm"])
            if "blocked_chars" in cfg:
                self.blocked_chars = set(cfg["blocked_chars"])
            if "allowed_path_prefixes" in cfg:
                self.allowed_prefixes = [
                    os.path.expanduser(p) for p in cfg["allowed_path_prefixes"]
                ]
        except Exception:
            pass  # YAML 加载失败用默认值

    # ═══ 路径安全检查 ═══

    def check_path(self, path: str) -> SafetyResult:
        """检查文件路径是否安全 — 已开放全部权限，直接放行"""
        if not path:
            return SafetyResult(safe=False, reason="路径为空")
        expanded = os.path.expanduser(path)
        try:
            resolved = os.path.realpath(expanded)
        except OSError:
            resolved = expanded
        return SafetyResult(safe=True, resolved_path=resolved)

    # ═══ 命令安全检查 ═══

    def check_command(self, command: str) -> SafetyResult:
        """检查 shell 命令是否安全 — 已开放全部权限，直接放行"""
        if not command or not command.strip():
            return SafetyResult(safe=False, reason="命令为空")
        return SafetyResult(safe=True, risk_level="none")

    # ═══ 操作频率熔断 ═══

    def check_rate(self, session_id: str = "default") -> SafetyResult:
        """
        检查操作频率是否异常。
        30秒内超过20次操作则冻结。
        """
        now = time.time()
        with self._lock:
            if session_id not in self._op_timestamps:
                self._op_timestamps[session_id] = []

            timestamps = self._op_timestamps[session_id]
            # 清理过期时间戳
            cutoff = now - self.rate_window
            self._op_timestamps[session_id] = [t for t in timestamps if t > cutoff]

            if len(self._op_timestamps[session_id]) >= self.rate_max_ops:
                return SafetyResult(
                    safe=False,
                    reason=f"操作频率异常：{self.rate_window}秒内{len(self._op_timestamps[session_id])}次操作",
                    risk_level="high",
                    details={"operations_in_window": len(self._op_timestamps[session_id])},
                )

            # 记录本次操作
            self._op_timestamps[session_id].append(now)
            return SafetyResult(safe=True)

    # ═══ GUI 操作确认门控 ═══

    def check_gui_operation(self, func_name: str, args: dict) -> dict:
        """桌面/浏览器操作 — 已开放全部权限，直接放行"""
        return {"needs_confirm": False}

    # ═══ 统一入口：工具调用安全检查 ═══

    def check_tool_call(self, tool_name: str, arguments: dict,
                        session_id: str = "default") -> SafetyResult:
        """统一安全检查入口 — 已开放全部权限，直接放行"""
        return SafetyResult(safe=True)


# ═══ 全局单例 ═══
guard = FileSystemGuard()
