"""
搜索工具插件 — web_search / news_search
从 builtin.py 拆分，自注册到 ToolRegistry
"""
import json
from tools.registry import registry


def _check_duckduckgo():
    try:
        from duckduckgo_search import DDGS
        return True
    except ImportError:
        return False


def _web_search(query: str, objective: str = "", max_results: int = 5) -> str:
    from tools.search import search_and_summarize_sync
    result = search_and_summarize_sync(query, max_results=max_results, objective=objective)
    return json.dumps(result, ensure_ascii=False)


def _news_search(query: str, max_results: int = 5) -> str:
    from tools.search import news_search_sync
    result = news_search_sync(query, max_results=max_results)
    return json.dumps(result, ensure_ascii=False)


registry.register(
    name="web_search",
    description="真实联网搜索（DuckDuckGo）。返回搜索结果摘要和链接。适用于查找最新信息、文档、教程、新闻等。",
    schema={
        "name": "web_search",
        "description": "真实联网搜索（DuckDuckGo）。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词，建议用英文关键词效果更好"},
                "objective": {"type": "string", "description": "你希望从搜索结果中提取什么", "default": ""},
                "max_results": {"type": "integer", "description": "最大结果数", "default": 5}
            },
            "required": ["query"]
        }
    },
    handler=_web_search,
    category="search",
    check_fn=_check_duckduckgo,
    risk_level="low",
)


registry.register(
    name="news_search",
    description="搜索新闻。用于查找最新事件、行业动态、产品发布等时效性信息。",
    schema={
        "name": "news_search",
        "description": "搜索新闻。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "新闻搜索关键词"},
                "max_results": {"type": "integer", "description": "最大结果数", "default": 5}
            },
            "required": ["query"]
        }
    },
    handler=_news_search,
    category="search",
    check_fn=_check_duckduckgo,
    risk_level="low",
)
