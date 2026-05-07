# HTML 界面优化计划

> 创建时间：2026-05-05 15:23 CST
> 目标：给 `index.html`（纯 HTML + JS 前端）加上工具管理、技能管理、记忆管理功能
> 前置条件：`manage/` 层已完成（tool_manager.py / skill_manager.py / memory_manager.py）

---

## 一、现状分析

### 当前 HTML 界面结构

```
index.html（纯前端，无框架依赖）
├── 左侧栏 — 工具列表 + 技能列表（只读，硬编码 fallback）
├── 中间 — 聊天区（消息 + 输入框）
├── 右侧栏 — 执行统计 + 日志
└── 设置下拉 — API 配置 + 主题切换
```

### 数据流

```
index.html → fetch('/api/chat') → Flask 后端 → Agent 执行
index.html → fetch('/api/status') → Flask 后端 → 返回工具/技能列表
```

### 问题

1. 左侧栏工具/技能只能看，不能操作（没有开关、没有增删改查）
2. 没有记忆管理入口
3. `/api/status` 返回的数据有限（只有 name + desc，没有分类、风险等级、启用状态）

---

## 二、改造方案

### 架构

```
index.html（前端）
    ↓ fetch API
Flask 后端（server.py / main.py）
    ↓ 调用
manage/ 层（已完成）
    ↓ 读写
数据层（registry.py / memory_system.py / skills/）
```

### 原则

1. **不改现有聊天功能** — 只加管理页，原有对话、统计、日志不动
2. **前端用原生 JS** — 不引入 React/Vue，保持零依赖
3. **后端复用 manage 层** — 不在 Flask 里写业务逻辑，只做路由
4. **增量式** — 每加一个 API + 一个前端页面，都可以独立验证

---

## 三、执行步骤

### 第 1 步：Flask 后端加 API 端点

**文件**：`server.py`（如果 API 在这里）或 `main.py`（如果 API 在这里）

先确认当前 API 定义在哪个文件里。

#### 1.1 确认 API 文件位置

```bash
grep -rn "api/chat\|api/status\|@app.route" server.py main.py 2>/dev/null
```

看哪个文件有 `@app.route` 装饰器，就改哪个。

#### 1.2 新增 6 个 API 端点

在 Flask 应用中添加以下路由：

```python
# ═══ 工具管理 API ═══

@app.route('/api/tools', methods=['GET'])
def api_tools_list():
    """列出所有工具（按分类分组）"""
    from manage.tool_manager import ToolManager
    mgr = ToolManager()
    return mgr.list_by_category()

@app.route('/api/tools/search', methods=['GET'])
def api_tools_search():
    """搜索工具"""
    keyword = request.args.get('q', '')
    from manage.tool_manager import ToolManager
    mgr = ToolManager()
    return mgr.search(keyword)

@app.route('/api/tools/<name>/toggle', methods=['POST'])
def api_tools_toggle(name):
    """启用/禁用工具"""
    enabled = request.json.get('enabled', True)
    from manage.tool_manager import ToolManager
    mgr = ToolManager()
    return mgr.toggle(name, enabled)

@app.route('/api/tools/auto-configure', methods=['POST'])
def api_tools_auto():
    """一键自动配置"""
    from manage.tool_manager import ToolManager
    mgr = ToolManager()
    return mgr.auto_configure()


# ═══ 技能管理 API ═══

@app.route('/api/skills', methods=['GET'])
def api_skills_list():
    """列出所有技能"""
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return mgr.list_skills()

@app.route('/api/skills/<name>', methods=['GET'])
def api_skills_read(name):
    """读取技能内容"""
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return mgr.read_skill(name)

@app.route('/api/skills', methods=['POST'])
def api_skills_create():
    """创建新技能"""
    data = request.json
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return mgr.create_skill(data.get('name', ''), data.get('description', ''))

@app.route('/api/skills/<name>', methods=['DELETE'])
def api_skills_delete(name):
    """删除技能"""
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return mgr.delete_skill(name, confirm=True)


# ═══ 记忆管理 API ═══

@app.route('/api/memory', methods=['GET'])
def api_memory_list():
    """列出所有记忆"""
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return mgr.list_daily_memories()

@app.route('/api/memory/search', methods=['GET'])
def api_memory_search():
    """搜索记忆"""
    keyword = request.args.get('q', '')
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return mgr.search_memories(keyword)

@app.route('/api/memory/<filename>', methods=['GET'])
def api_memory_read(filename):
    """读取记忆内容"""
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return mgr.read_memory(filename)

@app.route('/api/memory/<filename>', methods=['DELETE'])
def api_memory_delete(filename):
    """删除记忆"""
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return mgr.delete_memory(filename, confirm=True)

@app.route('/api/memory/stats', methods=['GET'])
def api_memory_stats():
    """记忆统计"""
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return mgr.get_stats()
```

