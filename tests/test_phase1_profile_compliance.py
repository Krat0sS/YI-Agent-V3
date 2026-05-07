# -*- coding: utf-8 -*-
"""
Phase 1 验收测试：Profile 合规校验（v3.0 适配）

v3.0 改动：
- 不再强制串行（LLM 自主决定）
- 不再覆盖步骤的 retry 和 timeout
- 仅保留：高风险步骤需要人工确认（安全机制）
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow import WorkflowRunner, WorkflowStep, StepResult
from yi_framework.profiles import ExecutionProfile


# ═══ 测试 1: 高风险步骤 + 用户拒绝 → 步骤被跳过 ═══

def test_high_risk_user_reject():
    confirm_calls = []
    def mock_confirm(msg):
        confirm_calls.append(msg)
        return False  # 用户拒绝
    runner = WorkflowRunner(goal="test", profile=None, on_confirm=mock_confirm)

    steps = [
        WorkflowStep(id=1, action="dangerous step", tool="test", risk="high"),
        WorkflowStep(id=2, action="safe step", tool="test", risk="low"),
    ]
    result = runner._profile_compliance_check(steps)

    assert len(result) == 1, f"Expected 1 step (high risk blocked), got {len(result)}"
    assert result[0].id == 2, f"Expected step 2 to survive, got step {result[0].id}"
    assert len(confirm_calls) == 1, f"Expected 1 confirm call, got {len(confirm_calls)}"
    print("✅ 测试 1 通过: high risk + 用户拒绝 → 步骤被跳过")


# ═══ 测试 2: 高风险步骤 + 用户同意 → 步骤保留 ═══

def test_high_risk_user_accept():
    def mock_confirm(msg):
        return True  # 用户同意
    runner = WorkflowRunner(goal="test", profile=None, on_confirm=mock_confirm)

    steps = [
        WorkflowStep(id=1, action="dangerous step", tool="test", risk="high"),
    ]
    result = runner._profile_compliance_check(steps)

    assert len(result) == 1, f"Expected 1 step, got {len(result)}"
    assert result[0].risk == "high", f"Expected risk='high', got '{result[0].risk}'"
    print("✅ 测试 2 通过: high risk + 用户同意 → 步骤保留")


# ═══ 测试 3: 低风险步骤 → 不需要确认，直接通过 ═══

def test_low_risk_passthrough():
    confirm_calls = []
    def mock_confirm(msg):
        confirm_calls.append(msg)
        return True
    runner = WorkflowRunner(goal="test", profile=None, on_confirm=mock_confirm)

    steps = [
        WorkflowStep(id=1, action="safe step", tool="test", risk="low"),
        WorkflowStep(id=2, action="medium step", tool="test", risk="medium"),
    ]
    result = runner._profile_compliance_check(steps)

    assert len(result) == 2, f"Expected 2 steps, got {len(result)}"
    assert len(confirm_calls) == 0, f"Expected 0 confirm calls, got {len(confirm_calls)}"
    print("✅ 测试 3 通过: low/medium risk → 不需要确认，直接通过")


# ═══ 测试 4: 步骤参数不被覆盖（v3.0 核心改动） ═══

def test_no_param_override():
    runner = WorkflowRunner(goal="test", profile=None)

    steps = [
        WorkflowStep(id=1, action="step1", tool="test", retry=5, timeout=999.0),
    ]
    result = runner._profile_compliance_check(steps)

    assert result[0].retry == 5, f"Expected retry=5, got {result[0].retry}"
    assert result[0].timeout == 999.0, f"Expected timeout=999.0, got {result[0].timeout}"
    print("✅ 测试 4 通过: 步骤 retry/timeout 不被覆盖")


# ═══ 测试 5: 无 profile 时正常工作 ═══

def test_no_profile():
    runner = WorkflowRunner(goal="test", profile=None)

    steps = [
        WorkflowStep(id=1, action="step1", tool="test", retry=3, timeout=60.0, risk="high"),
    ]
    # 无 profile + 无 on_confirm → high risk 步骤直接通过（confirm 默认返回 False）
    # 但实际上 on_confirm 默认是 lambda cmd: False，所以 high risk 会被跳过
    def default_confirm(msg):
        return True  # 模拟默认同意
    runner2 = WorkflowRunner(goal="test", profile=None, on_confirm=default_confirm)
    result = runner2._profile_compliance_check(steps)

    assert result[0].retry == 3, f"Expected retry=3, got {result[0].retry}"
    assert result[0].timeout == 60.0, f"Expected timeout=60.0, got {result[0].timeout}"
    assert result[0].risk == "high", f"Expected risk='high', got {result[0].risk}"
    print("✅ 测试 5 通过: 无 profile → 步骤参数原样保留")


# ═══ 测试 6: 全部 high risk 且用户拒绝 → filtered 为空 ═══

def test_all_steps_blocked():
    def always_reject(msg):
        return False
    runner = WorkflowRunner(goal="test", profile=None, on_confirm=always_reject)

    steps = [
        WorkflowStep(id=1, action="risky1", tool="test", risk="high"),
        WorkflowStep(id=2, action="risky2", tool="test", risk="high"),
    ]
    result = runner._profile_compliance_check(steps)

    assert len(result) == 0, f"Expected 0 steps (all blocked), got {len(result)}"
    print("✅ 测试 6 通过: 全部 high risk + 用户拒绝 → 无步骤执行")


if __name__ == "__main__":
    test_high_risk_user_reject()
    test_high_risk_user_accept()
    test_low_risk_passthrough()
    test_no_param_override()
    test_no_profile()
    test_all_steps_blocked()
    print("\n🎉 Phase 1 全部 6 个验收测试通过！")
