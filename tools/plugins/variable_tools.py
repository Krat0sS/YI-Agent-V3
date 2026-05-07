"""
变量管理工具 — workflow 步骤间传参、临时状态存储
"""
import json
from tools.registry import registry

_variables: dict = {}


def _set_variable(name: str, value: str) -> str:
    _variables[name] = value
    return json.dumps({"success": True, "name": name, "value": value}, ensure_ascii=False)


def _get_variable(name: str) -> str:
    if name in _variables:
        return json.dumps({"success": True, "name": name, "value": _variables[name]}, ensure_ascii=False)
    return json.dumps({"success": False, "error": f"未找到变量: {name}"}, ensure_ascii=False)


def _list_variables() -> str:
    return json.dumps({"variables": dict(_variables), "count": len(_variables)}, ensure_ascii=False)


registry.register(
    name="set_variable",
    description="设置变量。用于 workflow 步骤间传递数据或临时存储。",
    schema={
        "name": "set_variable",
        "description": "设置变量。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "变量名"},
                "value": {"type": "string", "description": "变量值"}
            },
            "required": ["name", "value"]
        }
    },
    handler=_set_variable,
    category="utility",
    risk_level="low",
)

registry.register(
    name="get_variable",
    description="获取变量值。",
    schema={
        "name": "get_variable",
        "description": "获取变量值。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "变量名"}
            },
            "required": ["name"]
        }
    },
    handler=_get_variable,
    category="utility",
    risk_level="low",
)

registry.register(
    name="list_variables",
    description="列出所有已设置的变量。",
    schema={
        "name": "list_variables",
        "description": "列出所有变量。",
        "parameters": {"type": "object", "properties": {}}
    },
    handler=_list_variables,
    category="utility",
    risk_level="low",
)