#### 1.3 更新 `/api/status` 返回更多数据

当前 `/api/status` 可能只返回简单的工具名列表。改为返回完整信息：

```python
@app.route('/api/status')
def api_status():
    """Agent 状态（增强版）"""
    from manage.tool_manager import ToolManager
    from manage.skill_manager import SkillManager
    from manage.memory_manager import MemoryManager

    tool_mgr = ToolManager()
    skill_mgr = SkillManager()
    mem_mgr = MemoryManager()

    tools_data = tool_mgr.list_by_category()
    skills_data = skill_mgr.list_skills()
    mem_stats = mem_mgr.get_stats()

    return {
        "status": "ok",
        "tools": tools_data.get("categories", {}),
        "tool_stats": tool_mgr.get_stats(),
        "skills": skills_data.get("skills", []),
        "memory_stats": mem_stats,
    }
```

#### 1.4 验证

```bash
# 启动 Flask
python main.py

# 测试 API
curl http://localhost:8080/api/tools | python -m json.tool
curl http://localhost:8080/api/skills | python -m json.tool
curl http://localhost:8080/api/memory | python -m json.tool
curl http://localhost:8080/api/memory/stats | python -m json.tool
```

---

### 第 2 步：HTML 前端 — 加顶部 Tab 导航

**文件**：`index.html`

#### 2.1 修改 header-center 区域

当前只有两个 Tab：💬 对话、ℹ️ 关于。改为四个：

```html
<div class="header-center">
  <button class="tab-btn active" onclick="switchTab('chat',this)">💬 对话</button>
  <button class="tab-btn" onclick="switchTab('tools',this)">🔧 工具</button>
  <button class="tab-btn" onclick="switchTab('skills',this)">🎯 技能</button>
  <button class="tab-btn" onclick="switchTab('memory',this)">🧠 记忆</button>
  <button class="tab-btn" onclick="switchTab('about',this)">ℹ️ 关于</button>
</div>
```

#### 2.2 修改 `switchTab()` 函数

```javascript
function switchTab(tab, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  // 隐藏所有页面
  document.querySelector('.chat-panel').style.display = 'none';
  document.querySelector('.sidebar-left').style.display = 'none';
  document.querySelector('.panel-right').style.display = 'none';
  document.getElementById('aboutPage').style.display = 'none';
  document.getElementById('toolsPage').style.display = 'none';
  document.getElementById('skillsPage').style.display = 'none';
  document.getElementById('memoryPage').style.display = 'none';

  if (tab === 'chat') {
    document.querySelector('.chat-panel').style.display = 'flex';
    document.querySelector('.sidebar-left').style.display = 'flex';
    document.querySelector('.panel-right').style.display = 'flex';
  } else if (tab === 'about') {
    document.getElementById('aboutPage').style.display = 'block';
  } else if (tab === 'tools') {
    document.getElementById('toolsPage').style.display = 'block';
    loadToolsPage();
  } else if (tab === 'skills') {
    document.getElementById('skillsPage').style.display = 'block';
    loadSkillsPage();
  } else if (tab === 'memory') {
    document.getElementById('memoryPage').style.display = 'block';
    loadMemoryPage();
  }
}
```

