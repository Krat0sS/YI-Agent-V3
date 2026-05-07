"""配置"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件 — 显式指定路径，不依赖 cwd
_project_dir = Path(__file__).parent.resolve()
_env_file = _project_dir / ".env"
load_dotenv(_env_file)

# LLM
# 内置默认 Key（用户可在 .env 中覆盖）
_DEFAULT_KEY = "your-api-key-here"  # 请在 .env 中设置 LLM_API_KEY

def _read_llm_key():
    """从环境变量读取 API Key，过滤占位符"""
    _env_key = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    return _env_key if (_env_key and not _env_key.startswith("your-")) else _DEFAULT_KEY

LLM_API_KEY = _read_llm_key()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


def reload_config():
    """重新加载配置（前端修改 .env 后调用）"""
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    global OLLAMA_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL
    # 重新加载 .env 文件
    load_dotenv(_env_file, override=True)
    LLM_API_KEY = _read_llm_key()
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
    OLLAMA_ENABLED = os.environ.get("OLLAMA_ENABLED", "false").lower() == "true"
    OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "modelscope.cn/qwen/Qwen2.5-7B-Instruct-GGUF:latest")
    print(f"[CONFIG] 已重新加载 | Key: {LLM_API_KEY[:8]}*** | Model: {LLM_MODEL}")

# 启动时打印 key 状态（脱敏）
_key_masked = LLM_API_KEY[:8] + "***" if len(LLM_API_KEY) > 8 else "(未设置)"
print(f"[CONFIG] API Key: {_key_masked} | Base URL: {LLM_BASE_URL} | Model: {LLM_MODEL}")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "16384"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "30"))

# Agent
AGENT_NAME = os.environ.get("AGENT_NAME", "Claw")
WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.my-agent/workspace"))
MEMORY_DIR = os.path.join(WORKSPACE, "memory")
MEMORY_FILE = os.path.join(WORKSPACE, "MEMORY.md")
SOUL_FILE = os.path.join(WORKSPACE, "SOUL.md")
LEARNED_PARAMS_FILE = os.path.join(WORKSPACE, "learned_params.json")

# Web Server
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))

# Safety
MAX_TOOL_CALLS_PER_TURN = 8  # 正常任务 3-5 步足够，浏览器复杂操作可到 8
# 已开放全部权限 — 命令拦截和确认全部禁用
BLOCKED_COMMANDS = []

CONFIRM_COMMANDS = [
    "playwright install",   # 浏览器安装太慢，不应在对话中执行
    "npx playwright install",
]

# 上下文管理
MAX_CONTEXT_TURNS = 20

# 工具超时
TOOL_TIMEOUT = float(os.environ.get("TOOL_TIMEOUT", "30"))

# 工具缓存
TOOL_CACHE_TTL = 60

# 会话持久化
SESSIONS_DIR = os.path.join(WORKSPACE, "sessions")

# ═══ Ollama 本地模型（第二层漏斗） ═══
OLLAMA_ENABLED = os.environ.get("OLLAMA_ENABLED", "false").lower() == "true"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "modelscope.cn/qwen/Qwen2.5-7B-Instruct-GGUF:latest")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "10"))
OLLAMA_MAX_TOKENS = int(os.environ.get("OLLAMA_MAX_TOKENS", "4096"))

# Vision 模型
VISION_API_KEY = os.environ.get("VISION_API_KEY", "")
VISION_BASE_URL = os.environ.get("VISION_BASE_URL", "")
VISION_MODEL = os.environ.get("VISION_MODEL", "")

# 浏览器安全
ALLOWED_BROWSER_DOMAINS = [
    "github.com", "arxiv.org", "docs.python.org",
    "docs.github.com", "stackoverflow.com", "localhost", "127.0.0.1",
]
ALLOWED_BROWSER_WRITE_DOMAINS = []

# ═══ 安全配置（Phase 1） ═══
# 已开放全部权限，安全层全部禁用
SECURITY_ENABLED = False
SECURITY_RATE_WINDOW = int(os.environ.get("SECURITY_RATE_WINDOW", "30"))
SECURITY_RATE_MAX_OPS = int(os.environ.get("SECURITY_RATE_MAX_OPS", "9999"))
