# -*- coding: utf-8 -*-
"""对话管理器 — Agent 核心循环（v1.3.5：五层易经流水线）"""
import json
import os
import re
import time
import datetime
import asyncio
import atexit
from dataclasses import dataclass
from typing import Callable, Optional, List
from core.llm import chat
from tools.registry import registry
from memory.memory_system import MemorySystem
from security.context_sanitizer import get_security_prompt
from data import execution_log
import config

# v1.4: 大衍筮法引擎
from core.dayan import dayan_diagnose, format_gua_message, get_changing_lines, get_bian_hexagram
# v1.4: 子Agent框架
from core.sub_agent import SubAgent, Orchestrator, OrchestrationPlan
# v2.0: YI-Framework — 易经态势感知引擎（Action 2: 切开LLM的神经）
# v3.0: 卦象改为工具索引（参谋模式），不再生成硬约束
from yi_framework import YiRuntime, GuaToolEffectiveness, generate_tool_hint


class Conversation:
    """一次对话会话（v1.3 async）"""

    def __init__(self, session_id: str = "default", restore: bool = True,
                 on_confirm: Optional[Callable[[str], bool]] = None):
        self.session_id = session_id
        self.memory = MemorySystem()
        self.messages: list[dict] = []
        self.tool_call_count = 0
        self.tool_log: list[dict] = []
        self._browser_session = None
        self._cancel_event = asyncio.Event()
        self._token_usage = []
        self._on_confirm = on_confirm  # 确认回调，默认 None 时危险操作会被拒绝

        # v2.0: YI-Framework 运行时（Action 2: 替代时辰/万物/五行/变爻）
        # v3.0: 卦象不再生成 ExecutionProfile，改为工具索引提示
        self._yi_runtime = YiRuntime()
        self._gua_effectiveness = GuaToolEffectiveness()
        self._default_timeout = 30
        self._default_risk_tolerance = 0.5

        if restore and self._session_file_exists():
            self._load_session()
        else:
            self._init_system()

    # ═══ 初始化 ═══

    def _init_system(self):
        system_prompt = self.memory.get_system_prompt()
        # v1.1: 注入安全规则
        system_prompt += "\n\n" + get_security_prompt()
        # v1.1: 注入技能列表
        try:
            from skills.loader import get_skill_prompt_context
            skill_context = get_skill_prompt_context()
            if skill_context:
                system_prompt += "\n\n" + skill_context
        except Exception:
            pass
        self.messages = [{"role": "system", "content": system_prompt}]

    @property
    def browser(self):
        """已废弃：浏览器工具统一走 registry.execute()（ab_* 系列）"""
        return None

    async def cleanup(self):
        self._browser_session = None

    def cancel(self):
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _clear_cancel(self):
        self._cancel_event.clear()

    # ═══ 自动记忆提取 ═══

    def _extract_memos(self, text: str) -> list[str]:
        import re
        memos = []
        pattern = r'\[MEMO:\s*(.*?)\]'
        for match in re.finditer(pattern, text, re.DOTALL):
            content = match.group(1).strip()
            if content and len(content) > 2:
                memos.append(content)
        return memos

    def _process_memos(self, text: str):
        memos = self._extract_memos(text)
        for memo in memos:
            self.memory.save_daily(f"[自动记忆] {memo}")
            pref_keywords = ["喜欢", "偏好", "习惯", "以后", "不要", "总是", "用中文", "简洁", "详细"]
            if any(kw in memo for kw in pref_keywords):
                self.memory.save_file_preference("auto", memo)
        return len(memos)

    # ═══ 会话持久化 ═══

    def _session_path(self) -> str:
        os.makedirs(config.SESSIONS_DIR, exist_ok=True)
        return os.path.join(config.SESSIONS_DIR, f"{self.session_id}.json")

    def _session_file_exists(self) -> bool:
        return os.path.exists(self._session_path())

    def save_session(self):
        try:
            with open(self._session_path(), "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self.session_id,
                    "messages": self.messages,
                    "saved_at": datetime.datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_session(self):
        try:
            with open(self._session_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            self.messages = data.get("messages", [])
            if not self.messages:
                self._init_system()
        except Exception:
            self._init_system()

    # ═══ 上下文保护（v1.3.4: 智能压缩） ═══

    # 压缩阈值：超过这个轮次就开始压缩旧消息
    _COMPRESS_AFTER_TURNS = 8    # 8 轮后压缩（16 条消息）
    # 保留最近 N 轮完整上下文
    _KEEP_RECENT_TURNS = 5
    # 每条旧消息最大保留字符数
    _MAX_OLD_MSG_LEN = 300

    # ═══ v3.0: 旧的 Profile 约束注入已移除，改为卦象工具索引提示 ═══
    # _get_profile_constraint_prompt 和 _inject_profile_constraints 不再使用
    # 卦象提示在 send() 开头通过 generate_tool_hint() 注入 system message

    def _trim_context(self):
        """
        v4.5 智能上下文压缩（彻底修复孤儿 tool 消息导致 API 400）。

        核心规则：old 区域不保留任何 tool_calls 字段和 tool 结果消息。
        - old assistant(tool_calls) → 转为纯文本摘要（不保留 tool_calls 字段）
        - old tool 结果 → 全部丢弃（对应的 tool_calls 已转纯文本，不需要配对）
        - recent 区域保持完整不动

        这样 old 区域只有 user + assistant(纯文本)，永远不会有配对断裂。
        """
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        history = [m for m in self.messages if m["role"] != "system"]

        keep_count = self._KEEP_RECENT_TURNS * 2
        if len(history) <= keep_count:
            return

        # 安全切割：确保不把 assistant(tool_calls) 和它的 tool 结果分到两边
        cut = len(history) - keep_count
        while cut > 0 and cut < len(history):
            cur = history[cut]
            prev = history[cut - 1]
            # 切割点在 tool 结果之前，且前一条是 assistant(tool_calls) → 往前挪
            if cur.get("role") == "tool" and prev.get("role") == "assistant" and "tool_calls" in prev:
                cut -= 1
                continue
            break

        old_history = history[:cut]
        recent_history = history[cut:]

        # 压缩 old 消息：user 原样保留，assistant 转纯文本，tool 全部丢弃
        condensed = []
        for msg in old_history:
            role = msg.get("role", "")

            if role == "user":
                condensed.append(msg)

            elif role == "assistant":
                if "tool_calls" in msg:
                    # tool_calls 转纯文本摘要，不保留 tool_calls 字段
                    tool_summary = []
                    for tc in msg.get("tool_calls", []):
                        fn = tc.get("function", {})
                        name = fn.get("name", "?")
                        args_str = fn.get("arguments", "{}")[:80]
                        tool_summary.append(f"{name}({args_str})")
                    condensed.append({
                        "role": "assistant",
                        "content": f"[调用了: {', '.join(tool_summary)}]",
                    })
                elif msg.get("content"):
                    content = msg["content"]
                    if len(content) > self._MAX_OLD_MSG_LEN:
                        condensed.append({
                            "role": "assistant",
                            "content": content[:150] + f"\n...[压缩]...\n" + content[-100:]
                        })
                    else:
                        condensed.append(msg)

            # role == "tool" → 全部丢弃（对应的 tool_calls 已转纯文本）

        # 确保 recent_history 不以孤立的 tool 消息开头
        while recent_history and recent_history[0]["role"] in ("tool", "assistant"):
            if recent_history[0]["role"] == "tool":
                recent_history.pop(0)
            elif "tool_calls" in recent_history[0]:
                recent_history.pop(0)
            else:
                break

        self.messages = system_msgs + condensed + recent_history

    def get_context_stats(self) -> dict:
        """获取上下文统计（调试用）"""
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        history = [m for m in self.messages if m["role"] != "system"]
        total_chars = sum(len(m.get("content", "")) for m in self.messages)
        return {
            "total_messages": len(self.messages),
            "system_messages": len(system_msgs),
            "history_messages": len(history),
            "total_chars": total_chars,
            "estimated_tokens": total_chars // 2,  # 粗估：中文约 2 字符 = 1 token
        }

    def _sanitize_messages(self):
        import re
        tool_call_ids_needed = set()
        tool_call_ids_found = set()
        for msg in self.messages:
            if msg["role"] == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    tool_call_ids_needed.add(tc["id"])
            if msg["role"] == "tool":
                tool_call_ids_found.add(msg.get("tool_call_id", ""))
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 100000:
                    try:
                        data = json.loads(content)
                        if "base64" in data:
                            b64_len = len(data["base64"])
                            data["base64"] = f"[图片已省略，{b64_len} 字符 base64]"
                            if "note" in data:
                                del data["note"]
                            msg["content"] = json.dumps(data, ensure_ascii=False)
                    except (json.JSONDecodeError, TypeError):
                        pass
        missing = tool_call_ids_needed - tool_call_ids_found
        if not missing:
            return
        cancel_result = json.dumps({"cancelled": True, "message": "上下文已压缩，此步骤结果不再可用。请重新调用工具。"})
        fixed = []
        for msg in self.messages:
            fixed.append(msg)
            if msg["role"] == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    if tc["id"] in missing:
                        fixed.append({"role": "tool", "tool_call_id": tc["id"], "content": cancel_result})
                        missing.discard(tc["id"])
        self.messages = fixed

    # ═══ 工具执行（v1.1：使用 ToolRegistry） ═══

    async def _execute_tool(self, func_name: str, args: dict,
                            on_confirm: Optional[Callable[[str], bool]] = None) -> str:
        # 使用实例级回调作为兜底
        confirm_fn = on_confirm or self._on_confirm
        start_time = time.time()
        loop = asyncio.get_running_loop()

        browser_session_tools = {
            "ab_click", "ab_fill", "ab_type", "ab_press", "ab_screenshot",
            "ab_open", "ab_dblclick", "ab_hover", "ab_select", "ab_check",
            "ab_uncheck", "ab_scroll", "ab_scrollintoview", "ab_drag",
            "ab_wait", "ab_eval", "ab_snapshot_click",
        }
        subprocess_tools = {"run_command", "run_command_confirmed"}

        if func_name in browser_session_tools:
            # ═══ Phase 1: 桌面操作确认门控 ═══
            try:
                from security.filesystem_guard import guard
                gui_check = guard.check_gui_operation(func_name, args)
                if gui_check.get("needs_confirm"):
                    if confirm_fn and callable(confirm_fn):
                        confirmed = confirm_fn(gui_check["confirm_message"])
                        if not confirmed:
                            return json.dumps({
                                "cancelled": True,
                                "message": "用户拒绝了桌面操作。"
                            }, ensure_ascii=False)
                    else:
                        # 无确认回调时，默认拒绝危险操作
                        return json.dumps({
                            "blocked": True,
                            "message": f"需要用户确认但未配置确认回调: {gui_check['confirm_message']}"
                        }, ensure_ascii=False)
            except ImportError:
                pass

            try:
                result_raw = await self._execute_browser_session_tool(func_name, args)
            except asyncio.CancelledError:
                result_raw = json.dumps({"cancelled": True, "message": "操作已被用户取消。"})
            except Exception as e:
                result_raw = json.dumps({"error": True, "message": f"浏览器工具失败: {str(e)}"})
            elapsed = time.time() - start_time
            self._log_tool_call(func_name, args, result_raw, elapsed, 0)
            execution_log.log_tool_call(
                func_name, args, result_raw[:500],
                success="error" not in result_raw.lower(),
                elapsed_ms=int(elapsed * 1000),
                session_id=self.session_id,
            )
            return result_raw

        if func_name in subprocess_tools:
            # ═══ 安全守卫：命令执行前检查 ═══
            try:
                from security.filesystem_guard import guard as _guard
                safety = _guard.check_command(args.get("command", ""))
                if not safety.safe:
                    result_raw = json.dumps({
                        "blocked": True,
                        "reason": safety.reason,
                        "tool": func_name,
                        "risk_level": safety.risk_level,
                    }, ensure_ascii=False)
                    elapsed = time.time() - start_time
                    self._log_tool_call(func_name, args, result_raw, elapsed, 0)
                    execution_log.log_tool_call(func_name, args, result_raw[:500], success=False, elapsed_ms=int(elapsed * 1000), session_id=self.session_id)
                    return result_raw
                if safety.needs_confirm:
                    if confirm_fn and callable(confirm_fn):
                        confirmed = confirm_fn(safety.reason)
                        if not confirmed:
                            result_raw = json.dumps({"cancelled": True, "message": "用户拒绝了命令执行。"}, ensure_ascii=False)
                            elapsed = time.time() - start_time
                            self._log_tool_call(func_name, args, result_raw, elapsed, 0)
                            execution_log.log_tool_call(func_name, args, result_raw[:500], success=False, elapsed_ms=int(elapsed * 1000), session_id=self.session_id)
                            return result_raw
                    else:
                        result_raw = json.dumps({"needs_confirm": True, "command": args.get("command", ""), "reason": safety.reason}, ensure_ascii=False)
                        elapsed = time.time() - start_time
                        self._log_tool_call(func_name, args, result_raw, elapsed, 0)
                        execution_log.log_tool_call(func_name, args, result_raw[:500], success=False, elapsed_ms=int(elapsed * 1000), session_id=self.session_id)
                        return result_raw
            except ImportError:
                pass  # 安全模块不存在时降级放行

            from tools.subprocess_runner import run_command_async, run_command_confirmed_async
            try:
                if func_name == "run_command":
                    result_raw = await run_command_async(args.get("command", ""), args.get("cwd"), args.get("timeout", 30))
                else:
                    result_raw = await run_command_confirmed_async(args.get("command", ""), args.get("cwd"), args.get("timeout", 30))
            except asyncio.CancelledError:
                result_raw = json.dumps({"cancelled": True, "message": "命令已被用户取消。"})
            elapsed = time.time() - start_time
            self._log_tool_call(func_name, args, result_raw, elapsed, 0)
            execution_log.log_tool_call(func_name, args, result_raw[:500], success="error" not in result_raw.lower(), elapsed_ms=int(elapsed * 1000), session_id=self.session_id)
            return result_raw

        # v3.0: 使用全局默认超时和风险容忍度（不再由卦象控制）
        profile_timeout = self._default_timeout
        try:
            result_raw = await asyncio.wait_for(
                loop.run_in_executor(None, registry.execute, func_name, args, self.session_id, self._default_risk_tolerance),
                timeout=profile_timeout
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            error_result = json.dumps({"error": True, "type": "tool_timeout", "tool": func_name, "message": f"工具 {func_name} 执行超时 ({profile_timeout}s)"}, ensure_ascii=False)
            self._log_tool_call(func_name, args, error_result, elapsed, 0, error=True)
            execution_log.log_tool_call(func_name, args, error_result[:500], success=False, elapsed_ms=int(elapsed * 1000), session_id=self.session_id)
            return error_result
        except asyncio.CancelledError:
            elapsed = time.time() - start_time
            cancel_result = json.dumps({"cancelled": True, "message": "操作已被用户取消。"}, ensure_ascii=False)
            self._log_tool_call(func_name, args, cancel_result, elapsed, 0, error=False)
            return cancel_result
        except Exception as e:
            elapsed = time.time() - start_time
            error_result = json.dumps({"error": True, "type": "execution_error", "tool": func_name, "message": f"工具 {func_name} 执行失败: {str(e)}"}, ensure_ascii=False)
            self._log_tool_call(func_name, args, error_result, elapsed, 0, error=True)
            execution_log.log_tool_call(func_name, args, error_result[:500], success=False, elapsed_ms=int(elapsed * 1000), session_id=self.session_id)
            return error_result

        # 确认检查
        try:
            parsed = json.loads(result_raw)
            if isinstance(parsed, dict) and parsed.get("needs_confirm"):
                cmd = parsed.get("command", "")
                if confirm_fn and callable(confirm_fn):
                    confirmed = confirm_fn(cmd)
                    if confirmed:
                        result_raw = await asyncio.wait_for(loop.run_in_executor(None, registry.execute, "run_command_confirmed", {"command": cmd}, self.session_id, self._default_risk_tolerance), timeout=config.TOOL_TIMEOUT)
                    else:
                        result_raw = json.dumps({"cancelled": True, "message": "用户取消了该命令的执行。"}, ensure_ascii=False)
                else:
                    result_raw = json.dumps({"error": True, "type": "confirm_required", "message": f"该命令需要用户确认: {cmd}"}, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

        elapsed = time.time() - start_time
        success = "error" not in result_raw.lower()
        self._log_tool_call(func_name, args, result_raw, elapsed, 0)
        execution_log.log_tool_call(func_name, args, result_raw[:500], success=success, elapsed_ms=int(elapsed * 1000), session_id=self.session_id)

        # ═══ v2.0: YiRuntime 态势监测 + GuaToolEffectiveness 经验记录 ═══
        yi_event = self._yi_runtime.tick({
            'success': success,
            'duration_ms': int(elapsed * 1000),
        })

        # 记录卦象×工具效果到 SQLite
        try:
            self._gua_effectiveness.record(
                hexagram=self._yi_runtime.current_hexagram,
                tool_name=func_name,
                success=success,
                duration_ms=int(elapsed * 1000),
                session_id=self.session_id,
            )
        except Exception:
            pass  # 记录失败不影响主流程

        # 动爻翻转 → 注入新的工具索引提示
        if yi_event:
            # v3.0: 翻转时更新 system message 中的卦象提示
            self.messages = [
                m for m in self.messages
                if not (m.get("role") == "system" and "[卦象索引]" in m.get("content", ""))
            ]
            self.messages.append({"role": "system", "content": yi_event.hint})

        # v3.0: 不再由 Profile 控制重试，使用全局默认值
        if not success:
            for retry_i in range(1):  # 默认重试 1 次
                try:
                    retry_result = await asyncio.wait_for(
                        loop.run_in_executor(None, registry.execute, func_name, args, self.session_id, self._default_risk_tolerance),
                        timeout=self._default_timeout
                    )
                    retry_success = "error" not in retry_result.lower()
                    execution_log.log_tool_call(
                        func_name, args, retry_result[:500],
                        success=retry_success,
                        elapsed_ms=int((time.time() - start_time) * 1000),
                        session_id=self.session_id,
                    )
                    # 移除第一次失败记录，避免污染滑动窗口
                    if self._yi_runtime._recent_results and not self._yi_runtime._recent_results[-1]:
                        self._yi_runtime._recent_results.pop()
                    self._yi_runtime.tick({'success': retry_success})
                    self._gua_effectiveness.record(
                        hexagram=self._yi_runtime.current_hexagram,
                        tool_name=func_name, success=retry_success,
                        duration_ms=int((time.time() - start_time) * 1000),
                        session_id=self.session_id,
                    )
                    if retry_success:
                        return retry_result
                except Exception:
                    pass

        return result_raw

    async def _execute_browser_session_tool(self, func_name: str, args: dict) -> str:
        """浏览器工具统一走 registry.execute()（Playwright 驱动的 ab_* 工具）"""
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, registry.execute, func_name, args, self.session_id, self._default_risk_tolerance),
                timeout=self._default_timeout,
            )
            return result
        except asyncio.TimeoutError:
            return json.dumps({"error": True, "message": f"浏览器工具 {func_name} 超时"})
        except Exception as e:
            return json.dumps({"error": True, "message": f"浏览器工具 {func_name} 失败: {str(e)}"})

    def _log_tool_call(self, func_name: str, args: dict, result: str, elapsed: float, retries: int, error: bool = False):
        entry = {
            "tool": func_name,
            "args": {k: str(v)[:100] for k, v in args.items()},
            "elapsed_ms": int(elapsed * 1000),
            "retries": retries,
            "error": error,
            "result_preview": result[:200] if not error else result,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        self.tool_log.append(entry)

    # ═══ 对话主循环 ═══

    async def send(self, user_message: str,
                   on_confirm: Optional[Callable[[str], bool]] = None,
                   on_progress: Optional[Callable[[str], None]] = None) -> dict:
        """
        v1.3 异步发送用户消息，获取助手回复。

        修复：
        - decompose_task 只调用一次，计划结果缓存复用
        - simple 指令也记录路由决策日志
        - 技能生成阈值从 tool_call_count >= 2 提升到 >= 3
        """
        self.messages.append({"role": "user", "content": user_message})
        self.tool_call_count = 0
        self._clear_cancel()
        self._token_usage = []
        rounds = 0
        start_time = time.time()

        self._trim_context()
        self._sanitize_messages()

        # ═══ v1.4: 大衍筮法诊断（第一层） ═══
        _all_tools = registry.get_all()
        _tool_names = [t.name for t in _all_tools if t.is_available()]
        _tool_descs = {t.name: t.description or "" for t in _all_tools if t.is_available()}
        _recent_calls = execution_log.get_recent_tool_calls(limit=20)

        dayan_result = dayan_diagnose(
            user_input=user_message,
            tool_names=_tool_names,
            tool_descriptions=_tool_descs,
            recent_calls=_recent_calls,
        )

        if on_progress:
            on_progress(format_gua_message(dayan_result))

        # 记录大衍诊断到 dayan_log
        try:
            from data.execution_log import log_dayan
            changing = get_changing_lines(dayan_result)
            bian = get_bian_hexagram(dayan_result)
            log_dayan(
                user_input=user_message,
                hexagram_name=dayan_result.hexagram_name,
                inner_trigram=dayan_result.inner_trigram,
                outer_trigram=dayan_result.outer_trigram,
                action_hint=dayan_result.action_hint,
                lines_json=json.dumps([{
                    'position': l.position,
                    'yan_type': l.yan_type,
                    'confidence': round(l.confidence, 3),
                    'tool_name': l.tool_name,
                } for l in dayan_result.lines], ensure_ascii=False),
                tool_sequence=', '.join(dayan_result.tool_sequence) if dayan_result.tool_sequence else None,
                changing_lines=', '.join(f"{l.position}爻({l.yan_type})" for l in changing) if changing else None,
                bian_hexagram=f"{bian[0]}→{bian[2]}" if bian else None,
                elapsed_ms=dayan_result.elapsed_ms,
                session_id=self.session_id,
            )
        except Exception:
            pass  # 日志写入不影响主流程

        # ═══ v3.0: 卦象 → 工具索引提示（参谋模式，非司令模式） ═══
        # 卦象不再生成 ExecutionProfile 硬约束，而是生成参考提示注入 system message
        changing_line_positions = [l.position for l in changing] if changing else []

        tool_hint = generate_tool_hint(
            hexagram_name=dayan_result.hexagram_name,
            changing_lines=changing_line_positions,
            effectiveness=self._gua_effectiveness,
            all_tool_names=[t.name for t in registry.get_all() if t.is_available()],
        )
        # 注入 system message（替代旧的 _inject_profile_constraints）
        self.messages = [
            m for m in self.messages
            if not (m.get("role") == "system" and "[卦象索引]" in m.get("content", ""))
        ]
        self.messages.append({"role": "system", "content": tool_hint})

        if on_progress:
            on_progress(f"☯️ {dayan_result.hexagram_name} → 工具索引已更新")

        # ═══ v1.1: 意图路由 ═══
        from core.intent_router import route, decompose_task, generate_skill_md, save_skill, RoutingResult
        from skills.loader import load_all_skills
        from skills.executor import SkillExecutor

        skills = load_all_skills()
        routing = await route(user_message, skills)

        # v1.3: 缓存 decompose 结果，避免重复调用
        cached_plan = None

        # —— 简单指令：直接走 LLM 对话 ——
        if routing.action == "direct_tool":
            # v1.3: simple 指令也记录路由决策
            execution_log.log_routing_decision(
                user_message,
                candidates=[{"skill": name, "score": round(s, 3)} for name, s in routing.candidates] if routing.candidates else [],
                fallback_to_decompose=False,
            )

        # —— 技能匹配命中：用 SkillExecutor 极速执行 ——
        elif routing.action == "execute_skill" and routing.matched_skill:
            if on_progress:
                on_progress(f"🎯 命中技能「{routing.matched_skill.name}」(置信度 {routing.match_score:.2f})")

            # v2.2: 执行前验证 — 检查工具运行时可用性
            try:
                from skills.validator import validate_skill_before_execute
                is_valid, validate_msg = validate_skill_before_execute(routing.matched_skill)
                if not is_valid:
                    if on_progress:
                        on_progress(f"⚠️ 技能执行前验证失败: {validate_msg}，回退到任务分解")
                    routing = RoutingResult(complexity=routing.complexity, action="decompose")
                    # 跳过后续技能执行，进入 decompose 分支
                else:
                    pass  # 验证通过，继续执行
            except ImportError:
                pass  # 验证模块不存在时跳过

            # 只有验证通过时才执行技能
            if routing.action == "execute_skill":
                executor = SkillExecutor(
                    routing.matched_skill,
                    on_progress=on_progress,
                    on_confirm=on_confirm,
                    session_id=self.session_id,
                )

                skill_result = await executor.execute(user_message)

                # 记录任务执行
                duration_ms = int((time.time() - start_time) * 1000)
                execution_log.log_task(
                    user_input=user_message,
                    matched_skill=routing.matched_skill.name,
                    match_score=routing.match_score,
                    success=skill_result.get("success", False),
                    duration_ms=duration_ms,
                    session_id=self.session_id,
                    time_slot=None,
                    task_type=None,
                )

                # v1.3: 记录路由决策
                execution_log.log_routing_decision(
                    user_message,
                    candidates=[{"skill": name, "score": round(s, 3)} for name, s in routing.candidates] if routing.candidates else [],
                    chosen_skill=routing.matched_skill.name,
                    chosen_score=routing.match_score,
                    fallback_to_decompose=False,
                )

                if skill_result.get("success"):
                    response = f"✅ 已通过技能「{routing.matched_skill.name}」完成任务"
                    # 汇总结果
                    results = skill_result.get("results", [])
                    for r in results:
                        if r.get("llm_response"):
                            response += f"\n{r['llm_response']}"

                    self.messages.append({"role": "assistant", "content": response})
                    self.save_session()
                    return self._build_result(response, 1)
                else:
                    # 技能执行失败，回退到普通对话
                    if on_progress:
                        on_progress(f"⚠️ 技能执行失败，回退到普通对话: {skill_result.get('error', '')}")

        # —— 复杂任务或未命中：模板匹配 → 万物组合 → 分解 → 执行 → 沉淀 ——
        elif routing.action == "decompose":
            # ═══ v1.5.1: 模板匹配（零成本，确定性） ═══
            from core.workflow_templates import try_template
            from core.workflow import WorkflowRunner, format_workflow_result

            tmpl_hit = try_template(user_message)
            if tmpl_hit:
                tmpl, wf_steps = tmpl_hit
                if on_progress:
                    on_progress(f"📐 命中模板「{tmpl.description}」（{len(wf_steps)} 步，零 token）")

                runner = WorkflowRunner(
                    goal=tmpl.description,
                    on_progress=on_progress,
                    on_confirm=on_confirm,
                    session_id=self.session_id,
                    profile=None,  # v3.0: 不再由卦象控制工作流
                )
                wf_result = await runner.execute(wf_steps)

                # 记录模板使用结果
                from core.workflow_templates import get_template_engine
                get_template_engine().record_result(tmpl.name, wf_result.success)

                response = format_workflow_result(wf_result)
                self.messages.append({"role": "assistant", "content": response})

                # 成功的模板执行尝试沉淀为技能
                if wf_result.success and len(wf_steps) >= 2:
                    try:
                        from core.sub_agent import generate_skill_from_orchestration, OrchestrationPlan
                        skill_plan = OrchestrationPlan(
                            goal=tmpl.description,
                            sub_tasks=[{"task": s.action, "tools": [s.tool] if s.tool != "auto" else [], "depends_on": [d - 1 for d in s.depends_on]} for s in wf_steps],
                        )
                        orch_result = {"success": True, "results": [type("R", (), {"success": r.success, "output": r.output})() for r in wf_result.step_results]}
                        skill_name = await generate_skill_from_orchestration(
                            user_message, skill_plan, orch_result, self.session_id
                        )
                        if skill_name and on_progress:
                            on_progress(f"💡 技能已沉淀: {skill_name}")
                    except Exception:
                        pass

                duration_ms = int((time.time() - start_time) * 1000)
                execution_log.log_task(
                    user_input=user_message, success=wf_result.success,
                    duration_ms=duration_ms, session_id=self.session_id,
                    time_slot=None,
                    task_type=None,
                )
                execution_log.log_routing_decision(
                    user_message,
                    candidates=[tmpl.name],
                    chosen_skill=tmpl.name,
                    chosen_score=1.0,
                    fallback_to_decompose=False,
                )
                self.save_session()
                return self._build_result(response, 1)

            if on_progress:
                on_progress("📝 模板未命中，进行任务分解...")

            # v1.3: 只调用一次 decompose_task，缓存结果
            cached_plan = await decompose_task(user_message)

            if cached_plan.get("steps") and not cached_plan.get("error"):
                steps = cached_plan["steps"]
                has_deps = any(s.get("depends_on") for s in steps)

                # ═══ v1.5.1: WorkflowRunner 轻量编排 ═══
                # 2+ 步骤且有依赖 → WorkflowRunner 直接调工具（替代重量级 SubAgent）
                # 无依赖的简单计划 → 注入系统提示让 LLM 串行执行
                if len(steps) >= 2 and has_deps:
                    if on_progress:
                        on_progress(f"⚡ 检测到多步任务（{len(steps)}步，含依赖），启动工作流...")

                    from core.workflow import WorkflowRunner, plan_to_steps, format_workflow_result

                    wf_steps = plan_to_steps(cached_plan, user_input=user_message)
                    runner = WorkflowRunner(
                        goal=user_message,  # P3: 用用户原始输入（含路径），不用 LLM 摘要
                        on_progress=on_progress,
                        on_confirm=on_confirm,
                        session_id=self.session_id,
                        profile=None,  # v3.0: 不再由卦象控制工作流
                    )
                    wf_result = await runner.execute(wf_steps)

                    response = format_workflow_result(wf_result)
                    self.messages.append({"role": "assistant", "content": response})

                    # 成功的工作流尝试沉淀为技能
                    if wf_result.success and len(wf_steps) >= 2:
                        try:
                            from core.sub_agent import generate_skill_from_orchestration
                            from core.sub_agent import OrchestrationPlan
                            skill_plan = OrchestrationPlan(
                                goal=cached_plan.get("goal", user_message),
                                sub_tasks=[{"task": s.action, "tools": [s.tool] if s.tool != "auto" else [], "depends_on": [d - 1 for d in s.depends_on]} for s in wf_steps],
                            )
                            orch_result = {"success": True, "results": [type("R", (), {"success": r.success, "output": r.output})() for r in wf_result.step_results]}
                            skill_name = await generate_skill_from_orchestration(
                                user_message, skill_plan, orch_result, self.session_id
                            )
                            if skill_name and on_progress:
                                on_progress(f"💡 工作流技能已沉淀: {skill_name}")
                        except Exception:
                            pass

                    duration_ms = int((time.time() - start_time) * 1000)
                    execution_log.log_task(
                        user_input=user_message, success=wf_result.success,
                        duration_ms=duration_ms, session_id=self.session_id,
                        time_slot=None,
                        task_type=None,
                    )
                    self.save_session()
                    return self._build_result(response, 1)

                # 常规路径：把计划注入系统提示，让 LLM 串行执行
                plan_text = f"📋 目标：{cached_plan.get('goal', user_message)}\n"
                for step in cached_plan["steps"]:
                    deps = step.get("depends_on", [])
                    dep_str = f" (依赖步骤 {','.join(map(str, deps))})" if deps else ""
                    plan_text += f"  {step['id']}. {step['action']}{dep_str}\n"

                self.messages.append({
                    "role": "system",
                    "content": f"[任务规划]\n{plan_text}\n\n请按以上步骤逐步执行。"
                })

                # v1.3: 记录路由决策
                execution_log.log_routing_decision(
                    user_message,
                    candidates=[{"skill": name, "score": round(s, 3)} for name, s in routing.candidates] if routing.candidates else [],
                    fallback_to_decompose=True,
                )

        # ═══ v1.3: 根据路由结果选择 LLM 客户端 ═══
        # simple → Ollama 本地（低成本），但需要工具时必须走 DeepSeek
        # medium/complex → DeepSeek 云端（高能力）
        # execute_skill → 技能内部决定，这里不走 LLM
        use_ollama = (routing.action == "direct_tool")
        if use_ollama:
            # 如果用户意图涉及工具调用（搜索、打开、运行等），Ollama 不可靠，直接走 DeepSeek
            tool_keywords = ['搜索', '搜一下', '查找', '打开', '运行', '执行', '下载', '截图',
                             '整理', '创建', '删除', '备份', '清理', '分析', '监控']
            if any(kw in user_message for kw in tool_keywords):
                use_ollama = False

        # ═══ 普通 LLM 对话循环 ═══
        # v4.1: 进展追踪 — 防止"停不下来"
        _success_count = 0          # 已获得有效结果的工具调用次数
        _consecutive_failures = 0   # 连续失败计数
        _search_done = False        # 搜索类工具已返回过有效数据
        _MAX_CONSECUTIVE_FAILS = 3  # 连续失败上限

        while self.tool_call_count < config.MAX_TOOL_CALLS_PER_TURN:
            if self.is_cancelled():
                fallback = "操作已被用户取消。"
                self.messages.append({"role": "assistant", "content": fallback})
                return self._build_result(fallback, rounds)

            # v3.0: 卦象提示已在 send() 开头注入 system message，不再每轮注入硬约束

            # PATCH: 只暴露当前环境实际可用的工具，避免 LLM 调用空壳工具
            available_schemas = [
                s for s in registry.get_schemas()
                if registry.get(s["function"]["name"]).is_available()
            ]
            response = await chat(self.messages, tools=available_schemas,
                                  use_ollama=use_ollama)
            rounds += 1

            if "_usage" in response:
                self._token_usage.append(response["_usage"])

            if response.get("_timeout") or response.get("_error"):
                assistant_msg = response["content"]
                self.messages.append({"role": "assistant", "content": assistant_msg})
                return self._build_result(assistant_msg, rounds)

            if "tool_calls" not in response:
                assistant_msg = response["content"]
                self.messages.append({"role": "assistant", "content": assistant_msg})
                memo_count = self._process_memos(assistant_msg)
                tool_summary = ""
                if self.tool_log:
                    recent_tools = self.tool_log[-5:]
                    tool_names = [t["tool"] for t in recent_tools]
                    tool_summary = f"\n工具调用: {', '.join(tool_names)}"
                memo_summary = f"\n自动记忆: {memo_count} 条" if memo_count > 0 else ""
                self.memory.save_daily(
                    f"用户: {user_message[:200]}\n"
                    f"助手: {assistant_msg[:200]}{tool_summary}{memo_summary}"
                )

                # v1.4: 分解模式下，任务成功时自动沉淀为 skill.md
                # v2.0: 先暂存到 staging，人工确认后生效
                # 步骤 >= 2 且没有同名技能时才生成（避免简单操作塞满 skills/）
                if routing.action == "decompose" and self.tool_call_count >= 1:
                    try:
                        if cached_plan and cached_plan.get("skill_name"):
                            # 检查是否已有同名技能
                            from skills.loader import load_all_skills
                            existing = [s.name for s in load_all_skills()]
                            if cached_plan["skill_name"] not in existing:
                                skill_md = await generate_skill_md(user_message, cached_plan, [])
                                if skill_md:
                                    from skills.staging import SkillStaging
                                    staging = SkillStaging()
                                    staging.stage(cached_plan["skill_name"], skill_md)
                                    if on_progress:
                                        on_progress(f"💡 新技能已暂存: {cached_plan['skill_name']}（需 --approve-skills 确认）")
                    except Exception:
                        pass  # 技能生成失败不影响正常回复

                # 记录任务执行
                duration_ms = int((time.time() - start_time) * 1000)
                execution_log.log_task(
                    user_input=user_message,
                    matched_skill=routing.matched_skill.name if routing.matched_skill else None,
                    match_score=routing.match_score,
                    success=True,
                    duration_ms=duration_ms,
                    session_id=self.session_id,
                    time_slot=None,
                    task_type=None,
                )

                self.save_session()
                return self._build_result(assistant_msg, rounds)

            self.messages.append(response)
            # v4.2: 按实际 tool_call 数量计数（而非每轮只 +1）
            num_calls = len(response.get("tool_calls", []))
            self.tool_call_count += max(num_calls, 1)

            # v3.1: 工具调用死循环检测 — 同工具同参数连续调用 3 次 → 注入警告
            _recent_tool_sigs = []
            for _m in self.messages[-10:]:
                if _m.get("role") == "assistant" and "tool_calls" in _m:
                    for _tc in _m["tool_calls"]:
                        _fn = _tc.get("function", {})
                        _sig = f"{_fn.get('name', '')}:{_fn.get('arguments', '')[:80]}"
                        _recent_tool_sigs.append(_sig)
            if len(_recent_tool_sigs) >= 3:
                _last3 = _recent_tool_sigs[-3:]
                if len(set(_last3)) == 1:
                    self.messages.append({
                        "role": "system",
                        "content": (
                            f"[循环检测] 你已经连续 3 次调用相同的工具 {_last3[0].split(':')[0]}，"
                            f"参数也完全相同。这说明当前方法无效。请换一种方式完成任务：\n"
                            f"- 如果是浏览器操作，尝试用 ab_fill 输入文字、ab_click 点击按钮\n"
                            f"- 如果是搜索，尝试换一个搜索关键词或工具\n"
                            f"- 如果多次失败，请直接告诉用户遇到了什么问题"
                        ),
                    })

            # Phase 3: 每 20 次工具调用触发后台自优化（不阻塞本次响应）
            if self.tool_call_count % 20 == 0 and self.tool_call_count > 0:
                asyncio.create_task(self._run_optimization_background())

            if response.get("content"):
                self._process_memos(response["content"])

            for tc in response["tool_calls"]:
                if self.is_cancelled():
                    cancel_result = json.dumps({"cancelled": True, "message": "操作已被用户取消。"})
                    self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": cancel_result})
                    continue

                func_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                result = await self._execute_tool(func_name, args, on_confirm=on_confirm)

                # Vision 自动分析截图
                if func_name == "ab_screenshot" and "base64" in result:
                    try:
                        result_data = json.loads(result)
                        if result_data.get("base64") and not result_data.get("error"):
                            from tools.vision import analyze_screenshot_sync
                            vision = analyze_screenshot_sync(result_data["base64"])
                            if not vision.get("error"):
                                result_data["vision_analysis"] = vision
                                result = json.dumps(result_data, ensure_ascii=False)
                    except (json.JSONDecodeError, Exception):
                        pass

                self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

                # v4.1: 进展追踪 — 判断工具是否产生了有效结果
                _tool_had_result = False
                try:
                    _parsed = json.loads(result)
                    if isinstance(_parsed, dict):
                        # 搜索工具有 data/results 字段 → 有效
                        if _parsed.get("data") or _parsed.get("results") or _parsed.get("success"):
                            _tool_had_result = True
                        # 浏览器快照有 content/text → 有效
                        if _parsed.get("content") or _parsed.get("text") or _parsed.get("base64"):
                            _tool_had_result = True
                        # 明确失败不算有效
                        if _parsed.get("error") or _parsed.get("_tool_failed"):
                            _tool_had_result = False
                except (json.JSONDecodeError, TypeError):
                    # 非 JSON 结果，有内容就算有效
                    if result and len(str(result)) > 20:
                        _tool_had_result = True

                if _tool_had_result:
                    _success_count += 1
                    _consecutive_failures = 0
                    if func_name in ("web_search", "search", "ddg_search"):
                        _search_done = True
                else:
                    _consecutive_failures += 1

                # 搜索已有结果 + LLM 还在调工具 → 告诉它该收手了
                if _search_done and _success_count >= 2 and self.tool_call_count >= 3:
                    self.messages.append({
                        "role": "system",
                        "content": (
                            "[提示] 你已经获取到了搜索结果，请不要再调用工具。"
                            "直接根据已有信息总结回复用户。"
                        ),
                    })

                # 连续失败太多次 → 强制终止
                if _consecutive_failures >= _MAX_CONSECUTIVE_FAILS:
                    self.messages.append({
                        "role": "system",
                        "content": (
                            f"[提示] 连续 {_consecutive_failures} 次工具调用未产生有效结果，"
                            f"请停止调用工具，直接告诉用户当前遇到了什么问题。"
                        ),
                    })

                # GUI 操作后自动验证
                GUI_VERIFY_TOOLS = {"ab_click", "ab_fill", "ab_type", "ab_press", "ab_dblclick", "ab_check", "ab_uncheck", "ab_select"}
                if func_name in GUI_VERIFY_TOOLS:
                    try:
                        tool_result = json.loads(result)
                        # PATCH: 工具失败时不要浪费一次截图验证
                        if tool_result.get("success") and not tool_result.get("_tool_failed"):
                            verify_result = await self._execute_tool("ab_screenshot", {"full_page": False}, on_confirm=on_confirm)
                            try:
                                verify_data = json.loads(verify_result)
                                if verify_data.get("base64") and not verify_data.get("error"):
                                    from tools.vision import analyze_screenshot_sync
                                    vision = analyze_screenshot_sync(verify_data["base64"], f"刚才执行了 {func_name} 操作，请判断操作是否成功。简短回答。")
                                    if not vision.get("error"):
                                        verify_data["verification"] = vision.get("description", "操作已执行")
                                        verify_result = json.dumps(verify_data, ensure_ascii=False)
                            except Exception:
                                pass
                            self.messages.append({"role": "system", "content": f"[操作验证] {func_name} 执行后截图: {verify_result[:500]}"})
                    except (json.JSONDecodeError, Exception):
                        pass

            # v1.3.4: 每轮工具调用后检查是否需要压缩上下文
            self._trim_context()

        # P1 修复：区分"工作流已完成但 LLM 还在调工具"和"真的卡住了"
        recent_success = any(
            not t.get("error")
            for t in self.tool_log[-5:]
        )
        if recent_success:
            fallback = (
                "⚠️ 任务已基本完成，但工具调用次数达到上限，自动停止。"
                "如果还有遗漏，请单独告诉我。"
            )
        else:
            fallback = f"⚠️ 工具调用次数达到上限（{config.MAX_TOOL_CALLS_PER_TURN}次），任务未完成。请简化请求或分步操作。"
        self.messages.append({"role": "assistant", "content": fallback})
        self.save_session()
        return self._build_result(fallback, rounds)

    def _build_result(self, response: str, rounds: int) -> dict:
        total_prompt = sum(u.get("prompt_tokens", 0) for u in self._token_usage)
        total_completion = sum(u.get("completion_tokens", 0) for u in self._token_usage)
        total_tokens = sum(u.get("total_tokens", 0) for u in self._token_usage)
        estimated_cost = (total_prompt * 0.5 + total_completion * 2.0) / 1_000_000
        return {
            "response": response,
            "tool_calls": self.tool_log[-10:],
            "stats": {
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "total_tokens": total_tokens,
                "tool_calls_count": self.tool_call_count,
                "rounds": rounds,
                "estimated_cost_cny": round(estimated_cost, 4),
            }
        }

    # ═══ 工具 ═══

    # ═══ Phase 3: 后台自我优化 ═══

    async def _run_optimization_background(self):
        """后台执行自我优化周期，不抛异常影响主流程"""
        try:
            from core.self_optimizer import self_optimization_cycle
            from data.execution_log import get_recent_tool_calls
            from core.workflow_templates import get_template_engine

            logs = get_recent_tool_calls(limit=50)
            if not logs:
                return

            engine = get_template_engine()
            await self_optimization_cycle(
                self._gua_effectiveness,
                logs,
                engine.templates,
                registry
            )
        except Exception:
            import logging
            logging.getLogger("conversation").debug("后台优化已跳过", exc_info=True)

    def get_history(self) -> list[dict]:
        return [m for m in self.messages if m["role"] != "system"]

    def get_tool_log(self) -> list[dict]:
        return self.tool_log

    def reset(self):
        if self._browser_session:
            self._browser_session.close()
            self._browser_session = None
        self.messages = []
        self.tool_log = []
        self._token_usage = []
        self._init_system()
        self.save_session()


class ConversationManager:
    """多会话管理"""

    def __init__(self):
        self.sessions: dict[str, Conversation] = {}
        atexit.register(self._cleanup_all)

    def _cleanup_all(self):
        for conv in self.sessions.values():
            if conv._browser_session:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(conv.cleanup())
                    else:
                        loop.run_until_complete(conv.cleanup())
                except Exception:
                    pass

    def get_or_create(self, session_id: str = "default") -> Conversation:
        if session_id not in self.sessions:
            self.sessions[session_id] = Conversation(session_id)
        return self.sessions[session_id]

    def list_sessions(self) -> list[str]:
        return list(self.sessions.keys())

    def delete_session(self, session_id: str):
        conv = self.sessions.pop(session_id, None)
        if conv:
            try:
                os.remove(conv._session_path())
            except OSError:
                pass
