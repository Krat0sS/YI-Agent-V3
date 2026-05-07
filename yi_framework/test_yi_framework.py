# -*- coding: utf-8 -*-
"""
YI-Framework 单元测试

运行: python -m pytest yi_framework/test_yi_framework.py -v
"""

import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yi_framework.profiles import (
    ExecutionProfile, derive_profile, TRIGRAM_ATTRIBUTES,
    HEXAGRAM_NAMES, HEXAGRAM_REVERSE, get_all_profiles, format_profile
)
from yi_framework.runtime import YiRuntime, StrategyChangeEvent
from yi_framework.effectiveness import GuaToolEffectiveness


# ═══════════════════════════════════════════════════════════
# Test 1: ExecutionProfile 推导
# ═══════════════════════════════════════════════════════════

def test_profile_derivation_qian():
    """乾为天: 纯阳，全速执行"""
    p = derive_profile("乾为天")
    assert p.max_retries == 0, f"乾为天 max_retries 应为0，实际为{p.max_retries}"
    assert p.parallel == True, f"乾为天 parallel 应为True"
    assert p.risk_tolerance > 0.6, f"乾为天 risk_tolerance 应>0.6，实际为{p.risk_tolerance}"
    assert p.ask_human == False, f"乾为天 ask_human 应为False"
    assert p.rollback == "none", f"乾为天 rollback 应为none，实际为{p.rollback}"
    print(f"✅ 乾为天: {p}")


def test_profile_derivation_kun():
    """坤为地: 纯阴，完全停止"""
    p = derive_profile("坤为地")
    assert p.max_retries == 0, f"坤为地 max_retries 应为0"
    assert p.parallel == False, f"坤为地 parallel 应为False"
    assert p.risk_tolerance < 0.3, f"坤为地 risk_tolerance 应<0.3，实际为{p.risk_tolerance}"
    assert p.ask_human == True, f"坤为地 ask_human 应为True"
    assert p.rollback == "full", f"坤为地 rollback 应为full，实际为{p.rollback}"
    print(f"✅ 坤为地: {p}")


def test_profile_derivation_kan():
    """坎为水: 高风险，需谨慎"""
    p = derive_profile("坎为水")
    assert p.max_retries >= 2, f"坎为水 max_retries 应>=2，实际为{p.max_retries}"
    assert p.risk_tolerance < 0.4, f"坎为水 risk_tolerance 应<0.4，实际为{p.risk_tolerance}"
    assert p.rollback == "step_back", f"坎为水 rollback 应为step_back，实际为{p.rollback}"
    print(f"✅ 坎为水: {p}")


def test_profile_derivation_zhen():
    """震为雷: 行动力强"""
    p = derive_profile("震为雷")
    assert p.max_retries <= 1, f"震为雷 max_retries 应<=1，实际为{p.max_retries}"
    assert p.timeout_seconds > 30, f"震为雷 timeout 应>30s，实际为{p.timeout_seconds}"
    print(f"✅ 震为雷: {p}")


def test_profile_derivation_gen():
    """艮为山: 静止等待"""
    p = derive_profile("艮为山")
    assert p.max_retries == 0, f"艮为山 max_retries 应为0"
    assert p.ask_human == True, f"艮为山 ask_human 应为True"
    print(f"✅ 艮为山: {p}")


def test_all_64_profiles_valid():
    """全部64卦都能生成有效Profile"""
    profiles = get_all_profiles()
    assert len(profiles) == 64, f"应有64卦，实际有{len(profiles)}"
    
    for name, p in profiles.items():
        assert isinstance(p, ExecutionProfile), f"{name} 不是ExecutionProfile"
        assert 0 <= p.max_retries <= 3, f"{name} max_retries 越界: {p.max_retries}"
        assert 0.0 <= p.risk_tolerance <= 1.0, f"{name} risk_tolerance 越界: {p.risk_tolerance}"
        assert p.timeout_seconds > 0, f"{name} timeout 应>0"
        assert p.rollback in ("none", "step_back", "full"), f"{name} rollback 无效: {p.rollback}"
    
    print(f"✅ 全部64卦Profile有效")


def test_unknown_hexagram():
    """未知卦名返回安全默认值"""
    p = derive_profile("不存在的卦")
    assert p.ask_human == True, "未知卦应求助人类"
    assert p.rollback == "step_back", "未知卦应step_back"
    print(f"✅ 未知卦安全默认值: {p}")


# ═══════════════════════════════════════════════════════════
# Test 2: YiRuntime 动爻检测
# ═══════════════════════════════════════════════════════════

def test_runtime_initial_state():
    """初始状态为坤为地"""
    rt = YiRuntime()
    assert rt.current_hexagram == "坤为地", f"初始卦应为坤为地，实际为{rt.current_hexagram}"
    p = rt.get_current_profile()
    assert p.ask_human == True, "初始状态应求助人类"
    print(f"✅ 初始状态: {rt.current_hexagram}")


def test_runtime_tick_success():
    """连续成功 → 向阳卦变化"""
    rt = YiRuntime()
    initial = rt.current_hexagram
    
    # 连续注入成功
    for i in range(5):
        rt.tick({'success': True, 'completion': i / 5})
    
    final = rt.current_hexagram
    vector = rt.get_vector()
    
    # 成功后向量应该上升
    assert vector[1] > 0.5, f"连续成功后进展应>0.5，实际为{vector[1]}"
    print(f"✅ 连续成功: {initial} → {final}, 向量={vector}")


