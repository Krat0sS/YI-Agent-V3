"""
YI-Agent — 轻量 Web 服务
为 index.html 提供 API 接口
"""
import os
import sys
import json
import asyncio
import datetime
import threading
import logging
from pathlib import Path

# 配置日志（抓 500 根因）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('yi-agent')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

# ═══ 延迟初始化 Agent ═══
_agent_initialized = False
_registry = None
_skills = []

# ═══ 会话管理（修复：复用 Conversation，避免内存泄漏）═══
_sessions = {}  # session_id → Conversation
_loop = None     # 全局事件循环（修复：asyncio.run 嵌套问题）
_loop_thread = None

def _get_loop():
    """获取全局事件循环（在专用线程中运行）"""
    global _loop, _loop_thread
    if _loop is None or (_loop_thread and not _loop_thread.is_alive()):
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
    return _loop

def _run_async(coro):
    """在线程安全的事件循环中执行异步代码"""
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=180)
    except Exception as e:
        logger.error(f"_run_async 执行失败: {e}", exc_info=True)
        raise

def init_agent():
    global _agent_initialized, _registry, _skills
    if _agent_initialized:
        return
    import config
    from tools.registry import registry, discover_tools
    discover_tools()
    from skills.loader import load_all_skills
    _registry = registry
    _skills = load_all_skills()
    _agent_initialized = True


# ═══ 页面路由 ═══

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# ═══ API 路由 ═══

@app.route('/api/status')
def api_status():
    """获取 Agent 状态"""
    init_agent()
    from manage.tool_manager import ToolManager
    from manage.skill_manager import SkillManager
    from manage.memory_manager import MemoryManager

    tool_mgr = ToolManager(_registry)
    skill_mgr = SkillManager()
    mem_mgr = MemoryManager()

    tools_data = tool_mgr.list_by_category()
    skills_data = skill_mgr.list_skills()
    mem_stats = mem_mgr.get_stats()

    return jsonify({
        'status': 'ok',
        'tools': tools_data.get('categories', {}),
        'tool_stats': tool_mgr.get_stats(),
        'skills': skills_data.get('skills', []),
        'memory_stats': mem_stats,
    })


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """对话接口（修复：复用会话 + 统一事件循环）"""
    init_agent()
    data = request.get_json(force=True)
    message = data.get('message', '').strip()
    session_id = data.get('session_id', 'web-default')

    if not message:
        return jsonify({'error': '消息不能为空'}), 400

    import config
    from core.conversation import Conversation

    try:
        # 复用已有会话（修复：避免每次新建 Conversation 导致内存泄漏）
        if session_id not in _sessions:
            _sessions[session_id] = Conversation(session_id=session_id, restore=True)
        conv = _sessions[session_id]

        progress_log = []

        def on_progress(msg):
            progress_log.append(msg)

        def on_confirm(cmd):
            # Web 模式下默认拒绝高风险操作
            return False

        # 修复：使用统一事件循环，避免 asyncio.run() 嵌套
        result = _run_async(conv.send(
            message,
            on_confirm=on_confirm,
            on_progress=on_progress,
        ))

        response = result.get('response', '(无回复)')
        tool_calls = result.get('tool_calls', [])
        stats = result.get('stats', {})

        result_data = {
            'response': response,
            'reply': response,  # 兼容 channels/webchat.py 的字段名
            'tool_calls': tool_calls,
            'stats': stats,
            '_progress': progress_log,
        }

        return jsonify(result_data)

    except Exception as e:
        # 发生严重错误时移除该会话，下次重新创建
        _sessions.pop(session_id, None)
        logger.error(f"Chat API 错误: {e}", exc_info=True)
        return jsonify({
            'response': f'❌ Agent 执行出错: {str(e)}',
            'tool_calls': [],
            'stats': {},
            '_progress': [],
        }), 500


@app.route('/api/chat/reset', methods=['POST'])
def api_chat_reset():
    """重置会话（修复：前端清空对话时同步清理后端会话）"""
    data = request.get_json(force=True)
    session_id = data.get('session_id', 'web-default')
    conv = _sessions.pop(session_id, None)
    if conv:
        try:
            _run_async(conv.cleanup())
        except Exception:
            pass
    return jsonify({'success': True})


@app.route('/api/chat/history')
def api_chat_history():
    """获取会话历史"""
    session_id = request.args.get('session_id', 'web-default')
    conv = _sessions.get(session_id)
    if not conv:
        return jsonify({'success': True, 'messages': []})
    try:
        history = getattr(conv, 'messages', []) or getattr(conv, '_messages', [])
        messages = []
        for msg in history:
            if isinstance(msg, dict):
                messages.append({
                    'role': msg.get('role', 'unknown'),
                    'content': msg.get('content', ''),
                })
        return jsonify({'success': True, 'messages': messages})
    except Exception as e:
        return jsonify({'success': True, 'messages': [], 'error': str(e)})


