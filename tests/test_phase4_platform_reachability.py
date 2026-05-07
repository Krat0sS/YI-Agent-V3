# -*- coding: utf-8 -*-
"""
Phase 4 验收测试：平台可达性扩展 d1

测试 1: PlatformReachability 全 False → score() == 0.0
测试 2: Android 断连 → d1_resource 下降
测试 3: 平台不可达的工具不出现在 get_available() 中
测试 4: d1 和 d2 维度正交（互不依赖同一信号）
测试 5: 单平台 → score == 1.0（不被压到 0.5）
测试 6: set_platform_filter 过滤正确
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yi_framework.platform import PlatformReachability
from yi_framework.runtime import YiRuntime
from tools.registry import ToolRegistry, ToolDefinition


# ═══ 测试 1: 全 False → score == 0.0 ═══

def test_all_false():
    p = PlatformReachability(windows=False, linux_ssh=False, android_adb=False)
    assert p.score() == 0.0, f"Expected 0.0, got {p.score()}"
    assert p.available_platforms() == [], f"Expected [], got {p.available_platforms()}"
    print("✅ 测试 1 通过: 全 False → score=0.0, 无可用平台")


# ═══ 测试 2: Android 断连 → d1 下降 ═══

def test_android_disconnect_drops_d1():
    rt = YiRuntime()
    rt._min_change_interval = 0

    # 全平台连接
    full_platform = PlatformReachability(windows=True, linux_ssh=True, android_adb=True)
    rt.tick({'success': True, 'duration_ms': 500}, platform=full_platform)
    d1_full = rt.vector[0]

    # Android 断连
    partial_platform = PlatformReachability(windows=True, linux_ssh=True, android_adb=False)
    rt.tick({'success': True, 'duration_ms': 500}, platform=partial_platform)
    d1_partial = rt.vector[0]

    # d1 应该下降（平台可达性降低）
    assert d1_partial < d1_full, f"d1 should drop: {d1_full} → {d1_partial}"
    print(f"✅ 测试 2 通过: Android 断连 → d1 下降: {d1_full:.3f} → {d1_partial:.3f}")


# ═══ 测试 3: 平台不可达的工具被过滤 ═══

def test_platform_filter_in_registry():
    reg = ToolRegistry()

    # 注册一个 windows-only 工具
    reg.register(
        name="win_tool",
        description="Windows only",
        schema={},
        handler=lambda: "ok",
        platform="windows",
    )

    # 注册一个 any 平台工具
    reg.register(
        name="any_tool",
        description="Any platform",
        schema={},
        handler=lambda: "ok",
        platform="any",
    )

    # 注册一个 android 工具
    reg.register(
        name="adb_tool",
        description="Android only",
        schema={},
        handler=lambda: "ok",
        platform="android",
    )

    # 无过滤时，全部可用
    available = reg.get_available()
    names = [t.name for t in available]
    assert "win_tool" in names, "win_tool should be available without filter"
    assert "adb_tool" in names, "adb_tool should be available without filter"

    # 设置平台过滤：只允许 windows 和 any
    def windows_filter(platform):
        return platform in ("windows", "any")

    reg.set_platform_filter(windows_filter)
    available = reg.get_available()
    names = [t.name for t in available]
    assert "win_tool" in names, "win_tool should pass windows filter"
    assert "any_tool" in names, "any_tool should pass any filter"
    assert "adb_tool" not in names, "adb_tool should NOT pass windows filter"

    # 清除过滤
    reg.set_platform_filter(None)
    available = reg.get_available()
    names = [t.name for t in available]
    assert "adb_tool" in names, "adb_tool should be available after clearing filter"

    # 清理
    reg.unregister("win_tool")
    reg.unregister("any_tool")
    reg.unregister("adb_tool")

    print("✅ 测试 3 通过: 平台过滤正确 — 不可达工具被排除")


# ═══ 测试 4: d1 和 d2 正交 ═══

def test_d1_d2_orthogonal():
    rt = YiRuntime()

    # 多次成功，d2 应该高
    for _ in range(5):
        rt.tick({'success': True, 'duration_ms': 200})
    d2_after_success = rt.vector[1]

    # d1 由耗时+平台决定，不由成功率决定
    # 耗时 200ms → time_score = max(0.2, 1.0 - 200/6000) = 0.967
    # 平台: windows=True → platform_score = 1.0
    # d1 = 0.6 * 0.967 + 0.4 * 1.0 = 0.98
    d1_after_success = rt.vector[0]

    # 现在连续失败，d2 应该降
    for _ in range(5):
        rt.tick({'success': False, 'duration_ms': 200})
    d2_after_failure = rt.vector[1]

    # d1 不应受失败影响（仍由耗时+平台决定）
    d1_after_failure = rt.vector[0]

    assert d2_after_failure < d2_after_success, \
        f"d2 should drop: {d2_after_success} → {d2_after_failure}"
    # d1 不应有大幅变化（耗时相同，平台相同）
    d1_diff = abs(d1_after_failure - d1_after_success)
    assert d1_diff < 0.1, f"d1 should be stable: diff={d1_diff}"

    print(f"✅ 测试 4 通过: d1 稳定({d1_after_success:.3f}→{d1_after_failure:.3f}), d2 变化({d2_after_success:.3f}→{d2_after_failure:.3f})")


# ═══ 测试 5: 单平台 → score ≈ 0.33 ═══

def test_single_platform_score():
    p = PlatformReachability(windows=True, linux_ssh=False, android_adb=False)
    assert abs(p.score() - 1/3) < 0.01, f"Expected ~0.33, got {p.score()}"

    # 全平台 = 1.0
    p_full = PlatformReachability(windows=True, linux_ssh=True, android_adb=True)
    assert p_full.score() == 1.0, f"Expected 1.0, got {p_full.score()}"

    print("✅ 测试 5 通过: 单平台 → score≈0.33, 全平台=1.0")


# ═══ 测试 6: is_platform_available ═══

def test_is_platform_available():
    p = PlatformReachability(windows=True, linux_ssh=False, android_adb=True)
    assert p.is_platform_available("windows") is True
    assert p.is_platform_available("linux") is False
    assert p.is_platform_available("android") is True
    assert p.is_platform_available("any") is True
    assert p.is_platform_available("unknown") is True  # 未知平台默认可用
    print("✅ 测试 6 通过: is_platform_available 查询正确")


if __name__ == "__main__":
    test_all_false()
    test_android_disconnect_drops_d1()
    test_platform_filter_in_registry()
    test_d1_d2_orthogonal()
    test_single_platform_score()
    test_is_platform_available()
    print("\n🎉 Phase 4 全部 6 个验收测试通过！")
