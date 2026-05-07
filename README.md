# YI-Agent V4

基于易经六十四卦的工具索引 AI Agent 框架。用三维向量映射卦象，将 58 个工具的搜索空间压缩到 3-5 个候选，让 LLM 精准调用而非盲目选择。

## 核心理念

LLM 面对 50+ 工具时选择困难。YI-Agent 在 LLM 之前加了一层**工具索引**：

1. 根据当前执行态势（资源/进展/完成度）计算三维向量
2. 向量映射到六十四卦之一，锁定 3-5 个相关工具 + 历史成功率
3. 索引提示注入 system message，LLM 在小范围内自主决策

**卦象是参谋，不是司令。** 提供参考信息，最终决策权在 LLM。SQLite 存储「卦象 × 工具」历史成功率，越用越准。

---

## 快速开始

### 环境要求
- Python 3.10+（推荐 3.12）
- Windows 10/11

### 启动

```powershell
python 启动.py
```

`启动.py` 自动完成：检测 Python → 创建虚拟环境 → 安装依赖（含 pytest、Playwright、GitPython）→ 环境检查 → 进入菜单。

| 模式 | 说明 | 地址 |
|------|------|------|
| Web 界面 | 浏览器可视化，推荐日常使用 | http://localhost:8080 |
| 命令行 | 终端交互，适合开发者 | — |
| Streamlit | 管理控制台，功能更全 | http://localhost:8501 |

### 配置 API

首次启动自动创建 `.env`，或在 Web 界面「设置」中直接填写（热加载，无需重启）：

```env
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

---

## 架构

```
用户输入
    ↓
[1] 态势评估（三维向量：资源/进展/完成度）
    ↓ 纯数学，零 LLM 调用
[2] 向量 → 六十四卦 → 工具索引提示
    ↓ 锁定 3-5 个候选工具 + 历史成功率
[3] 提示注入 system message
    ↓ LLM 在限定范围内自主决策
[4] 工具执行 + 效果记录
    ↓ YiRuntime 实时更新向量
[5] 动爻检测 → 索引更新
    ↓ 连续失败/成功 → 快速翻转
[6] 经验回流（双窗口加权）+ 技能沉淀
```

### 三维正交向量

| 维度 | 信号源 | 含义 |
|------|--------|------|
| d1 资源 | 工具耗时 + 平台可达性 | 系统当前的执行能力 |
| d2 进展 | 滑动窗口成功率 | 近期执行质量 |
| d3 完成度 | 任务进度 | 当前任务完成程度 |

### 防震荡机制

- 迟滞区间防止阈值附近抖动
- 30 次操作内翻转不超过 5 次
- 连续 3 次失败 → 强制保守索引
- 连续 5 次成功 → 强制激进索引

---

## 功能模块

### ☯️ 易经引擎
大衍筮法六爻十八变，三维向量→卦象→工具候选。八卦各映射一类工具能力，六十四卦锁定具体组合。

### 🔧 工具系统（58 个）
自动发现 + 动态 Schema + 优雅降级链。涵盖：
- **文件操作**：read/write/edit/list/scan/find/move/organize
- **浏览器自动化**：Playwright 驱动，28 个 ab_* 操作，操作后自动返回页面上下文
- **Git 工具**：status/diff/add/commit/push/restore，支持 `cwd` 跨目录操作，测试通过门禁防误推
- **搜索**：web_search + news_search
- **系统**：run_command（危险命令拦截）
- **记忆**：remember/recall
- **变量**：get/set/list 变量管理

### 🎯 技能系统
首次走分解流程，二次极速执行。TTL 暂存 + 人工确认，技能可从执行历史中自动沉淀。

### 🧠 意图路由
BM25 + LLM 精排。分类→匹配→执行→沉淀，支持技能热加载。

### 🔒 安全模块
文件系统守卫 + 命令拦截 + 敏感文件保护 + 路径穿越检测。

### 📊 执行日志
全链路打点，工具效果评估（双窗口加权），为进化提供数据支撑。

---

## 项目结构

```
YI-Agent-V4/
├── core/                    # 核心引擎
│   ├── conversation.py      # 对话管理器（Agent 主循环）
│   ├── dayan.py             # 大衍筮法引擎（六爻十八变）
│   ├── workflow.py          # 工作流执行器（拓扑排序）
│   ├── intent_router.py     # 意图路由（BM25 + LLM 精排）
│   └── llm.py               # LLM 调用封装（DeepSeek + Ollama 双客户端）
│
├── yi_framework/            # 态势感知引擎
│   ├── profiles.py          # 六十四卦 → 工具索引映射
│   ├── runtime.py           # 三维向量 + 动爻检测 + 防震荡
│   └── effectiveness.py     # 工具效果评估（双窗口加权）
│
├── tools/                   # 工具层
│   ├── registry.py          # 工具注册表（自动发现 + TTL 缓存 + 降级链）
│   ├── git_ops.py           # Git 工具集（GitPython + 测试门禁）
│   ├── agent_browser.py     # Playwright 浏览器自动化
│   ├── subprocess_runner.py # 命令执行器
│   └── plugins/             # 工具插件（自注册）
│       ├── file_ops.py      # 文件操作（read/write/edit/list/find/move）
│       ├── git_tools.py     # Git 工具注册
│       ├── system_tools.py  # 系统工具（run_command）
│       ├── search_tools.py  # 搜索工具
│       ├── agent_browser_tools.py  # 浏览器工具
│       ├── memory_tools.py  # 记忆工具
│       └── variable_tools.py # 变量工具
│
├── skills/                  # 技能系统
│   ├── staging.py           # 技能暂存（TTL + 人工确认）
│   ├── loader.py            # 技能加载
│   └── executor.py          # 技能执行
│
├── security/                # 安全模块
├── memory/                  # 记忆系统
├── data/                    # 执行日志 SQLite
│
├── index.html               # Web 前端（纯 HTML+JS）
├── server.py                # Flask API 后端
├── app.py                   # Streamlit 控制台
├── main.py                  # 命令行入口
├── config.py                # 配置（支持热重载）
├── 启动.py                  # 一键启动器（自动环境准备）
└── requirements.txt         # Python 依赖
```

---

## 支持的模型

| 模型 | 说明 |
|------|------|
| deepseek-chat | 默认模型，中文写作与代码能力强 |
| deepseek-v4-pro | 推理能力更强 |
| deepseek-reasoner | 深度推理模式 |
| moonshot-v1-8k | Kimi，超长上下文 |
| qwen-turbo | 通义千问 |
| glm-4-flash | 智谱 GLM-4 |
| gpt-4o / gpt-4o-mini | OpenAI |
| claude-3-5-sonnet | Anthropic |

Web 界面支持一键切换模型，API 地址自动填充。

---

## 未来方向

让 Agent **自我升级**：浏览网页 → 下载代码 → 读写修改 → 跑测试 → 推 GitHub。

三个瓶颈按优先级：
1. **浏览器反馈可靠性** ← 已基本解决（操作后自动返回 page_info）
2. **LLM 判断力** → 用测试结果代替 LLM 自评
3. **安全性** → 测试通过门禁，不需要全开安全层

---

## 许可证

MIT License
