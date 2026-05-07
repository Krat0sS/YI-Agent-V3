# tools/plugins/git_tools.py
# Git 工具插件 — 版本控制操作，自注册到 ToolRegistry
from tools.registry import registry
from tools.git_ops import (
    git_status, git_diff, git_add, git_commit,
    git_push, git_restore, git_last_test
)

registry.register(
    name="git_status",
    handler=git_status,
    description="查看当前 Git 仓库状态（分支、变更文件）",
    schema={
        "name": "git_status",
        "description": "查看当前 Git 仓库状态（分支、变更文件）",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "仓库目录路径，默认当前工作目录"}
            }
        }
    },
    category="git",
)

registry.register(
    name="git_diff",
    handler=git_diff,
    description="查看工作区与最后一次提交的差异",
    schema={
        "name": "git_diff",
        "description": "查看工作区与最后一次提交的差异",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "可选，仅查看指定文件差异"},
                "cwd": {"type": "string", "description": "仓库目录路径，默认当前工作目录"}
            }
        }
    },
    category="git",
)

registry.register(
    name="git_add",
    handler=git_add,
    description="将文件添加到 Git 暂存区",
    schema={
        "name": "git_add",
        "description": "将文件添加到 Git 暂存区",
        "parameters": {
            "type": "object",
            "properties": {
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要添加的文件路径列表"
                },
                "cwd": {"type": "string", "description": "仓库目录路径，默认当前工作目录"}
            },
            "required": ["file_paths"]
        }
    },
    category="git",
)

registry.register(
    name="git_commit",
    handler=git_commit,
    description="提交暂存的更改",
    schema={
        "name": "git_commit",
        "description": "提交暂存的更改",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "提交信息（1-200字符）"},
                "cwd": {"type": "string", "description": "仓库目录路径，默认当前工作目录"}
            },
            "required": ["message"]
        }
    },
    category="git",
)

registry.register(
    name="git_push",
    handler=git_push,
    description="推送提交到远程仓库（要求最近一次测试全部通过）",
    schema={
        "name": "git_push",
        "description": "推送提交到远程仓库（要求最近一次测试全部通过）",
        "parameters": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "分支名，默认 main"},
                "cwd": {"type": "string", "description": "仓库目录路径，默认当前工作目录"}
            }
        }
    },
    category="git",
    risk_level="high",
)

registry.register(
    name="git_restore",
    handler=git_restore,
    description="回滚文件到最近一次提交的状态（用于取消错误的修改）",
    schema={
        "name": "git_restore",
        "description": "回滚文件到最近一次提交的状态（用于取消错误的修改）",
        "parameters": {
            "type": "object",
            "properties": {
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要回滚的文件列表，不填则回滚全部"
                },
                "cwd": {"type": "string", "description": "仓库目录路径，默认当前工作目录"}
            }
        }
    },
    category="git",
)

registry.register(
    name="git_last_test",
    handler=git_last_test,
    description="查看最近一次自动化测试的结果",
    schema={
        "name": "git_last_test",
        "description": "查看最近一次自动化测试的结果",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    category="git",
)