@app.route('/api/sessions')
def api_sessions_list():
    """列出所有活跃会话"""
    sessions = []
    for sid, conv in _sessions.items():
        msg_count = len(getattr(conv, 'messages', []))
        sessions.append({
            'session_id': sid,
            'message_count': msg_count,
            'created': getattr(conv, '_created', None),
        })
    return jsonify({'success': True, 'sessions': sessions})


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def api_sessions_delete(session_id):
    """删除指定会话"""
    conv = _sessions.pop(session_id, None)
    if conv:
        try:
            _run_async(conv.cleanup())
        except Exception:
            pass
        return jsonify({'success': True, 'message': f'会话 {session_id} 已删除'})
    return jsonify({'success': False, 'error': '会话不存在'}), 404


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.datetime.now().isoformat()})


@app.route('/api/settings', methods=['GET'])
def api_settings_get():
    """获取当前后端配置（不暴露完整 key）"""
    import config
    api_key = os.environ.get('LLM_API_KEY', '')
    base_url = os.environ.get('LLM_BASE_URL', '')
    model = os.environ.get('LLM_MODEL', 'deepseek-chat')
    return jsonify({
        'success': True,
        'settings': {
            'apiKey': api_key[:8] + '***' if len(api_key) > 8 else '',
            'apiKeySet': bool(api_key),
            'baseUrl': base_url,
            'model': model,
        }
    })


@app.route('/api/settings', methods=['PUT'])
def api_settings_update():
    """更新后端配置（写入 .env 文件）"""
    data = request.get_json(force=True)
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        # 读取现有 .env
        lines = []
        if os.path.isfile(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        # 更新字段
        updates = {}
        if 'apiKey' in data and data['apiKey']:
            updates['LLM_API_KEY'] = data['apiKey']
        if 'baseUrl' in data:
            updates['LLM_BASE_URL'] = data['baseUrl']
        if 'model' in data:
            updates['LLM_MODEL'] = data['model']

        # 写入 .env
        new_lines = []
        found_keys = set()
        for line in lines:
            key = line.split('=')[0].strip() if '=' in line else ''
            if key in updates:
                new_lines.append(f'{key}={updates[key]}\n')
                found_keys.add(key)
            else:
                new_lines.append(line)
        for key, val in updates.items():
            if key not in found_keys:
                new_lines.append(f'{key}={val}\n')

        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        # 更新环境变量（立即生效）
        for key, val in updates.items():
            os.environ[key] = val

        # 重新加载配置模块 + 重置 LLM 客户端（让新 key 立即生效）
        try:
            import config as _config
            _config.reload_config()
            import core.llm as _llm
            _llm.reset_client()
        except Exception as reload_err:
            logger.warning(f"配置热重载失败（重启后端可解决）: {reload_err}")

        return jsonify({'success': True, 'message': '配置已保存并立即生效'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════
# 工具管理 API
# ═══════════════════════════════════════════════════

@app.route('/api/tools')
def api_tools_list():
    """列出所有工具（按分类分组）"""
    init_agent()
    from manage.tool_manager import ToolManager
    mgr = ToolManager(_registry)
    return jsonify(mgr.list_by_category())


@app.route('/api/tools/search')
def api_tools_search():
    """搜索工具"""
    keyword = request.args.get('q', '')
    init_agent()
    from manage.tool_manager import ToolManager
    mgr = ToolManager(_registry)
    return jsonify(mgr.search(keyword))


@app.route('/api/tools/<name>/toggle', methods=['POST'])
def api_tools_toggle(name):
    """启用/禁用工具"""
    init_agent()
    data = request.get_json(force=True)
    enabled = data.get('enabled', True)
    from manage.tool_manager import ToolManager
    mgr = ToolManager(_registry)
    return jsonify(mgr.toggle(name, enabled))


@app.route('/api/tools/auto-configure', methods=['POST'])
def api_tools_auto():
    """一键自动配置"""
    init_agent()
    from manage.tool_manager import ToolManager
    mgr = ToolManager(_registry)
    return jsonify(mgr.auto_configure())


# ═══════════════════════════════════════════════════
# 技能管理 API
# ═══════════════════════════════════════════════════

@app.route('/api/skills')
def api_skills_list():
    """列出所有技能"""
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return jsonify(mgr.list_skills())


@app.route('/api/skills/<name>')
def api_skills_read(name):
    """读取技能内容"""
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return jsonify(mgr.read_skill(name))


@app.route('/api/skills/<name>', methods=['PUT'])
def api_skills_update(name):
    """更新技能内容"""
    data = request.get_json(force=True)
    content = data.get('content', '')
    if not content:
        return jsonify({'success': False, 'error': '内容不能为空'}), 400
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return jsonify(mgr.update_skill(name, content))


@app.route('/api/skills', methods=['POST'])
def api_skills_create():
    """创建新技能"""
    data = request.get_json(force=True)
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return jsonify(mgr.create_skill(data.get('name', ''), data.get('description', '')))


@app.route('/api/skills/<name>', methods=['DELETE'])
def api_skills_delete(name):
    """删除技能"""
    from manage.skill_manager import SkillManager
    mgr = SkillManager()
    return jsonify(mgr.delete_skill(name, confirm=True))


# ═══════════════════════════════════════════════════
# 记忆管理 API
# ═══════════════════════════════════════════════════

@app.route('/api/memory')
def api_memory_list():
    """列出所有记忆"""
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return jsonify(mgr.list_daily_memories())


@app.route('/api/memory/search')
def api_memory_search():
    """搜索记忆"""
    keyword = request.args.get('q', '')
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return jsonify(mgr.search_memories(keyword))


@app.route('/api/memory/stats')
def api_memory_stats():
    """记忆统计"""
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return jsonify(mgr.get_stats())


@app.route('/api/memory/<filename>')
def api_memory_read(filename):
    """读取记忆内容"""
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return jsonify(mgr.read_memory(filename))


@app.route('/api/memory', methods=['POST'])
def api_memory_create():
    """新建记忆文件"""
    data = request.get_json(force=True)
    filename = data.get('filename', '').strip()
    content = data.get('content', '')
    if not filename:
        return jsonify({'success': False, 'error': '文件名不能为空'}), 400
    if not filename.endswith('.md'):
        filename += '.md'
    # 安全检查：只允许 memory/ 目录下的文件
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'success': False, 'error': '非法文件名'}), 400
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    import os
    fpath = os.path.join(mgr.memory_dir, filename)
    if os.path.exists(fpath):
        return jsonify({'success': False, 'error': f'文件已存在: {filename}'}), 409
    try:
        os.makedirs(mgr.memory_dir, exist_ok=True)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True, 'name': filename, 'path': fpath})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/memory/<filename>', methods=['PUT'])