def test_runtime_tick_failure_cascade():
    """连续失败触发动爻，Profile从积极变消极"""
    rt = YiRuntime()
    
    # 先注入成功建立积极态势
    for _ in range(5):
        rt.tick({'success': True, 'resource_level': 0.8})
    
    profile_before = rt.current_profile
    print(f"  成功后: {rt.current_hexagram}, retries={profile_before.max_retries}")
    
    # 连续注入失败，同时记录是否触发翻转
    change_triggered = False
    for i in range(15):
        event = rt.tick({'success': False, 'resource_level': 0.3})
        if event:
            change_triggered = True
            print(f"  动爻触发在第{i+1}次: {event.from_hexagram} → {event.to_hexagram}")
            print(f"  原因: {event.reason}")
            print(f"  工具索引提示: {event.hint[:100]}...")
            break
    
    assert change_triggered, "连续失败应触发动爻"
    
    profile_after = rt.current_profile
    # 翻转后应该更谨慎
    assert profile_after.max_retries >= profile_before.max_retries or \
           profile_after.ask_human == True or \
           profile_after.rollback != "none", \
        "翻转后应更谨慎"
    
    print(f"✅ 动爻触发: Profile从积极变消极")


def test_runtime_no_oscillation():
    """动爻不应频繁抖动（迟滞机制）"""
    rt = YiRuntime()
    
    # 在临界值附近快速切换
    events = []
    for i in range(20):
        # 交替成功失败，模拟临界值附近
        result = {'success': i % 2 == 0}
        event = rt.tick(result)
        if event:
            events.append(event)
    
    # 2秒内不应有多个翻转
    rapid_events = [e for e in events if len(events) > 1]
    assert len(events) <= 2, f"不应频繁翻转，实际翻转{len(events)}次"
    print(f"✅ 迟滞机制: 20次交替操作只翻转{len(events)}次")


# ═══════════════════════════════════════════════════════════
# Test 3: GuaToolEffectiveness 学习
# ═══════════════════════════════════════════════════════════

def test_effectiveness_record_and_query():
    """记录并查询工具效果"""
    # 使用临时数据库
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        eff = GuaToolEffectiveness(db_path)
        
        # 记录多次执行
        for _ in range(8):
            eff.record("乾为天", "ab_click", success=True, duration_ms=100)
        for _ in range(2):
            eff.record("乾为天", "ab_click", success=False, duration_ms=200)
        
        for _ in range(5):
            eff.record("乾为天", "file_read", success=True, duration_ms=50)
        
        # 查询
        best = eff.query_best_tools("乾为天", ["ab_click", "file_read", "ab_open"])
        
        assert len(best) == 3, f"应返回3个工具，实际{len(best)}"
        
        # file_read 应排第一（100%成功率 + 更快）
        assert best[0].tool_name == "file_read", f"最佳工具应为file_read，实际为{best[0].tool_name}"
        
        # ab_click 排第二（80%成功率）
        assert best[1].tool_name == "ab_click", f"第二应为ab_click"
        assert abs(best[1].success_rate - 0.8) < 0.01, f"ab_click 成功率应为0.8"
        
        # ab_open 无数据，默认0.5
        assert best[2].tool_name == "ab_open"
        assert best[2].success_rate == 0.5, f"无数据工具应为0.5"
        
        print(f"✅ 工具效果查询正确")
        
    finally:
        os.unlink(db_path)


def test_effectiveness_learning_loop():
    """模拟学习闭环：第一次慢，第二次快"""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        eff = GuaToolEffectiveness(db_path)
        
        # 第一次：不知道哪个工具好
        best1 = eff.query_best_tools("乾为天", ["tool_a", "tool_b", "tool_c"])
        assert all(t.success_rate == 0.5 for t in best1), "第一次应全部中性"
        
        # 模拟执行：tool_a 成功率高
        for _ in range(10):
            eff.record("乾为天", "tool_a", success=True, duration_ms=80)
        for _ in range(10):
            eff.record("乾为天", "tool_b", success=False, duration_ms=200)
        eff.record("乾为天", "tool_c", success=True, duration_ms=150)
        
        # 第二次：应该推荐 tool_a
        best2 = eff.query_best_tools("乾为天", ["tool_a", "tool_b", "tool_c"])
        assert best2[0].tool_name == "tool_a", f"应推荐tool_a，实际为{best2[0].tool_name}"
        assert best2[0].success_rate == 1.0, f"tool_a成功率应为1.0"
        
        print(f"✅ 学习闭环: 第一次中性，第二次推荐最优工具")
        
    finally:
        os.unlink(db_path)


# ═══════════════════════════════════════════════════════════
# 运行所有测试
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("YI-Framework 单元测试")
    print("=" * 60)
    
    tests = [
        # Profile 推导
        test_profile_derivation_qian,
        test_profile_derivation_kun,
        test_profile_derivation_kan,
        test_profile_derivation_zhen,
        test_profile_derivation_gen,
        test_all_64_profiles_valid,
        test_unknown_hexagram,
        # Runtime 动爻
        test_runtime_initial_state,
        test_runtime_tick_success,
        test_runtime_tick_failure_cascade,
        test_runtime_no_oscillation,
        # Effectiveness 学习
        test_effectiveness_record_and_query,
        test_effectiveness_learning_loop,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {test.__name__}: {type(e).__name__}: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败 / {len(tests)} 总计")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)
