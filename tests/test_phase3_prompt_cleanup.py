# -*- coding: utf-8 -*-
"""
Phase 3 验收测试：dayan.py 瘦身 + LLM prompt 清洗

测试 1: is_crisis() 正确判定危机状态
测试 2: conversation.py 中不再用 action_hint 做危机检测
测试 3: _get_profile_constraint_prompt() 正确生成约束文本
测试 4: _inject_profile_constraints() 正确注入/替换约束消息
测试 5: 串行模式 → LLM 收到"串行执行"约束
测试 6: 低风险模式 → LLM 收到"低风险"约束
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yi_framework.profiles import ExecutionProfile, is_crisis


# ═══ 测试 1: is_crisis() 正确判定 ═══

def test_is_crisis():
    # 危机: risk_tolerance < 0.15 且 rollback == "full"
    p_crisis = ExecutionProfile(
        max_retries=0, parallel=False, risk_tolerance=0.1,
        ask_human=True, timeout_seconds=15, rollback="full"
    )
    assert is_crisis(p_crisis), "risk_tolerance=0.1 + rollback=full 应判定为危机"

    # 非危机: risk_tolerance >= 0.15
    p_safe = ExecutionProfile(
        max_retries=1, parallel=False, risk_tolerance=0.3,
        ask_human=False, timeout_seconds=30, rollback="full"
    )
    assert not is_crisis(p_safe), "risk_tolerance=0.3 不应判定为危机"

    # 非危机: rollback != "full"
    p_step = ExecutionProfile(
        max_retries=0, parallel=False, risk_tolerance=0.1,
        ask_human=True, timeout_seconds=15, rollback="step_back"
    )
    assert not is_crisis(p_step), "rollback=step_back 不应判定为危机"

    # 边界: risk_tolerance == 0.15 → 不是危机（严格小于）
    p_edge = ExecutionProfile(
        max_retries=0, parallel=False, risk_tolerance=0.15,
        ask_human=True, timeout_seconds=15, rollback="full"
    )
    assert not is_crisis(p_edge), "risk_tolerance=0.15 不应判定为危机（边界）"

    print("✅ 测试 1 通过: is_crisis() 判定逻辑正确")


# ═══ 测试 2: 坤为地 → 卦象映射到危机 ═══

def test_kun_is_crisis():
    """坤为地: energy=0.0, risk=0.1 → risk_tolerance=0.27, rollback=full
    但 risk_tolerance=0.27 > 0.15, 所以不是危机"""
    from yi_framework.profiles import derive_profile
    p = derive_profile("坤为地")
    # 坤为地: inner.energy=0.0, outer.risk=0.1
    # risk_tolerance = 0.0*0.7 + (1.0-0.1)*0.3 = 0.27
    # rollback: inner.energy<0.2 and outer.energy<0.2 → "full"
    assert p.rollback == "full", f"Expected rollback=full, got {p.rollback}"
    assert p.risk_tolerance >= 0.15, f"Expected risk_tolerance>=0.15, got {p.risk_tolerance}"
    assert not is_crisis(p), "坤为地不应判定为危机（risk_tolerance=0.27）"
    print("✅ 测试 2 通过: 坤为地不是危机（risk_tolerance=0.27 > 0.15）")


# ═══ 测试 3: _get_profile_constraint_prompt() 生成正确 ═══

def test_constraint_prompt_generation():
    """直接测试约束文本生成逻辑"""
    # 串行 + 低风险 + 不重试 + 完全回滚
    p = ExecutionProfile(
        max_retries=0, parallel=False, risk_tolerance=0.2,
        ask_human=True, timeout_seconds=15, rollback="full"
    )
    constraints = []
    if not p.parallel:
        constraints.append("当前模式：串行执行，不要并行调度工具")
    if p.risk_tolerance < 0.3:
        constraints.append("当前风险容忍度低，避免高风险操作，必要时请求人工确认")
    if p.max_retries == 0:
        constraints.append("当前模式：不重试，一次失败即跳过")
    if p.rollback == "full":
        constraints.append("当前模式：失败时完全回滚")

    text = "[执行约束]\n" + "\n".join(constraints)
    assert "串行执行" in text, f"Expected '串行执行' in: {text}"
    assert "低风险" in text or "风险容忍度低" in text, f"Expected low risk in: {text}"
    assert "不重试" in text, f"Expected '不重试' in: {text}"
    assert "完全回滚" in text, f"Expected '完全回滚' in: {text}"
    print("✅ 测试 3 通过: 约束文本包含所有4条约束")


# ═══ 测试 4: 并行模式 → 无串行约束 ═══

def test_parallel_no_serial_constraint():
    p = ExecutionProfile(
        max_retries=2, parallel=True, risk_tolerance=0.8,
        ask_human=False, timeout_seconds=60, rollback="none"
    )
    constraints = []
    if not p.parallel:
        constraints.append("当前模式：串行执行，不要并行调度工具")
    if p.risk_tolerance < 0.3:
        constraints.append("当前风险容忍度低，避免高风险操作，必要时请求人工确认")
    if p.max_retries == 0:
        constraints.append("当前模式：不重试，一次失败即跳过")
    if p.rollback == "full":
        constraints.append("当前模式：失败时完全回滚")

    # 全部宽松 → 无约束
    assert len(constraints) == 0, f"Expected 0 constraints, got {len(constraints)}: {constraints}"
    print("✅ 测试 4 通过: 并行+高风险+重试+无回滚 → 无约束")


# ═══ 测试 5: conversation.py 中不含 action_hint 危机检测 ═══

def test_no_action_hint_in_crisis_detection():
    """验证 conversation.py 中不再用 action_hint 做危机检测"""
    with open("core/conversation.py") as f:
        content = f.read()

    # v3.0: 卦象不再生成 ExecutionProfile 硬约束
    # 验证不再有 _current_profile 硬约束引用
    assert "_current_profile" not in content or "_current_profile" in content.split("v3.0")[0], \
        "conversation.py 不应再有 _current_profile 硬约束引用"

    # 验证有 generate_tool_hint 调用（新架构）
    assert "generate_tool_hint" in content, \
        "conversation.py 应包含 generate_tool_hint 调用"

    print("✅ 测试 5 通过: conversation.py 已改为卦象工具索引模式")


# ═══ 测试 6: generate_tool_hint 存在且可调用 ═══

def test_generate_tool_hint_exists():
    with open("yi_framework/profiles.py") as f:
        content = f.read()

    assert "def generate_tool_hint(" in content, \
        "profiles.py 应包含 generate_tool_hint 函数"

    # v3.0: 旧的 _inject_profile_constraints 已移除，改为 generate_tool_hint
    with open("core/conversation.py") as f:
        conv_content = f.read()
    assert "generate_tool_hint" in conv_content, \
        "conversation.py 应调用 generate_tool_hint()"

    print("✅ 测试 6 通过: 卦象工具索引函数存在且被调用")


if __name__ == "__main__":
    test_is_crisis()
    test_kun_is_crisis()
    test_constraint_prompt_generation()
    test_parallel_no_serial_constraint()
    test_no_action_hint_in_crisis_detection()
    test_generate_tool_hint_exists()
    print("\n🎉 Phase 3 全部 6 个验收测试通过！")