---

### 第 3 步：HTML 前端 — 工具管理页

**文件**：`index.html`

在 `</div>`（app 的 closing div）之前、`<div id="aboutPage">` 之前，插入工具管理页：

```html
<!-- ═══════ TOOLS PAGE ═══════ -->
<div id="toolsPage" style="display:none;position:fixed;inset:0;z-index:50;background:var(--bg-primary);overflow-y:auto">
  <div style="max-width:900px;margin:0 auto;padding:40px 32px">
    <!-- 标题栏 -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
      <div>
        <h1 style="font-size:1.5rem;font-weight:700;letter-spacing:-.02em">🔧 工具管理</h1>
        <p style="font-size:.82rem;color:var(--text-secondary);margin-top:4px" id="toolsStats">加载中...</p>
      </div>
      <div style="display:flex;gap:8px">
        <input type="text" class="config-input" id="toolsSearchInput" placeholder="🔍 搜索工具..." style="width:200px" oninput="searchTools(this.value)">
        <button class="btn-ghost" onclick="autoConfigureTools()">🪄 一键自动</button>
      </div>
    </div>
    <!-- 工具分类列表 -->
    <div id="toolsCategoryList"></div>
  </div>
</div>
```

#### 3.1 工具管理页的 JS 逻辑

```javascript
async function loadToolsPage() {
  try {
    const resp = await fetch('/api/tools');
    const data = await resp.json();
    if (!data.success) return;

    // 统计
    const stats = await fetch('/api/tools').then(r => r.json());
    const allTools = Object.values(data.categories).flat();
    const available = allTools.filter(t => t.enabled).length;
    document.getElementById('toolsStats').textContent =
      `${available}/${allTools.length} 可用 · ${allTools.length} 个工具`;

    // 渲染分类
    renderToolsCategories(data.categories);
  } catch (e) {
    document.getElementById('toolsCategoryList').innerHTML =
      '<p style="color:var(--text-tertiary)">⚠️ 无法加载工具列表，请确认 Flask 后端已启动</p>';
  }
}

function renderToolsCategories(categories) {
  const container = document.getElementById('toolsCategoryList');
  container.innerHTML = Object.entries(categories).map(([cat, tools]) => `
    <div style="margin-bottom:20px">
      <div style="font-size:.82rem;font-weight:600;color:var(--text-secondary);margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border)">
        📁 ${cat} (${tools.length})
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px">
        ${tools.map(t => renderToolCard(t)).join('')}
      </div>
    </div>
  `).join('');
}

function renderToolCard(tool) {
  const riskColors = { low: 'var(--success)', medium: 'var(--warning)', high: 'var(--danger)' };
  const riskLabels = { low: '低', medium: '中', high: '高' };
  const riskColor = riskColors[tool.risk_level] || 'var(--text-tertiary)';
  const overrideMark = tool.manually_overridden ? ' ⚡' : '';

  return `
    <div class="stat-card" style="display:flex;align-items:center;gap:12px;padding:12px">
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:6px">
          <span style="font-size:.82rem;font-weight:600;font-family:'SF Mono','Fira Code',monospace">${tool.name}</span>
          ${overrideMark}
          <span style="font-size:.6rem;padding:1px 6px;border-radius:9999px;background:${riskColor}20;color:${riskColor};font-weight:600">${riskLabels[tool.risk_level] || '?'}</span>
        </div>
        <div style="font-size:.72rem;color:var(--text-tertiary);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${tool.description || ''}</div>
      </div>
      <label style="position:relative;display:inline-block;width:44px;height:24px;flex-shrink:0;cursor:pointer">
        <input type="checkbox" ${tool.enabled ? 'checked' : ''} onchange="toggleTool('${tool.name}', this.checked)" style="opacity:0;width:0;height:0">
        <span style="position:absolute;inset:0;background:${tool.enabled ? 'var(--accent)' : 'var(--bg-tertiary)'};border-radius:12px;transition:.3s;border:1px solid var(--border)"></span>
        <span style="position:absolute;top:2px;left:${tool.enabled ? '22px' : '2px'};width:20px;height:20px;background:white;border-radius:50%;transition:.3s;box-shadow:var(--shadow-sm)"></span>
      </label>
    </div>
  `;
}

async function toggleTool(name, enabled) {
  try {
    const resp = await fetch(`/api/tools/${name}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    });
    const data = await resp.json();
    if (data.success) {
      loadToolsPage(); // 刷新
    }
  } catch (e) {
    console.error('切换工具失败:', e);
  }
}

