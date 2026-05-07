"""
视觉工具插件 — vision_analyze / task_plan
从 builtin.py 拆分，自注册到 ToolRegistry
"""
import json
from tools.registry import registry


def _vision_analyze(base64_image: str, question: str = None) -> str:
    from tools.vision import analyze_screenshot_sync
    result = analyze_screenshot_sync(base64_image, question)
    return json.dumps(result, ensure_ascii=False)


def _task_plan(instruction: str, context: str = "") -> str:
    from tools.planner import plan_task, format_plan
    import asyncio
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, plan_task(instruction, context))
            plan = future.result(timeout=30)
    except RuntimeError:
        plan = asyncio.run(plan_task(instruction, context))
    return json.dumps(plan, ensure_ascii=False)


registry.register(
    name="vision_analyze",
    description="用视觉模型分析截图，识别界面元素和位置。传入 base64 图片，返回元素列表和建议操作。",
    schema={
        "name": "vision_analyze",
        "description": "用视觉模型分析截图。",
        "parameters": {
            "type": "object",
            "properties": {
                "base64_image": {"type": "string", "description": "base64 编码的图片"},
                "question": {"type": "string", "description": "分析问题"}
            },
            "required": ["base64_image"]
        }
    },
    handler=_vision_analyze,
    category="vision",
    risk_level="low",
)


registry.register(
    name="task_plan",
    description="分析复杂指令，生成分步执行计划。用于多步骤任务。返回结构化步骤列表。",
    schema={
        "name": "task_plan",
        "description": "分析复杂指令，生成分步执行计划。",
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "用户的完整指令"},
                "context": {"type": "string", "description": "当前环境上下文", "default": ""}
            },
            "required": ["instruction"]
        }
    },
    handler=_task_plan,
    category="vision",
    risk_level="low",
)
