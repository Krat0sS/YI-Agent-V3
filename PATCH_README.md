# YI-Agent V4 综合修复补丁

## 使用方法

按顺序修改以下 4 个文件，每处修改标注了 `# [PATCH]`。

---

## 1. `.env` — 关闭 Ollama

在 `.env` 文件末尾加一行：

```
OLLAMA_ENABLED=false
```

---

## 2. `tools/agent_browser.py` — 修复 agent-browser 查找 + 错误标识

替换 `_find_ab()` 和 `_run()` 两个函数（文件顶部约 46-105 行）：

```python
import sys  # [PATCH] 新增导入

def _find_ab() -> Optional[str]:
    """查找 agent-browser 可执行文件"""
    global _AB_CMD, _AB_CHECKED
    if _AB_CHECKED:
        return _AB_CMD
    _AB_CHECKED = True

    # 1. 环境变量指定
    env_path = os.environ.get("AGENT_BROWSER_PATH")
    if env_path and os.path.isfile(env_path):
        _AB_CMD = env_path
        return _AB_CMD

    # 2. PATH 中查找（包括 .cmd 文件）
    for name in ["agent-browser.cmd", "agent-browser"]:
        found = shutil.which(name)
        if found:
            _AB_CMD = found
            return _AB_CMD

    # 3. 常见安装路径（Windows 优先）
    candidates = [
        os.path.expandvars(r"%APPDATA%\npm\agent-browser.cmd"),
        os.path.expanduser("~/AppData/Roaming/npm/agent-browser.cmd"),
        os.path.expanduser("~/.npm-global/bin/agent-browser"),
        "/usr/local/bin/agent-browser",
        "/opt/homebrew/bin/agent-browser",
    ]
    for p in candidates:
        if os.path.isfile(p):
            _AB_CMD = p
            return _AB_CMD

    # 4. 兜底：返回命令名，让 subprocess 自己走 PATH 解析
    _AB_CMD = "agent-browser"
    return _AB_CMD


def _run(args: list[str], timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    执行 agent-browser 命令。
    返回 {"success": True, "output": str} 或 {"success": False, "error": str}
    """
    cmd_path = _find_ab()
    if not cmd_path:
        return {"success": False, "error": "agent-browser 未安装。请运行: npm install -g agent-browser && agent-browser install", "_tool_failed": True}

    cmd = [cmd_path] + args
    # [PATCH] Windows 上 .cmd 文件需要 shell=True 才能正确解析
    use_shell = (sys.platform == "win32" and not os.path.isabs(cmd_path))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=use_shell,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            if output:
                return {"success": True, "output": output[:MAX_OUTPUT], "warning": stderr[:500] if stderr else None}
            return {"success": False, "error": stderr or f"命令执行失败 (exit {result.returncode})", "_tool_failed": True}

        return {"success": True, "output": output[:MAX_OUTPUT]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"命令超时 ({timeout}s): {' '.join(args[:3])}", "_tool_failed": True}
    except FileNotFoundError:
        return {"success": False, "error": f"找不到 {cmd_path}。请运行: npm install -g agent-browser && agent-browser install", "_tool_failed": True}
    except Exception as e:
        return {"success": False, "error": f"执行异常: {str(e)}", "_tool_failed": True}
```

---

## 3. `conversation.py` — 只暴露可用工具 + 失败时跳过截图验证

### 修改 3a：send() 方法中只暴露可用工具

找到 `send()` 方法中的 LLM 调用（约第 330 行）：

```python
# 旧代码：
response = await chat(self.messages, tools=registry.get_schemas(), use_ollama=use_ollama)
```

替换为：

```python
# [PATCH] 只暴露当前环境实际可用的工具，避免 LLM 调用空壳工具
available_schemas = [
    s for s in registry.get_schemas()
    if registry.get(s["function"]["name"]).is_available()
]
response = await chat(self.messages, tools=available_schemas, use_ollama=use_ollama)
```

### 修改 3b：GUI 操作失败时跳过截图验证

找到 GUI 验证代码块（约第 380 行）：

```python
# 旧代码：
if func_name in GUI_VERIFY_TOOLS:
    try:
        tool_result = json.loads(result)
        if tool_result.get("success"):
```

替换为：

```python
if func_name in GUI_VERIFY_TOOLS:
    try:
        tool_result = json.loads(result)
        # [PATCH] 工具失败时不要浪费一次截图验证
        if tool_result.get("success") and not tool_result.get("_tool_failed"):
```

---

## 4. `config.py` — 提高工具调用上限

找到：

```python
MAX_TOOL_CALLS_PER_TURN = 10
```

替换为：

```python
MAX_TOOL_CALLS_PER_TURN = 20  # [PATCH] 浏览器操作天然需要多步
```

---

## 5. `intent_router.py` — BM25 精排走 DeepSeek

找到 `_llm_confirm_match()` 函数中的：

```python
result = await chat(messages, temperature=0.1, use_ollama=True)
```

替换为：

```python
result = await chat(messages, temperature=0.1, use_ollama=False)  # [PATCH] 精排走云端
```

---

## 验证步骤

1. 修改完后重启后端：`python server.py --port 8080`
2. 在 Web 界面输入：`打开百度搜索今天天气`
3. 预期结果：
   - 日志中 `ab_open` 耗时 > 1000ms（不是 1ms）
   - Chrome 浏览器自动弹出并打开百度
   - 搜索框自动输入"今天天气"并回车
   - 总耗时 < 30 秒