async function searchTools(keyword) {
  if (!keyword.trim()) {
    loadToolsPage();
    return;
  }
  try {
    const resp = await fetch(`/api/tools/search?q=${encodeURIComponent(keyword)}`);
    const data = await resp.json();
    if (data.success) {
      // 搜索结果不分组，直接展示
      const container = document.getElementById('toolsCategoryList');
      container.innerHTML = `
        <div style="font-size:.82rem;color:var(--text-tertiary);margin-bottom:12px">搜索 "${keyword}" — ${data.count} 个结果</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px">
          ${data.tools.map(t => renderToolCard(t)).join('')}
        </div>
      `;
    }
  } catch (e) {}
}

async function autoConfigureTools() {
  try {
    const resp = await fetch('/api/tools/auto-configure', { method: 'POST' });
    const data = await resp.json();
    if (data.success && data.suggest_disable.length > 0) {
      // 批量禁用
      for (const name of data.suggest_disable) {
        await fetch(`/api/tools/${name}/toggle`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: false })
        });
      }
      loadToolsPage();
    }
  } catch (e) {}
}
```

---

### 第 4 步：HTML 前端 — 技能管理页

**文件**：`index.html`

在工具管理页之后插入：

```html
<!-- ═══════ SKILLS PAGE ═══════ -->
<div id="skillsPage" style="display:none;position:fixed;inset:0;z-index:50;background:var(--bg-primary);overflow-y:auto">
  <div style="max-width:900px;margin:0 auto;padding:40px 32px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
      <div>
        <h1 style="font-size:1.5rem;font-weight:700;letter-spacing:-.02em">🎯 技能管理</h1>
        <p style="font-size:.82rem;color:var(--text-secondary);margin-top:4px" id="skillsStats">加载中...</p>
      </div>
      <button class="btn-ghost" onclick="showCreateSkill()">➕ 新建技能</button>
    </div>
    <!-- 新建技能表单（默认隐藏） -->
    <div id="createSkillForm" style="display:none;margin-bottom:20px;padding:16px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:12px">
      <div style="display:flex;gap:8px;align-items:end">
        <div style="flex:1">
          <div class="config-label">技能名称</div>
          <input type="text" class="config-input" id="newSkillName" placeholder="my-skill">
        </div>
        <div style="flex:2">
          <div class="config-label">描述</div>
          <input type="text" class="config-input" id="newSkillDesc" placeholder="技能用途">
        </div>
        <button class="btn-save" style="width:auto;padding:7px 20px" onclick="createSkill()">创建</button>
        <button class="btn-ghost" onclick="hideCreateSkill()">取消</button>
      </div>
    </div>
    <!-- 技能列表 -->
    <div id="skillsList"></div>
  </div>
