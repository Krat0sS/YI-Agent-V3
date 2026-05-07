# 安全硬内核 — 操作说明

> Phase 1 完成后的使用和配置指南

---

## 快速开始

安全模块开箱即用，不需要额外配置。启动 Agent 后自动生效。

```bash
python main.py
```

安全拦截器会在每次工具调用时自动检查。

---

## 配置

### 环境变量（.env）

```bash
# 安全总开关（默认开启）
SECURITY_ENABLED=true

# 频率熔断：窗口时长（秒）
SECURITY_RATE_WINDOW=30

# 频率熔断：窗口内最大操作数
SECURITY_RATE_MAX_OPS=20
```

### 命令白名单（security/command_whitelist.yaml）

编辑 YAML 文件即可自定义白名单：

```yaml
# 添加新的只读命令
read_only:
  - ls
  - cat
  - your_custom_command    # ← 在这里加

# 添加新的写命令
write:
  - mv
  - cp
  - your_write_command     # ← 在这里加

# 添加需要二次确认的命令
write_requires_confirm:
  - rm
  - your_dangerous_command # ← 在这里加
```

### 路径白名单

```yaml
allowed_path_prefixes:
  - "~"           # 用户主目录
  - "~/Desktop"   # 桌面
  - "~/Downloads" # 下载目录
  - "/tmp"        # 临时目录
  - "/data"       # 自定义目录
```

---

## 工作原理

### 安全拦截流程

```
用户请求 → LLM 决策 → 工具调用
                        ↓
                  ┌─────────────┐
                  │ 安全拦截器   │ ← 代码层，不依赖 LLM
                  └──────┬──────┘
                         ↓
              ┌──────────┴──────────┐
              │                     │
         频率熔断检查           命令/路径检查
              │                     │
         ↓ 超频                ↓ 危险
     返回 blocked          返回 blocked
              │                     │
         ↓ 正常                ↓ 安全
              └──────────┬──────────┘
                         ↓
                    执行工具调用
```

### 四层检查

| 检查层 | 触发条件 | 拦截行为 |
|--------|---------|---------|
| 频率熔断 | 30秒内 > 20次操作 | 返回 `blocked: true, reason: "频率异常"` |
| 命令注入 | 命令含 ; \| & ` $() 等 | 返回 `blocked: true, reason: "危险字符"` |
| 白名单外 | 命令不在白名单中 | 返回 `blocked: true, reason: "不在白名单中"` |
| GUI 门控 | 高风险桌面/浏览器操作 | 返回 `needs_confirm: true`，等待用户确认 |

### 返回格式

**拦截时：**
```json
{
  "blocked": true,
  "reason": "命令包含危险字符 ';': cat file; rm -rf /",
  "tool": "run_command",
  "risk_level": "high"
}
```

**需确认时：**
```json
{
  "needs_confirm": true,
  "command": "rm file.txt",
  "reason": "写命令需用户确认: rm"
}
```

**通过时：** 正常执行工具，返回工具结果。

---

## 自定义扩展

### 添加新工具的安全检查

在 `security/filesystem_guard.py` 的 `check_tool_call()` 方法中添加：

```python
# 你的工具名
if tool_name == "your_tool":
    # 检查参数
    path = arguments.get("target_path", "")
    return self.check_path(path)
```

### 添加新的高风险 GUI 操作

在 `check_gui_operation()` 方法中：

```python
high_risk_gui = {
    "desktop_click", "desktop_double_click",
    "browser_click", "browser_type",
    "your_new_gui_tool",  # ← 在这里加
}
```

---

## 故障排除

### 问题：正常命令被拦截

**原因：** 命令不在白名单中
**解决：** 在 `command_whitelist.yaml` 的对应分类中添加命令名

### 问题：路径操作被拦截

**原因：** 路径不在 `allowed_path_prefixes` 中
**解决：** 在 YAML 中添加需要的路径前缀

### 问题：操作频率被熔断

**原因：** 短时间内操作过多
**解决：** 调整 `SECURITY_RATE_WINDOW` 或 `SECURITY_RATE_MAX_OPS`

### 问题：想临时关闭安全检查

**解决：** 设置环境变量 `SECURITY_ENABLED=false`

---

## 下一步

Phase 1 完成后，进入 Phase 2：动态工具注册 + 安全检疫

- 将 40 个工具从 builtin.py 拆分为 10 个插件文件
- 实现 TOCTOU 安全加载（读-哈希-执行一体）
- 建立信任清单机制