def api_memory_update(filename):
    """更新记忆内容"""
    data = request.get_json(force=True)
    content = data.get('content', '')
    if filename == 'MEMORY.md':
        return jsonify({'success': False, 'error': '不能通过 API 编辑 MEMORY.md'}), 403
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'success': False, 'error': '非法文件名'}), 400
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    import os, shutil
    from datetime import datetime
    fpath = os.path.join(mgr.memory_dir, filename)
    if not os.path.isfile(fpath):
        return jsonify({'success': False, 'error': f'文件不存在: {filename}'}), 404
    try:
        # 备份
        trash_dir = os.path.join(mgr.memory_dir, '.trash')
        os.makedirs(trash_dir, exist_ok=True)
        backup = os.path.join(trash_dir, f'{filename}.{datetime.now().strftime("%Y%m%d%H%M%S")}.bak')
        shutil.copy2(fpath, backup)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True, 'name': filename, 'backup': backup})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/memory/<filename>', methods=['DELETE'])
def api_memory_delete(filename):
    """删除记忆"""
    from manage.memory_manager import MemoryManager
    mgr = MemoryManager()
    return jsonify(mgr.delete_memory(filename, confirm=True))


# ═══════════════════════════════════════════════════
# 权限管理 API（前端「权限」页面调用）
# ═══════════════════════════════════════════════════

_PERMISSIONS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'permissions.json')

def _load_permissions() -> dict:
    """从文件加载权限配置"""
    try:
        if os.path.isfile(_PERMISSIONS_FILE):
            with open(_PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {
        'toolWhitelist': [],
        'toolBlacklist': [],
        'skillWhitelist': [],
        'skillBlacklist': [],
        'riskTolerance': 1.0,
    }

def _save_permissions(perm: dict):
    """保存权限配置到文件"""
    os.makedirs(os.path.dirname(_PERMISSIONS_FILE), exist_ok=True)
    with open(_PERMISSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(perm, f, ensure_ascii=False, indent=2)

@app.route('/api/permissions', methods=['GET'])
def api_permissions_get():
    """获取权限配置"""
    return jsonify({'success': True, 'permissions': _load_permissions()})

@app.route('/api/permissions', methods=['PUT'])
def api_permissions_put():
    """更新权限配置"""
    try:
        data = request.get_json(force=True)
        # 校验字段
        perm = {
            'toolWhitelist': data.get('toolWhitelist', []),
            'toolBlacklist': data.get('toolBlacklist', []),
            'skillWhitelist': data.get('skillWhitelist', []),
            'skillBlacklist': data.get('skillBlacklist', []),
            'riskTolerance': float(data.get('riskTolerance', 1.0)),
        }
        _save_permissions(perm)
        logger.info(f"权限已更新: riskTolerance={perm['riskTolerance']}")
        return jsonify({'success': True, 'message': '权限已保存'})
    except Exception as e:
        logger.error(f"保存权限失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()

    print(f'\n🤖 YI-Agent v4 Web 服务启动')
    print(f'   地址: http://localhost:{args.port}')
    print(f'   API:  http://localhost:{args.port}/api/chat')
    print(f'   健康: http://localhost:{args.port}/api/health')
    print()

    app.run(host=args.host, port=args.port, debug=False)