</div>
```

#### 4.1 技能管理页的 JS 逻辑

```javascript
async function loadSkillsPage() {
  try {
    const resp = await fetch('/api/skills');
    const data = await resp.json();
    if (!data.success) return;

    document.getElementById('skillsStats').textContent = `${data.count} 个技能`;

    const container = document.getElementById('skillsList');
    container.innerHTML = data.skills.map(skill => `
      <div class="stat-card" style="margin-bottom:8px">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <div>
            <div style="font-size:.88rem;font-weight:600">📄 ${skill.name}</div>
            <div style="font-size:.75rem;color:var(--text-tertiary);margin-top:2px">${skill.preview || ''}</div>
            <div style="font-size:.65rem;color:var(--text-tertiary);margin-top:4px">${(skill.size / 1024).toFixed(1)}KB · ${new Date(skill.modified * 1000).toLocaleDateString()}</div>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn-ghost" onclick="viewSkill('${skill.name}')">👁️ 查看</button>
            <button class="btn-ghost" style="color:var(--danger);border-color:var(--danger)" onclick="deleteSkill('${skill.name}')">🗑️ 删除</button>
          </div>
        </div>
        <div id="skillContent_${skill.name}" style="display:none;margin-top:12px;padding:12px;background:var(--bg-tertiary);border-radius:8px;font-size:.82rem;line-height:1.6;white-space:pre-wrap;max-height:400px;overflow-y:auto"></div>
      </div>
    `).join('');
  } catch (e) {
    document.getElementById('skillsList').innerHTML =
      '<p style="color:var(--text-tertiary)">⚠️ 无法加载技能列表</p>';
  }
}

async function viewSkill(name) {
  const el = document.getElementById(`skillContent_${name}`);
  if (el.style.display === 'none') {
    try {
      const resp = await fetch(`/api/skills/${name}`);
      const data = await resp.json();
      if (data.success) {
        el.textContent = data.content;
        el.style.display = 'block';
      }
    } catch (e) {}
  } else {
    el.style.display = 'none';
  }
}

function showCreateSkill() {
  document.getElementById('createSkillForm').style.display = 'block';
}
function hideCreateSkill() {
  document.getElementById('createSkillForm').style.display = 'none';
}

async function createSkill() {
  const name = document.getElementById('newSkillName').value.trim();
  const desc = document.getElementById('newSkillDesc').value.trim();
  if (!name) return;
  try {
    const resp = await fetch('/api/skills', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description: desc })
    });
    const data = await resp.json();
    if (data.success) {
      hideCreateSkill();
      loadSkillsPage();
    }
  } catch (e) {}
}

async function deleteSkill(name) {
  if (!confirm(`确定删除技能 ${name}？`)) return;
  try {
    const resp = await fetch(`/api/skills/${name}`, { method: 'DELETE' });
    const data = await resp.json();
    if (data.success) {
      loadSkillsPage();
    }
  } catch (e) {}
}
```

---

### 第 5 步：HTML 前端 — 记忆管理页

**文件**：`index.html`

在技能管理页之后插入：

```html
<!-- ═══════ MEMORY PAGE ═══════ -->
<div id="memoryPage" style="display:none;position:fixed;inset:0;z-index:50;background:var(--bg-primary);overflow-y:auto">
  <div style="max-width:900px;margin:0 auto;padding:40px 32px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
      <div>
        <h1 style="font-size:1.5rem;font-weight:700;letter-spacing:-.02em">🧠 记忆管理</h1>
        <p style="font-size:.82rem;color:var(--text-secondary);margin-top:4px" id="memoryStats">加载中...</p>
      </div>
      <input type="text" class="config-input" id="memorySearchInput" placeholder="🔍 搜索记忆..." style="width:250px" oninput="searchMemory(this.value)">
    </div>
    <!-- 搜索结果 -->
    <div id="memorySearchResults" style="display:none;margin-bottom:20px"></div>
    <!-- MEMORY.md -->
    <div id="memoryLongTerm" class="stat-card" style="margin-bottom:16px;cursor:pointer" onclick="toggleLongTermMemory()">
      <div style="display:flex;align-items:center;justify-content:space-between">
        <div>
          <div style="font-size:.88rem;font-weight:600">📋 MEMORY.md（长期记忆）</div>
          <div style="font-size:.72rem;color:var(--text-tertiary);margin-top:2px">点击查看</div>
        </div>
      </div>
      <div id="longTermContent" style="display:none;margin-top:12px;padding:12px;background:var(--bg-tertiary);border-radius:8px;font-size:.82rem;line-height:1.6;white-space:pre-wrap;max-height:400px;overflow-y:auto"></div>
    </div>
    <!-- 每日记忆列表 -->
    <div id="memoryDailyList"></div>
  </div>
