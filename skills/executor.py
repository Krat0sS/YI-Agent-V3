"""
技能执行器 — 按 SKILL.md 的步骤序列调用工具

接收一个已加载的 Skill 对象和用户输入，
按 ## 执行步骤 顺序调用工具，在检查点暂停等待确认。
"""
import json
import time
import asyncio
from typing import Callable, Optional, List
from skills.loader import Skill
from tools.registry import registry
from data import execution_log


class SkillExecutor:
    """技能执行器"""

    def __init__(self, skill: Skill, on_progress: Callable = None,
                 on_confirm: Callable = None, session_id: str = ""):
        """
        Args:
            skill: 要执行的技能
            on_progress: 进度回调 fn(message: str)
            on_confirm: 确认回调 fn(prompt: str) -> bool
            session_id: 会话 ID
        """
        self.skill = skill
        self.on_progress = on_progress or (lambda msg: None)
        self.on_confirm = on_confirm
        self.session_id = session_id
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    async def execute(self, user_input: str = "") -> dict:
        """
        执行技能。返回：
        {
            "success": bool,
            "skill": str,
            "steps_completed": int,
            "steps_total": int,
            "results": [...],
            "duration_ms": int,
            "error": str (if failed)
        }
        """
        start_time = time.time()
        steps = self.skill.steps
        results = []

        self.on_progress(f"🎯 开始执行技能「{self.skill.name}」，共 {len(steps)} 步")

        # 检查前置工具是否可用
        missing_tools = []
        for tool_name in self.skill.tools:
            if registry.get(tool_name) is None:
                missing_tools.append(tool_name)
        if missing_tools:
            return {
                "success": False,
                "skill": self.skill.name,
                "steps_completed": 0,
                "steps_total": len(steps),
                "results": [],
                "duration_ms": int((time.time() - start_time) * 1000),
                "error": f"缺少前置工具: {', '.join(missing_tools)}",
            }

        for i, step in enumerate(steps):
            if self._cancelled:
                results.append({"step": i + 1, "status": "cancelled"})
                break

            self.on_progress(f"⏳ 步骤 {i + 1}/{len(steps)}: {step[:60]}...")

            # 执行这一步（通过 LLM 解析步骤 → 工具调用）
            step_result = await self._execute_step(step, user_input, i + 1)
            results.append(step_result)

            if not step_result.get("success"):
                self.on_progress(f"❌ 步骤 {i + 1} 失败: {step_result.get('error', '未知错误')}")
                # 记录失败
                execution_log.log_skill_usage(
                    self.skill.name, user_input,
                    success=False,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
                return {
                    "success": False,
                    "skill": self.skill.name,
                    "steps_completed": i,
                    "steps_total": len(steps),
                    "results": results,
                    "duration_ms": int((time.time() - start_time) * 1000),
                    "error": step_result.get("error", "步骤执行失败"),
                }

            self.on_progress(f"✅ 步骤 {i + 1} 完成")

        duration_ms = int((time.time() - start_time) * 1000)

        # 记录成功
        execution_log.log_skill_usage(
            self.skill.name, user_input,
            success=True, duration_ms=duration_ms,
        )

        self.on_progress(f"🎉 技能「{self.skill.name}」执行完成")

        return {
            "success": True,
            "skill": self.skill.name,
            "steps_completed": len(steps),
            "steps_total": len(steps),
            "results": results,
            "duration_ms": duration_ms,
        }

    # 步骤描述中的关键词 → 工具名映射（用于强制匹配）
    _STEP_TOOL_HINTS = {
        '搜索': 'web_search', '搜一下': 'web_search', '查找资料': 'web_search',
        '联网搜索': 'web_search', '搜索引擎': 'web_search',
        '打开网页': 'ab_open', '访问网页': 'ab_open', '浏览网页': 'ab_open',
        '截图': 'ab_screenshot', '截屏': 'ab_screenshot',
        '点击': 'ab_click', '填写': 'ab_fill', '输入': 'ab_type',
        '读取文件': 'read_file', '查看文件': 'read_file', '打开文件': 'read_file',
        '写入文件': 'write_file', '创建文件': 'write_file', '保存文件': 'write_file',
        '编辑文件': 'edit_file', '修改文件': 'edit_file',
        '列出文件': 'list_files', '扫描目录': 'scan_files', '扫描文件': 'scan_files',
        '查找文件': 'find_files', '搜索文件': 'find_files',
        '移动文件': 'move_file', '整理': 'organize_directory',
        '执行命令': 'run_command', '运行命令': 'run_command',
        '记住': 'remember', '回忆': 'recall',
        '检查状态': 'check_directory_status',
    }

    def _infer_tool_from_step(self, step: str) -> tuple:
        """从步骤描述中推断应该使用的工具名和默认参数"""
        step_lower = step.lower()
        for hint, tool_name in self._STEP_TOOL_HINTS.items():
            if hint in step_lower:
                # 为常见工具生成默认参数
                args = self._default_args_for_tool(tool_name, step)
                return tool_name, args
        return None, {}

    def _default_args_for_tool(self, tool_name: str, step: str) -> dict:
        """根据工具名和步骤描述生成默认参数"""
        if tool_name == 'web_search':
            # 从步骤中提取搜索关键词
            query = step
            for prefix in ['使用', '调用', '通过', '利用', '搜索', '查找', '联网搜索']:
                query = query.replace(prefix, '')
            for suffix in ['收集搜索结果', '获取信息', '搜索资料', '进行搜索']:
                query = query.replace(suffix, '')
            return {"query": query.strip()[:100] or step[:80]}
        if tool_name == 'read_file':
            return {"path": "."}
        if tool_name == 'list_files':
            return {"path": "."}
        if tool_name == 'scan_files':
            return {"path": "."}
        if tool_name == 'ab_open':
            # 尝试从步骤中提取 URL
            import re
            url_match = re.search(r'https?://\S+', step)
            if url_match:
                return {"url": url_match.group()}
            return {"url": "https://www.google.com"}
        if tool_name == 'write_file':
            return {}  # 需要 LLM 推导
        if tool_name == 'run_command':
            return {}  # 需要 LLM 推导
        return {}

    async def _execute_step(self, step: str, user_input: str, step_num: int) -> dict:
        """
        执行单个步骤。
        通过 LLM 将步骤描述转换为具体的工具调用。
        如果 LLM 没调工具但步骤描述暗示需要工具，强制匹配并执行。
        """
        from core.llm import chat

        # 构建上下文：告诉 LLM 当前步骤和可用工具
        available_tools = registry.get_schemas()
        tool_names = registry.get_available_names()

        prompt = f"""你需要执行以下步骤：
步骤 {step_num}: {step}

用户原始输入: {user_input}

可用工具: {', '.join(tool_names[:30])}

【重要】你必须调用工具来完成这一步。不要只输出文字描述——必须实际调用工具执行操作。
如果步骤说"搜索"，就调用 web_search；说"读取文件"，就调用 read_file；说"列出"，就调用 list_files。
只有纯分析/总结步骤才可以不调工具。"""

        messages = [
            {"role": "system", "content": "你是一个技能执行器。你必须调用工具来完成每一步，不要只说不做。每步只做一件事。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = await chat(messages, tools=available_tools[:20])
        except Exception as e:
            return {"success": False, "step": step_num, "error": str(e)}

        if result.get("_error") or result.get("_timeout"):
            return {"success": False, "step": step_num, "error": result.get("content", "LLM 调用失败")}

        # 如果 LLM 调用了工具，执行它
        if "tool_calls" in result:
            tool_results = []
            for tc in result["tool_calls"]:
                func_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                # 高风险工具需要确认
                td = registry.get(func_name)
                if td and td.risk_level == "high" and self.on_confirm:
                    confirmed = self.on_confirm(f"{func_name}({json.dumps(args, ensure_ascii=False)[:100]})")
                    if not confirmed:
                        tool_results.append({"tool": func_name, "cancelled": True})
                        continue

                tool_result = registry.execute(func_name, args)
                tool_results.append({"tool": func_name, "result": tool_result[:500]})

            return {
                "success": True,
                "step": step_num,
                "action": step,
                "tool_calls": tool_results,
                "llm_response": result.get("content", ""),
            }
        else:
            # ═══ LLM 没调工具 → 尝试从步骤描述强制匹配工具 ═══
            inferred_tool, inferred_args = self._infer_tool_from_step(step)
            if inferred_tool and registry.get(inferred_tool):
                self.on_progress(f"  🔧 LLM 未调工具，强制匹配: {inferred_tool}")
                # 如果参数为空，用 LLM 推导
                if not inferred_args:
                    from core.workflow import WorkflowRunner
                    # 简单推导：让 LLM 填参数
                    infer_prompt = f"工具 {inferred_tool} 需要参数。步骤: {step}。请输出 JSON 参数。"
                    infer_msg = [{"role": "user", "content": infer_prompt}]
                    try:
                        infer_result = await chat(infer_msg, temperature=0.1, use_ollama=True)
                        if not infer_result.get("_error"):
                            content = infer_result["content"].strip()
                            if "```" in content:
                                content = content.split("```")[1].split("```")[0].strip()
                            inferred_args = json.loads(content)
                    except Exception:
                        pass  # 推导失败，用空参数试

                try:
                    tool_result = registry.execute(inferred_tool, inferred_args)
                    return {
                        "success": True,
                        "step": step_num,
                        "action": step,
                        "tool_calls": [{"tool": inferred_tool, "args": inferred_args, "result": tool_result[:500], "forced": True}],
                        "llm_response": result.get("content", ""),
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "step": step_num,
                        "action": step,
                        "error": f"强制匹配工具 {inferred_tool} 执行失败: {str(e)}",
                    }

            # 真的不需要工具的步骤（纯分析/总结）
            return {
                "success": True,
                "step": step_num,
                "action": step,
                "tool_calls": [],
                "llm_response": result.get("content", ""),
                "no_tool": True,
            }
