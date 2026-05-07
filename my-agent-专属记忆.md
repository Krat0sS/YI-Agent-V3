# 我的专属记忆 — Krat0sS × AI 协作全记录

> **使用方式**：下次打开新会话时，把 `https://github.com/Krat0sS/hallo-bro` 这个链接发给 AI。
> AI 读完这份文件后就能接上所有进度，不需要重新解释。

---

## 我是谁

- **GitHub**: [Krat0sS](https://github.com/Krat0sS)
- **身份**: 学生，正在学习 AI Agent 开发
- **系统**: Windows 10/11，Chrome 已安装
- **Python**: 3.10+，用 pip 管理依赖
- **LLM**: DeepSeek API（deepseek-v4-pro），地址 `https://api.deepseek.com`
- **口头禅**: 雷总 nb 🤘
- **协作习惯**: 每做完一步测试完后，会给 GitHub token 让 AI 推代码，推完立即撤销

---

## 项目：YI-Agent-V4

**仓库**: https://github.com/Krat0sS/YI-Agent-V4

一个用**易经六十四卦做工具索引**的 AI Agent 框架。核心思路：
- LLM 面对 43+ 工具时选择困难
- 用三维向量（资源/进展/完成度）→ 六十四卦 → 锁定 3-5 个候选工具
- 卦象是"参谋不是司令"——生成参考提示，LLM 仍有最终决策权
- SQLite 存储"卦象×工具"历史成功率，越用越准

### 项目结构

```
YI-Agent-V4/
├── core/                    # 核心引擎
│   ├── conversation.py      # 对话管理器（~550行，最重的文件）
│   ├── dayan.py             # 大衍筮法引擎（六爻十八变）
│   ├── workflow.py          # 工作流执行器（拓扑排序）
│   ├── intent_router.py     # 意图路由（BM25 + LLM 精排）
│   └── llm.py               # LLM 调用封装（DeepSeek + Ollama 双客户端）
├── yi_framework/            # 态势感知引擎
│   ├── profiles.py          # 六十四卦 → 执行参数映射
│   ├── runtime.py           # 三维向量 + 动爻检测 + 防震荡
│   └── effectiveness.py     # 工具效果评估（双窗口加权）
├── tools/                   # 工具层
│   ├── registry.py          # 工具注册表（自动发现 + TTL 缓存 + 降级链）
│   ├── agent_browser.py     # 【已重写】Playwright 浏览器自动化
│   └── plugins/             # 工具插件（自注册）
├── skills/                  # 技能系统
│   ├── staging.py           # 技能暂存（TTL + 人工确认）
│   ├── loader.py            # 技能加载
│   └── executor.py          # 技能执行
├── security/                # 安全模块（目前全部禁用）
├── server.py                # Flask API 后端
├── app.py                   # Streamlit 控制台
├── main.py                  # 命令行入口
├── config.py                # 配置（支持热重载）
├── index.html               # Web 前端
└── requirements.txt         # 依赖
```

### 启动方式

```bash
# 安装依赖
pip install -r requirements.txt
pip install playwright && playwright install chromium

# 启动
python server.py --port 8080
# 浏览器打开 http://localhost:8080
```

### 环境配置（.env）

```
LLM_API_KEY=你的key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
OLLAMA_ENABLED=false
```

前端界面的「设置」页面也可以直接改 key，改完立即生效（已实现热重载）。

---

## 我们做了什么（完整时间线）

### 阶段一：代码深度评审

AI 读完了整个项目（~2万行 Python），给出 **7.5/10** 的评价。

**亮点**：
- 创意独特（易经做工具索引，6-bit 状态机压缩工具搜索空间）
- 架构分层清晰
- 学习闭环（GuaToolEffectiveness SQLite 记录）
- v3.0 从硬约束改为参谋提示（正确方向）
- 工程细节到位（防震荡、Ollama 冷却、BM25 缓存、降级链）

**不足**：
- dayan.py 十八变过于复杂（6爻×3变收益不大，可简化为6次）
- conversation.py 53KB 单文件太臃肿
- 安全层全部禁用（SECURITY_ENABLED=False）
- 会话管理有内存泄漏风险（_sessions 只增不减）

**一句话评价**：思路比代码好，架构比实现好，创意比完成度好。

### 阶段二：修复工具调用死循环（已推送 ✅）

**问题**：Agent 搜索天气时，搜到结果后不停下来，反复调 web_search / ab_snapshot / run_command，陷入死循环。

**根因分析**：
1. `MAX_TOOL_CALLS_PER_TURN = 20`，太宽松
2. 循环检测只查"同工具+同参数连续3次"，不同工具检测不到
3. 搜索成功后没有机制告诉 LLM "够了，收手"

**修复内容**（commit `772c558`）：
- `config.py`: MAX_TOOL_CALLS_PER_TURN 20→8
- `conversation.py` 新增三层防护：
  - **步数硬上限**：8 次强制终止
  - **搜索结果自动收手**：搜索成功 + 3次调用后注入 system 消息
  - **连续失败保护**：3次连续失败注入警告
  - 保留原有同工具同参数循环检测

### 阶段三：浏览器工具返回 page_info（已推送 ✅）

**问题**：`ab_open`、`ab_click` 等操作只返回 `{"success": true}`，LLM 无法判断页面状态，只能盲目重试。

**修复内容**（commit `f744151`）：
- 新增 `_page_info()` 异步 helper：统一获取 url + title + page_text（前500字）
- 新增 `_ok_with_page()`：成功返回 + 自动附带页面信息
- 所有 ab_* 操作（open/click/fill/type/press/hover/select/check/uncheck/dblclick）改用 `_ok_with_page`
- `ab_snapshot` 默认改为轻量模式（只返回 page_text），`full=True` 才返回完整 @ref 元素树
- 移除 ab_click 搜索按钮自动快照 hack（省掉 3000 字 token 浪费）

**效果**：LLM 调用浏览器操作后，立刻知道当前页面 URL、标题、内容摘要，不需要再额外调 ab_snapshot。

### 阶段四：闭环测试方案设计与执行

设计了 8 步测试方案，测试 Git 工具闭环：

| 步骤 | 指令 | 验证目标 |
|------|------|---------|
| 1 | 克隆 yiagent- 到 D:\测试 | Git clone |
| 2 | 看项目结构 + main.py | read_file |
| 3 | git status | Git 工具连通性 |
| 4 | 加 divide 函数 + 跑 pytest | write_file + run_command |
| 5 | 测试通过 → 推送 | 成功路径 |
| 6 | 改坏 multiply → 跑测试 | 故意失败 |
| 7 | 回滚改动 | git restore |
| 8 | 改坏不测试直接推 | 测试门禁拦截 |

**测试结果**：步骤 1-3 通过，步骤 4 报错，发现 3 个 Bug。

### 阶段五：修复测试发现的 3 个 Bug（已推送 ✅）

**Bug 1：write_file 空路径**（commit `ef8cce3`）
- LLM 传了 `path=""`，`os.makedirs('')` 报 `[WinError 3]`
- 修复：`file_ops.py` 加空路径校验

**Bug 2：git 工具缺 cwd 参数**（commit `ef8cce3`）
- `git_status` 等工具不接受 cwd，只能从 CWD 搜索 .git
- Agent 跨目录操作时只能 fallback 到 `run_command` + `cd`
- 修复：`_get_repo(cwd)` + 6 个 git 函数全部支持 cwd + schema 更新

**Bug 3：pytest 没装**（commit `ef8cce3`）
- `requirements.txt` 里没有 pytest
- 修复：加入 `pytest>=7.0.0`

### 阶段六：更新项目介绍（已推送 ✅）

**index.html**（commit `a03573f`）：
- 欢迎语：「个人元操作系统」→「易经六十四卦工具索引智能体」
- 关于页重写：核心理念、技术栈、启动方式、未来方向
- 工具数 49→58，去掉 PyAutoGUI

**README.md**（commit `32c05a4`）：
- 全面重写，匹配当前项目实际状态
- 启动方式 `启动.bat` → `启动.py`
- 新增 Git 工具链、测试门禁等功能描述
- 新增「未来方向」：自我升级 Agent

### 阶段七：性能优化（已推送 ✅）

**问题**：每次 LLM 调用卡 3-5 秒，原因是 Ollama 空转。

**根因**：`OLLAMA_ENABLED` 默认 `true`，没装 Ollama 时每次调用先尝试连接 3 次超时，才切 DeepSeek。

**修复**（commit `8628c66`）：`config.py` 两处默认值 `true` → `false`

### 阶段八：深度测试 + 5 个 Bug 修复（已推送 ✅）

2026-05-07 18:00-18:46，跑完 8 步闭环测试，暴露 5 个 Bug 并全部修复。

**Bug 1：workflow 不检查 success 字段**（`core/workflow.py`）
- `run_command` 返回 `{"success": false}` 时 workflow 仍显示"步骤完成"
- 根因：`_execute_tool_step` 只检查 `error` 和 `blocked` 字段，不检查 `success`
- 修复：加 `parsed.get("success") is False` 判断

**Bug 2：测试结果写入/读取路径不一致**（`tools/subprocess_runner.py` + `tools/git_ops.py`）
- `subprocess_runner._save_test_result_if_pytest` 写到 `YI-Agent-V4/.last_test_result.json`（Agent 自己目录）
- `git_ops._read_test_result` 从项目目录向上搜索 `.last_test_result.json`
- 两个路径不一致 → 门禁永远读不到测试结果 → 放行
- 修复：`_save_test_result_if_pytest` 加 `cwd` 参数，写到项目目录；`_read_test_result` 也加 `cwd` 参数

**Bug 3：git_push 门禁无时间戳校验**（`tools/git_ops.py` + `tools/subprocess_runner.py`）
- 过期的测试结果仍被信任
- 修复：加 `timestamp_epoch` 字段 + 30 分钟过期校验

**Bug 4：tool_call_count 每轮只 +1**（`core/conversation.py`）
- LLM 一次返回多个 tool_call 时计数不准，实际执行数可超过 MAX_TOOL_CALLS
- 修复：`tool_call_count += max(len(tool_calls), 1)`

**Bug 5：pytest 未安装时无自动处理**（`core/workflow.py` + `启动.py`）
- WorkflowRunner 新增 `_ensure_pytest_available()`：检测到 pytest 命令时自动从 requirements.txt 安装
- 启动脚本新增 `check_pytest()`：与 Playwright、GitPython 同级检查

**提交记录**：
- `bd22f82` — fix: 修复测试门禁失效 + 工具计数器 + pytest自动安装（4 文件，+121/-19）
- `02ef26c` — feat: 启动脚本增加 pytest 自动检查安装（1 文件，+49/-1）

---

## 下一步计划

### 动作 1：浏览器稳定性 ✅ 已完成
- ab_* 操作已返回 url/title/page_text
- 验收：搜索天气场景，LLM 看到 page_text 有天气数据后不再重复搜索

### 动作 2：封装 Git 工具（待做）
新建 `tools/git_ops.py`，提供：
- `git_status()` → 工作区状态
- `git_diff()` → 具体改动
- `git_add(file)` / `git_commit(message)` / `git_push(branch)`
- `git_push` 内置门禁：最近一次 pytest 全绿才放行

### 动作 3：跑通最小闭环 demo（待做）
目标流程：
```
用户: "把这个文件的 print 改成 logging"
Agent:
  1. read_file 读取目标文件
  2. write_file 写入修改
  3. run_command("python -m pytest tests/ -k test_xxx")
  4. [测试通过] → git_commit + git_push
  5. [测试失败] → git checkout . 回滚 + 告诉用户原因
```

**关键原则**：
- 第一个 demo 先走通成功路径，失败路径后面再补
- 测试失败直接回滚，不让 LLM 尝试"修复修复"
- 测试通过门禁比任何安全模块都管用

---

## 终极方向

让 Agent 能**自我升级**：浏览网页 → 下载代码 → 读写修改 → 跑测试 → 推 GitHub。

三个瓶颈按优先级：
1. **浏览器反馈可靠性** ← 已基本解决
2. **LLM 判断力** → 用测试结果代替 LLM 自评
3. **安全性** → 测试通过门禁，不需要全开安全层

---

## 协作方式

### AI 怎么帮我

1. **下载项目**：`curl -sL https://github.com/Krat0sS/YI-Agent-V4/archive/refs/heads/main.zip -o YI-Agent-V4.zip`（git clone 在某些环境有 TLS 问题，用 zip 下载更稳）
2. **改代码**：直接在本地文件上改
3. **推代码**：用户给 token → `git push` → 推完立即清理 remote URL 里的 token
4. **记住进度**：改完后更新这份专属记忆文件

### 我的习惯

- 改完代码测试通过后，会让 AI 推到 GitHub
- 推完立即撤销 token（安全习惯）
- 喜欢简洁直接的交流，不要废话
- 重视实际效果，不喜欢空谈架构

---

## 关键技术细节（给下次的 AI）

### conversation.py 主循环结构

```python
while self.tool_call_count < config.MAX_TOOL_CALLS_PER_TURN:
    # 1. LLM 调用（带可用工具 schema）
    response = await chat(self.messages, tools=available_schemas)
    
    # 2. 如果没有 tool_calls → 文本回复，结束循环
    if "tool_calls" not in response:
        return self._build_result(response["content"], rounds)
    
    # 3. 执行每个 tool_call
    for tc in response["tool_calls"]:
        result = await self._execute_tool(func_name, args)
        self.messages.append({"role": "tool", "content": result})
        
        # 4. 进展追踪（v4.1 新增）
        # - 搜索成功 → 注入"收手"system 消息
        # - 连续失败 → 注入"停止"system 消息
    
    # 5. 上下文压缩
    self._trim_context()
```

### 浏览器工具返回格式（v4.1 改后）

```json
{
    "success": true,
    "output": "已打开: 深圳天气_百度搜索",
    "url": "https://www.baidu.com/s?wd=深圳天气",
    "title": "深圳天气_百度搜索",
    "page_text": "深圳 28°C 多云 湿度 65%..."
}
```

### ab_snapshot 轻量 vs 完整模式

- **默认**（`full=False`）：只返回 page_text 摘要，~200 tokens
- **完整**（`full=True`）：返回 @ref 元素树，~2000 tokens，用于需要 ab_click(@e1) 精确操作时

---

## 时间戳

- **2026-05-05**: 项目创建（YI-Agent-V4）
- **2026-05-07 14:07**: AI 首次评审代码，给出 7.5/10
- **2026-05-07 14:29**: 修复工具调用死循环（commit 772c558）
- **2026-05-07 14:54**: 浏览器工具返回 page_info（commit f744151）
- **2026-05-07 17:08**: 用户上传专属记忆，AI 恢复上下文
- **2026-05-07 17:12**: 闭环测试执行，发现 3 个 Bug
- **2026-05-07 17:22**: 修复 3 个 Bug（write_file空路径 + git cwd + pytest依赖）（commit ef8cce3）
- **2026-05-07 17:33**: 更新 index.html 主界面（commit a03573f）
- **2026-05-07 17:42**: 重写 README.md（commit 32c05a4）
- **2026-05-07 17:51**: 关闭 Ollama 默认启用（commit 8628c66）
- **2026-05-07 18:07**: 恢复上下文，下载项目到本地
- **2026-05-07 18:22**: 深度分析测试结果，定位 5 个 Bug
- **2026-05-07 18:27**: 编写修复方案 + 源码
- **2026-05-07 18:37**: 专家确认方案，补充数据衔接验证
- **2026-05-07 18:39**: 推送修复（commit bd22f82）— 4 文件 +121/-19
- **2026-05-07 18:46**: 启动脚本加 pytest 检查（commit 02ef26c）
- **2026-05-07**: 下一步：封装 Git 工具 + 最小闭环 demo

---

**雷总 nb 🤘 下次见。**