</div>
```

#### 5.1 记忆管理页的 JS 逻辑

```javascript
async function loadMemoryPage() {
  try {
    // 统计
    const statsResp = await fetch('/api/memory/stats');
    const stats = await statsResp.json();
    if (stats.success) {
      document.getElementById('memoryStats').textContent =
        `${stats.daily_count} 条日记忆 · ${(stats.total_size / 1024).toFixed(1)}KB`;
    }

    // 每日记忆列表
    const resp = await fetch('/api/memory');
    const data = await resp.json();
    if (data.success) {
      const container = document.getElementById('memoryDailyList');
      container.innerHTML = data.memories.map(mem => `
        <div class="stat-card" style="margin-bottom:8px">
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div>
              <div style="font-size:.88rem;font-weight:600">📝 ${mem.name}</div>
              <div style="font-size:.72rem;color:var(--text-tertiary);margin-top:2px">${mem.preview || ''}</div>
              <div style="font-size:.65rem;color:var(--text-tertiary);margin-top:4px">${(mem.size / 1024).toFixed(1)}KB</div>
            </div>
            <div style="display:flex;gap:6px">
              <button class="btn-ghost" onclick="viewMemory('${mem.name}')">👁️ 查看</button>
              <button class="btn-ghost" style="color:var(--danger);border-color:var(--danger)" onclick="deleteMemory('${mem.name}')">🗑️</button>
            </div>
          </div>
          <div id="memContent_${mem.name}" style="display:none;margin-top:12px;padding:12px;background:var(--bg-tertiary);border-radius:8px;font-size:.82rem;line-height:1.6;white-space:pre-wrap;max-height:400px;overflow-y:auto"></div>
        </div>
      `).join('');
    }
  } catch (e) {
    document.getElementById('memoryDailyList').innerHTML =
      '<p style="color:var(--text-tertiary)">⚠️ 无法加载记忆列表</p>';
  }
}

async function toggleLongTermMemory() {
  const el = document.getElementById('longTermContent');
  if (el.style.display === 'none') {
    try {
      const resp = await fetch('/api/memory/MEMORY.md');
      const data = await resp.json();
      if (data.success) {
        el.textContent = data.content;
        el.style.display = 'block';
      }
    } catch (e) {}
  } else {
    el.style.display = 'none';
  }
}

async function viewMemory(filename) {
  const el = document.getElementById(`memContent_${filename}`);
  if (el.style.display === 'none') {
    try {
      const resp = await fetch(`/api/memory/${filename}`);
      const data = await resp.json();
      if (data.success) {
        el.textContent = data.content;
        el.style.display = 'block';
      }
    } catch (e) {}
  } else {
    el.style.display = 'none';
  }
}

async function deleteMemory(filename) {
  if (!confirm(`确定删除记忆文件 ${filename}？`)) return;
  try {
    const resp = await fetch(`/api/memory/${filename}`, { method: 'DELETE' });
    const data = await resp.json();
    if (data.success) {
      loadMemoryPage();
    }
  } catch (e) {}
}

