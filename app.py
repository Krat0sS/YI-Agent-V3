"""
YI-Agent V4 — Streamlit 控制台
"""
import streamlit as st
import asyncio
import os
import sys
import time
import importlib
from pathlib import Path
from dotenv import load_dotenv, set_key

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

# ═══ 工具函数 ═══

def async_run(coro):
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as executor:
                return executor.submit(asyncio.run, coro).result(timeout=120)
    except RuntimeError:
        return asyncio.run(coro)

@st.cache_resource
def init_agent_cached():
    import config
    from tools.registry import registry, discover_tools
    discover_tools()
    from skills.loader import load_all_skills
    skills = load_all_skills()
    return registry, skills

async def run_agent(message, api_key, api_base, model, session_id="gui"):
    os.environ["LLM_API_KEY"] = api_key
    os.environ["LLM_BASE_URL"] = api_base
    os.environ["LLM_MODEL"] = model
    import config
    importlib.reload(config)
    import core.llm as llm_module
    llm_module._client = None
    from core.conversation import Conversation
    conv = Conversation(session_id=session_id, restore=False)
    progress_log = []
    def on_progress(msg):
        progress_log.append(msg)
    def on_confirm(cmd):
        progress_log.append(f"⚠️ 高风险操作被拦截: {cmd}")
        return False
    result = await conv.send(message, on_confirm=on_confirm, on_progress=on_progress)
    response = result.get("response", "Agent 没有返回回复。")
    tool_calls = result.get("tool_calls", [])
    stats = result.get("stats", {})
    if progress_log:
        response = "\n".join(f"  {p}" for p in progress_log) + "\n\n" + response
    await conv.cleanup()
    return response, tool_calls, stats


# ═══ 页面配置 ═══

