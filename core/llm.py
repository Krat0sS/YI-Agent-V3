"""LLM 客户端 — async 版本，双客户端（Ollama 本地 + DeepSeek 云端）"""
import json
import asyncio
import time as _time
from openai import AsyncOpenAI
import config

# ═══ 云端客户端（DeepSeek） ═══
_cloud_client = None

# ═══ Ollama 失败冷却 ═══
_ollama_fail_count = 0
_ollama_cooldown_until = 0
_OLLAMA_COOLDOWN_SECONDS = 300  # 连续失败后冷却 5 分钟

def get_client() -> AsyncOpenAI:
    """获取云端 LLM 客户端（DeepSeek）"""
    global _cloud_client
    if _cloud_client is None:
        _cloud_client = AsyncOpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT,
        )
    return _cloud_client


def reset_client():
    """重置 LLM 客户端（API Key 变更后调用）"""
    global _cloud_client, _ollama_client
    _cloud_client = None
    _ollama_client = None


# ═══ 本地客户端（Ollama） ═══
_ollama_client = None

def get_ollama_client() -> AsyncOpenAI:
    """获取 Ollama 本地客户端（OpenAI 兼容格式）"""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = AsyncOpenAI(
            api_key="ollama",  # Ollama 不需要真实 key
            base_url=config.OLLAMA_BASE_URL,
            timeout=config.OLLAMA_TIMEOUT,
        )
    return _ollama_client


def is_ollama_available() -> bool:
    """检查 Ollama 是否启用且可用（含失败冷却）"""
    if not config.OLLAMA_ENABLED:
        return False
    global _ollama_cooldown_until
    if _time.time() < _ollama_cooldown_until:
        return False
    try:
        import httpx
        resp = httpx.get(
            f"{config.OLLAMA_BASE_URL.replace('/v1', '')}/api/tags",
            timeout=2.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


# ═══ 统一聊天接口 ═══

async def chat(messages: list[dict], tools: list[dict] = None,
               temperature: float = None, timeout: float = None,
               use_ollama: bool = False) -> dict:
    """
    统一 LLM 聊天接口（用户无感切换）。

    use_ollama=True  → 优先走 Ollama 本地，失败自动降级到 DeepSeek
    use_ollama=False → 直接走 DeepSeek 云端

    用户永远不知道后面用的是哪个模型。
    """
    global _ollama_fail_count, _ollama_cooldown_until

    if use_ollama and config.OLLAMA_ENABLED:
        # 冷却期内直接跳过 Ollama
        if _time.time() < _ollama_cooldown_until:
            return await _chat_cloud(messages, tools, temperature, timeout)

        result = await _chat_ollama(messages, tools, temperature, timeout)
        # Ollama 调用失败 → 累计失败次数，连续 3 次后冷却
        if result.get("_error") or result.get("_timeout"):
            _ollama_fail_count += 1
            if _ollama_fail_count >= 3:
                _ollama_cooldown_until = _time.time() + _OLLAMA_COOLDOWN_SECONDS
                print(f"[LLM] Ollama 连续 {_ollama_fail_count} 次失败，冷却 {_OLLAMA_COOLDOWN_SECONDS}s")
            return await _chat_cloud(messages, tools, temperature, timeout)
        else:
            _ollama_fail_count = 0  # 成功则重置计数
        return result
    return await _chat_cloud(messages, tools, temperature, timeout)


async def _chat_cloud(messages: list[dict], tools: list[dict] = None,
                      temperature: float = None, timeout: float = None) -> dict:
    """云端 LLM 调用（DeepSeek）"""
    client = get_client()
    kwargs = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature or config.LLM_TEMPERATURE,
        "max_tokens": config.LLM_MAX_TOKENS,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if "deepseek" in config.LLM_MODEL.lower():
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return await _execute_chat(client, kwargs, timeout or config.LLM_TIMEOUT)


async def _chat_ollama(messages: list[dict], tools: list[dict] = None,
                       temperature: float = None, timeout: float = None) -> dict:
    """本地 LLM 调用（Ollama）"""
    client = get_ollama_client()
    kwargs = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "temperature": temperature if temperature is not None else 0.3,
        "max_tokens": config.OLLAMA_MAX_TOKENS,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return await _execute_chat(client, kwargs, timeout or config.OLLAMA_TIMEOUT)


async def _execute_chat(client: AsyncOpenAI, kwargs: dict, timeout: float,
                        max_retries: int = 3) -> dict:
    """执行 LLM 调用（通用逻辑，带指数退避重试）"""
    # [DEBUG] 打印工具调用信息
    tools_list = kwargs.get('tools', [])
    model = kwargs.get('model', '?')
    print(f"[LLM] model={model}, tools={len(tools_list)}, tool_choice={kwargs.get('tool_choice', 'none')}")
    if tools_list:
        tool_names = [t['function']['name'] for t in tools_list[:8]]
        print(f"[LLM] tools_preview: {tool_names}...")

    last_error = None
    for attempt in range(max_retries):
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            last_error = "timeout"
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[LLM] 超时，{wait}s 后重试 ({attempt+1}/{max_retries})")
                await asyncio.sleep(wait)
                continue
            return {"role": "assistant", "content": "⏱️ LLM 响应超时，请稍后重试或缩短请求。", "_timeout": True}
        except Exception as e:
            last_error = str(e)
            # 429 限流或 5xx 服务端错误时重试
            is_retryable = hasattr(e, 'status_code') and (e.status_code == 429 or e.status_code >= 500)
            if is_retryable and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[LLM] 错误 {e.status_code}，{wait}s 后重试 ({attempt+1}/{max_retries})")
                await asyncio.sleep(wait)
                continue
            return {"role": "assistant", "content": f"❌ LLM 调用失败: {str(e)}", "_error": True}
        break

    msg = resp.choices[0].message
    result = {"role": "assistant", "content": msg.content or ""}
    has_tool_calls = bool(msg.tool_calls)
    print(f"[LLM] response: tool_calls={has_tool_calls}, content_len={len(msg.content or '')}")
    if has_tool_calls:
        for tc in msg.tool_calls:
            print(f"[LLM]   → {tc.function.name}({tc.function.arguments[:100]})")
    if msg.tool_calls:
        result["tool_calls"] = [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
    if hasattr(resp, 'usage') and resp.usage:
        result["_usage"] = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        }
    return result


async def chat_simple(system_prompt: str, user_prompt: str,
                      use_ollama: bool = False) -> str:
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    result = await chat(messages, use_ollama=use_ollama)
    return result["content"]


def chat_simple_sync(system_prompt: str, user_prompt: str,
                     use_ollama: bool = False) -> str:
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, chat_simple(system_prompt, user_prompt, use_ollama))
            return future.result(timeout=30)
    except RuntimeError:
        return asyncio.run(chat_simple(system_prompt, user_prompt, use_ollama))