async function searchMemory(keyword) {
  const resultsEl = document.getElementById('memorySearchResults');
  if (!keyword.trim()) {
    resultsEl.style.display = 'none';
    return;
  }
  try {
    const resp = await fetch(`/api/memory/search?q=${encodeURIComponent(keyword)}`);
    const data = await resp.json();
    if (data.success && data.results.length > 0) {
      resultsEl.style.display = 'block';
      resultsEl.innerHTML = `
        <div style="font-size:.82rem;color:var(--text-tertiary);margin-bottom:8px">搜索 "${keyword}" — ${data.file_count} 个文件匹配</div>
        ${data.results.map(r => `
          <div class="stat-card" style="margin-bottom:6px">
            <div style="font-size:.82rem;font-weight:600">📄 ${r.name} (${r.match_count} 处匹配)</div>
            ${r.matches.map(m => `
              <div style="font-size:.72rem;color:var(--text-tertiary);margin-top:2px;padding-left:12px">
                行 ${m.line}: ${escapeHtml(m.text)}
              </div>
            `).join('')}
          </div>
        `).join('')}
      `;
    } else {
      resultsEl.style.display = 'block';
      resultsEl.innerHTML = '<div style="font-size:.82rem;color:var(--text-tertiary)">未找到匹配内容</div>';
    }
  } catch (e) {}
}
```

---

### 第 6 步：验证

#### 6.1 启动 Flask 后端

```bash
cd YI-Agent-V1
python main.py
```

#### 6.2 打开浏览器

```
http://localhost:8080
```

#### 6.3 逐项验证

| 验证项 | 操作 | 期望结果 |
|--------|------|---------|
| Tab 切换 | 点击 🔧🎯🧠 Tab | 页面正确切换，对话功能不受影响 |
| 工具列表 | 点击 🔧 工具 | 显示分类分组的工具列表，有开关 |
| 工具开关 | 切换某个工具的开关 | 状态保存，刷新后保持 |
| 工具搜索 | 输入关键词 | 实时过滤显示 |
| 一键自动 | 点击 🪄 一键自动 | 低频高风险工具被禁用 |
| 技能列表 | 点击 🎯 技能 | 显示所有技能 |
| 技能查看 | 点击 👁️ 查看 | 展开显示 SKILL.md 内容 |
| 技能创建 | 点击 ➕ 新建 → 填写 → 创建 | 新技能目录和 SKILL.md 被创建 |
| 技能删除 | 点击 🗑️ 删除 → 确认 | 技能移到 .trash/ |
| 记忆列表 | 点击 🧠 记忆 | 显示 MEMORY.md + 每日记忆 |
| 记忆搜索 | 输入关键词 | 显示匹配的文件和行 |
| 记忆查看 | 点击 👁️ 查看 | 展开显示记忆内容 |
| 记忆删除 | 点击 🗑️ → 确认 | 记忆移到 .trash/ |
| 对话功能 | 切回 💬 对话 → 发消息 | 正常对话，不受影响 |

---

## 四、文件改动清单

| 文件 | 操作 | 改动内容 |
|------|------|---------|
| `server.py` 或 `main.py` | 修改 | 添加 12 个 `/api/*` 端点 |
| `index.html` | 修改 | 加 3 个管理页 + Tab 导航 + JS 逻辑 |

---

## 五、风险评估

| 风险 | 影响 | 规避 |
|------|------|------|
| Flask 后端没启动 | 管理页加载失败 | 前端有 fallback 提示 |
| manage 层 import 失败 | API 返回错误 | try/except 降级 |
| 工具开关不持久 | 刷新后恢复默认 | ToolDefinition._manual_enabled 是内存态，需要持久化方案（后续迭代） |
| 技能删除不可恢复 | 文件丢失 | 已移到 .trash/，可手动恢复 |

---

## 六、后续迭代（不在本次范围）

1. **工具开关持久化** — 保存到 `config/tools_state.json`，启动时加载
2. **技能在线编辑** — 加 textarea 编辑 SKILL.md 内容
3. **记忆手动添加** — 等 Phase 4 向量检索完成后
4. **实时状态同步** — WebSocket 推送工具/技能变更