st.set_page_config(
    page_title="YI-Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══ 全局样式 ═══

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap');

/* ── Reset ── */
* { font-family: 'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif; }
section[data-testid="stMain"] { background: #0a0a0c; }

/* ── Sidebar ── */
div[data-testid="stSidebar"] {
    background: #141416;
    border-right: 1px solid rgba(255,255,255,0.06);
    padding-top: 1rem;
}
div[data-testid="stSidebar"] > div { padding: 0 1rem; }

/* Sidebar 标题 */
div[data-testid="stSidebar"] h1 {
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    color: #f5f5f7 !important;
    letter-spacing: -0.03em;
    margin-bottom: 0 !important;
}
div[data-testid="stSidebar"] h3 {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    color: #636366 !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 1.2rem !important;
    margin-bottom: 0.4rem !important;
}
div[data-testid="stSidebar"] p { color: #a1a1a6; font-size: 0.82rem; }
div[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.06) !important; margin: 0.8rem 0; }

/* Sidebar 输入框 */
div[data-testid="stSidebar"] .stTextInput input {
    background: #0a0a0c !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
    color: #f5f5f7 !important;
    font-size: 0.82rem !important;
    padding: 0.45rem 0.7rem !important;
}
div[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: #0a84ff !important;
    box-shadow: 0 0 0 2px rgba(10,132,255,0.15) !important;
}
div[data-testid="stSidebar"] .stTextInput label {
    font-size: 0.72rem !important;
    color: #636366 !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

/* Sidebar Select */
div[data-testid="stSidebar"] .stSelectbox label {
    font-size: 0.72rem !important;
    color: #636366 !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
div[data-testid="stSidebar"] .stSelectbox > div > div {
    background: #0a0a0c !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
    color: #f5f5f7 !important;
    font-size: 0.82rem !important;
}

/* Sidebar 按钮 */
div[data-testid="stSidebar"] .stButton > button {
    background: #1c1c1e !important;
    color: #a1a1a6 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    padding: 0.4rem 0.8rem !important;
    transition: all 0.15s;
}
div[data-testid="stSidebar"] .stButton > button:hover {
    background: #2c2c2e !important;
    color: #f5f5f7 !important;
    border-color: rgba(255,255,255,0.15) !important;
}

/* Sidebar 导航 */
div[data-testid="stSidebar"] .stRadio > div {
    display: flex;
    gap: 2px;
    background: #0a0a0c;
    border-radius: 8px;
    padding: 3px;
}
div[data-testid="stSidebar"] .stRadio > div > label {
    background: transparent !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 0.4rem 0.6rem !important;
    font-size: 0.75rem !important;
    color: #636366 !important;
    font-weight: 500;
    transition: all 0.15s;
}
div[data-testid="stSidebar"] .stRadio > div > label:hover { color: #a1a1a6 !important; }
div[data-testid="stSidebar"] .stRadio > div > label[data-checked="true"] {
    background: #1c1c1e !important;
    color: #f5f5f7 !important;
}

/* Sidebar Toggle */
div[data-testid="stSidebar"] .stToggle label { font-size: 0.75rem !important; color: #a1a1a6 !important; }

/* Sidebar Alert */
div[data-testid="stSidebar"] .stAlert {
    border-radius: 8px !important;
    border: none !important;
    font-size: 0.78rem !important;
    padding: 0.5rem 0.7rem !important;
}
div[data-testid="stSidebar"] .stSuccess { background: rgba(48,209,88,0.1) !important; color: #30d158 !important; }
div[data-testid="stSidebar"] .stWarning { background: rgba(255,159,10,0.1) !important; color: #ff9f0a !important; }
div[data-testid="stSidebar"] .stError { background: rgba(255,69,58,0.1) !important; color: #ff453a !important; }

/* ── Main Area ── */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 4rem !important;
    max-width: 860px;
}
h1, h2, h3, h4 { color: #f5f5f7 !important; letter-spacing: -0.02em; }
p, li { color: #a1a1a6; }
.stCaption { color: #636366 !important; }

/* ── Chat Messages ── */
.stChatMessage {
    border-radius: 12px !important;
    padding: 1rem 1.2rem !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    background: #141416 !important;
    box-shadow: none !important;
    margin: 0.5rem 0 !important;
}
div[data-testid="stChatMessage"][data-testid-type="user"] {
    background: #1c1c1e !important;
    border-color: rgba(255,255,255,0.08) !important;
}
div[data-testid="stChatMessage"][data-testid-type="assistant"] {
    background: #141416 !important;
}

/* ── Chat Input ── */
.stChatInput > div {
    background: #141416 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
}
.stChatInput > div:focus-within {
    border-color: #0a84ff !important;
    box-shadow: 0 0 0 2px rgba(10,132,255,0.12) !important;
}
.stChatInput textarea { color: #f5f5f7 !important; }

/* ── Expander ── */
.stExpander {
    background: #141416 !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 10px !important;
}
.stExpander summary { color: #a1a1a6 !important; font-size: 0.82rem; }

/* ── Metric Cards ── */
div[data-testid="stMetric"] {
    background: #141416;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    padding: 1rem;
}
div[data-testid="stMetric"] label {
    color: #636366 !important;
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #f5f5f7 !important;
    font-size: 1.3rem !important;
    font-weight: 600;
}

/* ── Alerts ── */
.stAlert { border-radius: 8px !important; border: none !important; font-size: 0.82rem; }
.stSuccess { background: rgba(48,209,88,0.08) !important; color: #30d158 !important; }
.stWarning { background: rgba(255,159,10,0.08) !important; color: #ff9f0a !important; }
.stError { background: rgba(255,69,58,0.08) !important; color: #ff453a !important; }
.stInfo { background: rgba(10,132,255,0.08) !important; color: #0a84ff !important; }

/* ── Primary Button ── */
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {
    background: #0a84ff !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.82rem;
}
.stButton > button[kind="primary"]:hover { background: #0077ed !important; }

/* ── Spinner ── */
.stSpinner > div { border-top-color: #0a84ff !important; }

/* ── Columns gap ── */
div[data-testid="stHorizontalBlock"] { gap: 0.8rem !important; }

/* ── Text Area (readonly) ── */
div[data-testid="stSidebar"] .stTextArea textarea {
    background: #0a0a0c !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 8px !important;
    color: #a1a1a6 !important;
    font-size: 0.78rem !important;
    line-height: 1.6;
}
</style>
""", unsafe_allow_html=True)


# ═══ 会话状态 ═══

if "messages" not in st.session_state:
    st.session_state.messages = []

try:
    registry, skills = init_agent_cached()
    agent_ready = True
except Exception:
    registry, skills = None, []
    agent_ready = False


# ═══ 侧边栏 ═══

with st.sidebar:
    st.markdown("# ⚡ YI-Agent")
    st.caption("V4 · 态势感知 AI Agent")
    st.markdown("---")

    page = st.radio(
        "导航",
        ["💬 对话", "🧠 记忆", "🎯 技能", "🔧 工具"],
        label_visibility="collapsed",
        horizontal=True,
    )
    st.markdown("---")

    # ─── 对话页 ───
    if page == "💬 对话":
        st.markdown("### API 配置")

        saved_key = os.getenv("LLM_API_KEY", "")
        saved_base = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        saved_model = os.getenv("LLM_MODEL", "deepseek-chat")

        api_key = st.text_input("API Key", type="password", value=saved_key, placeholder="sk-...")
        api_base = st.text_input("Base URL", value=saved_base)

        model_map = {
            "deepseek-chat": "DeepSeek",
            "deepseek-v4-pro": "DeepSeek V4 Pro",
            "deepseek-reasoner": "DeepSeek Reasoner",
            "gpt-4o": "GPT-4o",
            "gpt-4o-mini": "GPT-4o Mini",
        }
        model_options = list(model_map.keys())
        model_index = model_options.index(saved_model) if saved_model in model_options else 0
        model = st.selectbox("模型", model_options, format_func=lambda x: model_map.get(x, x), index=model_index)

        if api_key != saved_key or api_base != saved_base or model != saved_model:
            env_path = Path(".env")
            if not env_path.exists():
                env_path.touch()
            if api_key:
                set_key(str(env_path), "LLM_API_KEY", api_key)
            set_key(str(env_path), "LLM_BASE_URL", api_base)
            set_key(str(env_path), "LLM_MODEL", model)
            os.environ["LLM_API_KEY"] = api_key
            os.environ["LLM_BASE_URL"] = api_base
            os.environ["LLM_MODEL"] = model

        if api_key:
            st.success(f"✓ {model_map.get(model, model)}")
        else:
            st.warning("请输入 API Key")

    # ─── 记忆页 ───
    elif page == "🧠 记忆":
        st.markdown("### 记忆管理")
        from manage.memory_manager import MemoryManager
        mem_mgr = MemoryManager()

        search_kw = st.text_input("搜索", placeholder="关键词...")
        if search_kw:
            result = mem_mgr.search_memories(search_kw)
            if result["success"] and result["results"]:
                for r in result["results"]:
                    with st.expander(f"{r['name']} ({r['match_count']} 匹配)"):
                        for m in r["matches"]:
                            st.caption(f"行 {m['line']}: {m['text']}")
            else:
                st.info("未找到")
        else:
            stats = mem_mgr.get_stats()
            if stats["success"]:
                st.caption(f"{stats['daily_count']} 条日记忆 · {stats['total_size']//1024}KB")

            lt = mem_mgr.read_memory("MEMORY.md")
            if lt["success"]:
                with st.expander("MEMORY.md"):
                    st.text_area("", lt["content"][:2000], height=120, disabled=True, key="lt_mem")

            daily = mem_mgr.list_daily_memories()
            if daily["success"]:
                for mem in daily["memories"]:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        with st.expander(mem['name']):
                            content = mem_mgr.read_memory(mem['name'])
                            if content["success"]:
                                st.text_area("", content["content"][:2000], height=120, disabled=True, key=f"mem_{mem['name']}")
                    with col2:
                        if st.button("🗑️", key=f"del_{mem['name']}", help="删除"):
                            st.session_state[f"cdel_{mem['name']}"] = True
                            st.rerun()
                    if st.session_state.get(f"cdel_{mem['name']}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("确认", key=f"y_{mem['name']}"):
                                mem_mgr.delete_memory(mem['name'], confirm=True)
                                st.session_state.pop(f"cdel_{mem['name']}", None)
                                st.rerun()
                        with c2:
                            if st.button("取消", key=f"n_{mem['name']}"):
                                st.session_state.pop(f"cdel_{mem['name']}", None)
                                st.rerun()

    # ─── 技能页 ───
    elif page == "🎯 技能":
        st.markdown("### 技能管理")
        from manage.skill_manager import SkillManager
        skill_mgr = SkillManager()

        with st.expander("新建技能"):
            new_name = st.text_input("名称", placeholder="my-skill")
            new_desc = st.text_input("描述", placeholder="用途")
            if st.button("创建", key="mk_skill"):
                if new_name:
                    result = skill_mgr.create_skill(new_name, new_desc)
                    if result["success"]:
                        st.success(f"「{new_name}」已创建")
                        st.rerun()
                    else:
                        st.error(result["error"])

        result = skill_mgr.list_skills()
        if result["success"]:
            st.caption(f"{result['count']} 个技能")
            for skill in result["skills"]:
                with st.expander(skill['name']):
                    st.caption(skill['preview'])
                    content = skill_mgr.read_skill(skill['name'])
                    if content["success"]:
                        st.text_area("", content["content"][:3000], height=160, disabled=True, key=f"sk_{skill['name']}")
                    if st.button("删除", key=f"dsk_{skill['name']}"):
                        skill_mgr.delete_skill(skill['name'], confirm=True)
                        st.rerun()

    # ─── 工具页 ───
    elif page == "🔧 工具":
        st.markdown("### 工具管理")
        from manage.tool_manager import ToolManager
        tool_mgr = ToolManager()

        tool_search = st.text_input("搜索", placeholder="工具名...")
        if tool_search:
            result = tool_mgr.search(tool_search)
            if result["success"]:
                for t in result["tools"]:
                    risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(t["risk_level"], "⚪")
                    st.markdown(f"{risk_icon} `{t['name']}` — {t['description'][:40]}")

        st.markdown("---")

        if st.button("一键自动配置", use_container_width=True):
            result = tool_mgr.auto_configure()
            if result["success"]:
                if result["suggest_disable"]:
                    for name in result["suggest_disable"]:
                        tool_mgr.toggle(name, False)
                    st.success(f"已禁用 {len(result['suggest_disable'])} 个工具")
                else:
                    st.info("配置合理")
                st.rerun()

        result = tool_mgr.list_by_category()
        if result["success"]:
            stats = tool_mgr.get_stats()
            st.caption(f"{stats['available']}/{stats['total']} 可用 · {stats['by_risk'].get('high', 0)} 高风险")

            for category, tools in result["categories"].items():
                with st.expander(f"{category} ({len(tools)})"):
                    for t in tools:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(t["risk_level"], "⚪")
                            st.markdown(f"{risk_icon} `{t['name']}`")
                            st.caption(t["description"][:50])
                        with col2:
                            new_state = st.toggle("启用", value=t["enabled"], key=f"tool_{t['name']}")
                            if new_state != t["enabled"]:
                                tool_mgr.toggle(t["name"], new_state)
                                st.rerun()

    # ─── 底部状态 ───
    st.markdown("---")
    if agent_ready:
        st.caption(f"{registry.available_count()} 工具 · {len(skills)} 技能")
    else:
        st.caption("Agent 未就绪")


# ═══ 主区域 ═══

# 对话消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tool_calls"):
            with st.expander(f"工具调用 ({len(msg['tool_calls'])} 次)", expanded=False):
                for tc in msg["tool_calls"]:
                    st.markdown(f"{'❌' if tc.get('error') else '✅'} `{tc.get('tool', '?')}` — {tc.get('elapsed_ms', 0)}ms")
        if msg.get("stats") and msg["stats"].get("total_tokens", 0) > 0:
            s = msg["stats"]
            st.caption(f"{s.get('total_tokens', 0)} tokens · {s.get('tool_calls_count', 0)} 次调用 · ¥{s.get('estimated_cost_cny', 0):.4f}")

# 输入
if prompt := st.chat_input("说点什么..."):
    current_key = os.getenv("LLM_API_KEY", "")
    if not current_key:
        st.error("请先在侧边栏配置 API Key")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            start_time = time.time()
            try:
                response, tool_calls, stats = async_run(run_agent(
                    prompt,
                    api_key=os.getenv("LLM_API_KEY", ""),
                    api_base=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
                    model=os.getenv("LLM_MODEL", "deepseek-chat"),
                ))
                elapsed = time.time() - start_time
                response += f"\n\n⏱ {elapsed:.1f}s"
            except Exception as e:
                response = f"❌ {str(e)}"
                tool_calls, stats = [], {}
        st.markdown(response)
        if tool_calls:
            with st.expander(f"工具调用 ({len(tool_calls)} 次)", expanded=False):
                for tc in tool_calls:
                    st.markdown(f"{'❌' if tc.get('error') else '✅'} `{tc.get('tool', '?')}` — {tc.get('elapsed_ms', 0)}ms")
        if stats and stats.get("total_tokens", 0) > 0:
            st.caption(f"{stats.get('total_tokens', 0)} tokens · ¥{stats.get('estimated_cost_cny', 0):.4f}")

    st.session_state.messages.append({"role": "assistant", "content": response, "tool_calls": tool_calls, "stats": stats})

# 底部操作
col1, col2, _ = st.columns([1, 1, 4])
with col1:
    if st.button("清空对话"):
        st.session_state.messages = []
        st.rerun()
with col2:
    if st.button("重置会话"):
        import config
        sf = os.path.join(config.SESSIONS_DIR, "gui.json")
        if os.path.exists(sf):
            os.remove(sf)
        st.session_state.messages = []
        st.rerun()
