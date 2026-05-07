# v1.5.0 — 安全硬内核 + UI 管理层 + HTML 界面优化 + 全面 Bug 修复

> 日期：2026-05-05
> 分支：`discipline-first`
> 会话：第 8 次（15:48 - 16:17）

---

## Phase 1: 安全硬内核 ✅

详见下方原始 changelog。

---

## UI 管理层 ✅（commit `2b4eec8`）

### 新增 `manage/` 目录
- `manage/tool_manager.py` — 工具启用/禁用/搜索/分类/一键自动配置
- `manage/skill_manager.py` — 技能增删改查（SKILL.md 文件管理）
- `manage/memory_manager.py` — 记忆查看/搜索/删除/统计

### 修改 `tools/registry.py`
- `ToolDefinition` 新增 `_manual_enabled` 字段
- 新增 `enable()` / `disable()` / `reset_manual()` 方法
- `is_available()` 支持手动开关优先

### 修改 `app.py`
- 侧边栏改为 💬🧠🎯🔧 四 Tab 管理页

### 测试
- `tests/test_managers.py` — 28 个测试全过

---

## HTML 界面优化 ✅（commit `84ed2c2`）

### `server.py` — 新增 12 个 API 端点

| 分类 | 端点 | 方法 | 说明 |
|------|------|------|------|
| 工具 | `/api/tools` | GET | 按分类列出所有工具 |
| 工具 | `/api/tools/search?q=` | GET | 搜索工具 |
| 工具 | `/api/tools/<name>/toggle` | POST | 启用/禁用工具 |
| 工具 | `/api/tools/auto-configure` | POST | 一键自动配置 |
| 技能 | `/api/skills` | GET | 列出所有技能 |
| 技能 | `/api/skills/<name>` | GET | 读取技能内容 |
| 技能 | `/api/skills` | POST | 创建新技能 |
| 技能 | `/api/skills/<name>` | DELETE | 删除技能 |
| 记忆 | `/api/memory` | GET | 列出日记忆 |
| 记忆 | `/api/memory/search?q=` | GET | 搜索记忆 |
| 记忆 | `/api/memory/stats` | GET | 记忆统计 |
| 记忆 | `/api/memory/<filename>` | GET/DELETE | 读取/删除记忆 |

`/api/status` 增强版：返回分类工具 + 技能 + 记忆统计。

### `index.html` — 新增 3 个管理页

- 🔧 **工具管理** — 分类展示、启用/禁用开关、搜索、一键自动配置
- 🎯 **技能管理** — 列表、查看 SKILL.md、新建、删除
- 🧠 **记忆管理** — MEMORY.md 长期记忆、日记忆、搜索、删除
- 顶部 Tab 导航：💬🔧🎯🧠ℹ️
- 侧边栏适配新 API 格式

---

## 全面 Bug 修复 ✅（commit `83f3059`）

基于诊断清单 25 个问题，修复了 8 项关键/高危问题：

| # | 问题 | 修复 |
|---|------|------|
| 4 | `on_confirm` 回调静默跳过 | `Conversation.__init__` 接收实例级回调，无回调时拒绝危险操作 |
| 5 | 记忆检索不可用 | `get_recent_context` 按行边界截断，新增 `search_memory` 全文搜索 |
| 12 | 中文截断乱码 | 按行边界截断，不切断多字节字符 |
| 13 | LLM 调用无重试 | `_execute_chat` 加指数退避重试（超时/429/5xx，最多 3 次） |
| 14 | .gitignore 不全 | 补全 `rollback_data/`、`*.db`、`*.log` |
| 16 | 截图 base64 超长 | >200KB 自动保存到临时文件，返回路径 |
| 17 | watchdog 缺失 | `requirements.txt` 补全 `watchdog>=3.0.0` |
| 18 | SubAgent 递归 | 加 `depth`/`max_depth` 参数保护 |

---

## 一键启动 `start.bat` 重写

- 自动检测 Python 环境
- 自动创建虚拟环境
- 清华大学 pip 镜像加速
- 自动安装依赖
- 自动创建 `.env` 配置文件
- 界面选择：Web（推荐）/ CLI / 退出

---

## 当前状态

| 模块 | 状态 |
|------|------|
| 安全硬内核 | ✅ 完成 |
| UI 管理层 | ✅ 完成 |
| HTML 界面优化 | ✅ 完成 |
| Bug 修复 | ✅ 17/25 已解决，8 个低风险后续处理 |
| 一键启动 | ✅ 完成 |

---

## 剩余架构债务（低优先级）

| # | 问题 | 建议 |
|---|------|------|
| 7 | 工具失败时 LLM 幻觉 | 在工具结果中注入明确错误提示 |
| 9 | 缓存键无命名空间 | 单用户场景不影响，多用户时再加 |
| 10 | TOCTOU 插件加载 | Phase 2 工具插件化时一并修复 |
| 11 | 三入口不一致 | 建议统一为 server.py + index.html |
| 19 | 缓存 TTL 依赖系统时间 | 单机场景不影响 |
| 21 | builtin_compat 覆盖 | 命名规范避免冲突 |
