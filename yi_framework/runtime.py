# -*- coding: utf-8 -*-
"""
YiRuntime — 易经实时态势感知引擎

核心功能：
- 情境向量实时更新（三维：资源/进展/完成度）
- 动爻检测（斜率+临界区间+迟滞）
- 态势翻转 → 自动切换 ExecutionProfile
- 不调LLM，纯数值计算
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Deque, Tuple

from .profiles import (
    ExecutionProfile, derive_profile, TRIGRAM_ATTRIBUTES,
    HEXAGRAM_NAMES, HEXAGRAM_REVERSE, generate_tool_hint
)
from .platform import PlatformReachability


@dataclass
class StrategyChangeEvent:
    """态势翻转事件 — 动爻触发时产生"""
    from_hexagram: str          # 原卦名
    to_hexagram: str            # 之卦名（变卦）
    hint: str                   # 工具索引提示（替代 from_profile / to_profile）
    changing_lines: List[int]   # 动爻位置 (0-5)
    reason: str                 # 翻转原因
    timestamp: float = field(default_factory=time.time)


class YiRuntime:
    """
    易经实时运行时 — Agent的态势感知核心
    
    使用方法：
        runtime = YiRuntime()
        
        # 每次工具执行后调用
        event = runtime.tick({
            'success': True/False,
            'resource_level': 0.8,  # 可选，系统资源水平
            'completion': 0.5,      # 可选，任务完成度
        })
        
        if event:
            # 态势翻转，使用工具索引提示
            hint = event.hint  # 注入 system message 给 LLM 参考
    """

    def __init__(self, window_size: int = 10, hysteresis: float = 0.05):
        """
        Args:
            window_size: 历史窗口大小（用于计算斜率）
            hysteresis: 迟滞区间宽度（防抖动）
        """
        self.window_size = window_size
        self.hysteresis = hysteresis

        # 三维情境向量：[资源, 进展, 完成度]
        self.vector: List[float] = [0.5, 0.5, 0.5]

        # 历史记录（用于斜率计算）
        self.history: Deque[List[float]] = deque(maxlen=window_size * 2)

        # 工具执行统计（用于进展计算）
        self._recent_results: Deque[bool] = deque(maxlen=window_size)

        # v2.0: 平台可达性（d1 维度的独立信号源）
        self._platform_reachability: PlatformReachability = PlatformReachability()

        # 当前卦象和Profile
        self.current_hexagram: str = "坤为地"  # 初始：纯阴，等待
        self.current_profile: ExecutionProfile = derive_profile(self.current_hexagram)

        # 上次翻转时间（防频繁切换）
        self._last_change_time: float = 0
        self._min_change_interval: float = 2.0  # 最少间隔2秒

        # v2.0: 防震荡 — 记录最近30次操作中的翻转时间戳
        self._change_count_30ops: Deque[float] = deque(maxlen=30)
        self._max_flips_30ops: int = 5  # 30次操作内最多5次翻转

    def tick(self, tool_result: dict, platform: 'PlatformReachability' = None) -> Optional[StrategyChangeEvent]:
        """
        每次工具执行后调用 — 更新向量、检测动爻、可能触发翻转

        Args:
            tool_result: 工具执行结果，支持字段：
                - success (bool): 是否成功
                - resource_level (float): 系统资源水平 0-1，可选
                - completion (float): 任务完成度 0-1，可选
                - duration_ms (int): 执行耗时，可选
            platform: 平台可达性状态，可选（更新 d1 维度）

        Returns:
            StrategyChangeEvent if 态势翻转, else None
        """
        # 更新平台可达性
        if platform is not None:
            self._platform_reachability = platform

        # 更新三维向量
        self._update_vector(tool_result)

        # 记录历史
        self.history.append(self.vector.copy())

        # 生成当前卦象
        new_hexagram = self._vector_to_hexagram()

        # v2.0: 快速通道 — 连续失败/成功时强制翻转（跳过斜率检测和时间间隔）
        force_flip = self._check_force_flip()
        if force_flip:
            changing_lines = force_flip
            force_mode = True
        else:
            # 检测动爻（斜率+临界区间+迟滞）
            changing_lines = self._detect_changing_lines()
            force_mode = False

        # 判断是否触发翻转（快速通道跳过时间间隔检查）
        if changing_lines and (force_mode or self._should_trigger_change()):
            # 生成之卦
            bian_hexagram = self._apply_changes(new_hexagram, changing_lines)

            if bian_hexagram and bian_hexagram != self.current_hexagram:
                old_hexagram = self.current_hexagram

                # 更新状态
                self.current_hexagram = bian_hexagram
                self.current_profile = derive_profile(bian_hexagram)
                self._last_change_time = time.time()
                self._change_count_30ops.append(time.time())  # 防震荡计数

                # v3.0: 生成工具索引提示（非硬约束）
                hint = generate_tool_hint(
                    hexagram_name=bian_hexagram,
                    changing_lines=changing_lines,
                )

                return StrategyChangeEvent(
                    from_hexagram=old_hexagram,
                    to_hexagram=bian_hexagram,
                    hint=hint,
                    changing_lines=changing_lines,
                    reason=self._format_change_reason(changing_lines, new_hexagram, bian_hexagram),
                )

        # 无翻转，但更新当前卦象（可能从初始状态变化）
        if new_hexagram != self.current_hexagram and not changing_lines:
            self.current_hexagram = new_hexagram
            self.current_profile = derive_profile(new_hexagram)

        return None

    def get_current_profile(self) -> ExecutionProfile:
        """获取当前执行参数"""
        return self.current_profile

    def get_explanation(self) -> str:
        """获取当前态势的解释文本"""
        return self.current_profile.explanation

    def get_vector(self) -> List[float]:
        """获取当前情境向量（调试用）"""
        return self.vector.copy()

    def reset(self):
        """重置到初始状态"""
        self.vector = [0.5, 0.5, 0.5]
        self.history.clear()
        self._recent_results.clear()
        self.current_hexagram = "坤为地"
        self.current_profile = derive_profile("坤为地")
        self._last_change_time = 0
        self._change_count_30ops.clear()
        self._platform_reachability = PlatformReachability()

    # ═══ 内部方法 ═══

    def _update_vector(self, result: dict):
        """更新三维情境向量（正交化：每个维度有独立信号源）

        d1_resource  ← 工具耗时 + 平台可达性（不与 d2 共享信号）
        d2_progress  ← 近期执行质量（滑动窗口成功率）
        d3_completion ← 任务完成度
        """
        # 维度0：资源水平 — 从工具耗时 + 平台可达性推导
        self._update_d1_resource(result)

        # 维度1：进展满意度（近期成功率的滑动平均）
        success = result.get('success', False)
        self._recent_results.append(success)
        if len(self._recent_results) >= 3:
            self.vector[1] = sum(self._recent_results) / len(self._recent_results)
        else:
            self.vector[1] = 0.5  # 样本不足时保持中性

        # 维度2：任务完成度
        if 'completion' in result:
            self.vector[2] = max(0.0, min(1.0, result['completion']))
        # 否则保持上次的值

    def _update_d1_resource(self, result: dict):
        """d1 只从系统和平台状态计算，不与 d2 共享信号

        - 有显式 resource_level → 直接使用
        - 否则：工具耗时越短 → 资源越充足，叠加平台可达性
        """
        if 'resource_level' in result:
            self.vector[0] = max(0.0, min(1.0, result['resource_level']))
        else:
            duration_ms = result.get('duration_ms', 1000)
            # 耗时 <500ms → 资源充足(1.0)，>5000ms → 资源紧张(0.2)
            time_score = max(0.2, 1.0 - (duration_ms / 6000.0))
            platform_score = self._platform_reachability.score()
            self.vector[0] = 0.6 * time_score + 0.4 * platform_score

    def _vector_to_hexagram(self) -> str:
        """三维向量 → 6位二进制 → 卦名"""
        # 每个维度 > 0.5 为阳，否则为阴
        # 三维扩展为六维：每个维度生成两爻
        # 初爻/二爻 = 资源, 三爻/四爻 = 进展, 五爻/上爻 = 完成度
        bits = []
        for val in self.vector:
            if val > 0.6:
                bits.extend([1, 1])  # 阳阳
            elif val > 0.4:
                bits.extend([1, 0])  # 阳阴（中性偏阳）
            elif val > 0.2:
                bits.extend([0, 1])  # 阴阳（中性偏阴）
            else:
                bits.extend([0, 0])  # 阴阴

        # 下卦（内卦）= 初三爻, 上卦（外卦）= 上三爻
        inner_bits = tuple('yang' if b else 'yin' for b in bits[0:3])
        outer_bits = tuple('yang' if b else 'yin' for b in bits[3:6])

        from .profiles import TRIGRAM_ATTRIBUTES
        # 查三爻卦名
        inner_name = self._bits_to_trigram(inner_bits)
        outer_name = self._bits_to_trigram(outer_bits)

        return HEXAGRAM_NAMES.get((inner_name, outer_name), '坤为地')

    def _bits_to_trigram(self, bits: Tuple[str, str, str]) -> str:
        """三爻二进制 → 卦名"""
        trigram_map = {
            ('yang', 'yang', 'yang'): '乾',
            ('yang', 'yang', 'yin'): '兑',
            ('yang', 'yin', 'yang'): '离',
            ('yang', 'yin', 'yin'): '震',
            ('yin', 'yang', 'yang'): '巽',
            ('yin', 'yang', 'yin'): '坎',
            ('yin', 'yin', 'yang'): '艮',
            ('yin', 'yin', 'yin'): '坤',
        }
        return trigram_map.get(bits, '坤')

    def _detect_changing_lines(self) -> List[int]:
        """
        检测动爻 — 临界翻转信号
        
        条件（满足其一即可）：
        1. 当前值在中线附近 且 有明确趋势
        2. 刚刚穿越中线（上一步在对面，这一步在这边）
        
        Returns:
            动爻位置列表 (0-5)，空列表表示无动爻
        """
        if len(self.history) < 3:
            return []

        changing = []
        slope_threshold = 0.03  # 降低斜率阈值，更容易触发
        wide_band = 0.15        # 扩大检测带

        for dim in range(3):
            val = self.vector[dim]
            slope = self._calc_slope(dim)

            triggered = False

            # 条件1：在中线附近（宽区间）且有趋势
            if (0.5 - wide_band < val < 0.5 + wide_band) and abs(slope) > slope_threshold:
                if slope < -slope_threshold:
                    triggered = True  # 正在向阴翻转
                elif slope > slope_threshold:
                    triggered = True  # 正在向阳翻转

            # 条件2：刚刚穿越中线（上一步在对面）
            if len(self.history) >= 2:
                prev_val = self.history[-2][dim]
                # 从阳穿越到阴，或从阴穿越到阳
                if (prev_val > 0.5 and val <= 0.5) or (prev_val < 0.5 and val >= 0.5):
                    triggered = True

            if triggered:
                changing.append(dim * 2)
                changing.append(dim * 2 + 1)

        return changing

    def _calc_slope(self, dim: int) -> float:
        """计算某维度的历史斜率（线性回归）"""
        values = [h[dim] for h in self.history]
        n = len(values)
        if n < 2:
            return 0.0

        # 简单线性回归: y = mx + b
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _should_trigger_change(self) -> bool:
        """防频繁切换：时间间隔 + 频率限制"""
        # 时间间隔检查
        if (time.time() - self._last_change_time) <= self._min_change_interval:
            return False
        # 频率限制：30次操作内翻转不超过5次
        if len(self._change_count_30ops) >= self._max_flips_30ops:
            return False
        return True

    def _check_force_flip(self) -> Optional[List[int]]:
        """快速通道：连续失败/成功时强制翻转（跳过斜率检测）

        连续 3 次失败 → 全爻动（翻转到保守模式）
        连续 5 次成功 → 全爻动（翻转到激进模式）
        """
        if len(self._recent_results) < 3:
            return None

        recent = list(self._recent_results)

        # 连续 3 次失败 → 全部爻动
        if len(recent) >= 3 and all(not r for r in recent[-3:]):
            return [0, 1, 2, 3, 4, 5]

        # 连续 5 次成功 → 全部爻动
        if len(recent) >= 5 and all(r for r in recent[-5:]):
            return [0, 1, 2, 3, 4, 5]

        return None

    def _apply_changes(self, current_hexagram: str, changing_lines: List[int]) -> str:
        """
        将动爻应用到当前卦象，生成之卦（变卦）
        
        Args:
            current_hexagram: 当前卦名
            changing_lines: 动爻位置列表
        
        Returns:
            之卦名
        """
        if current_hexagram not in HEXAGRAM_REVERSE:
            return current_hexagram

        inner_name, outer_name = HEXAGRAM_REVERSE[current_hexagram]
        inner = TRIGRAM_ATTRIBUTES[inner_name]
        outer = TRIGRAM_ATTRIBUTES[outer_name]

        # 将三爻卦转换为二进制列表
        inner_bits = self._trigram_to_bits(inner_name)
        outer_bits = self._trigram_to_bits(outer_name)
        all_bits = inner_bits + outer_bits

        # 翻转动爻
        for pos in changing_lines:
            if 0 <= pos < 6:
                all_bits[pos] = 1 - all_bits[pos]

        # 重新组合
        new_inner_bits = tuple('yang' if b else 'yin' for b in all_bits[0:3])
        new_outer_bits = tuple('yang' if b else 'yin' for b in all_bits[3:6])

        new_inner = self._bits_to_trigram(new_inner_bits)
        new_outer = self._bits_to_trigram(new_outer_bits)

        return HEXAGRAM_NAMES.get((new_inner, new_outer), current_hexagram)

    def _trigram_to_bits(self, name: str) -> List[int]:
        """三爻卦名 → 二进制列表"""
        bit_map = {
            '乾': [1, 1, 1], '兑': [1, 1, 0], '离': [1, 0, 1], '震': [1, 0, 0],
            '巽': [0, 1, 1], '坎': [0, 1, 0], '艮': [0, 0, 1], '坤': [0, 0, 0],
        }
        return bit_map.get(name, [0, 0, 0])

    def _format_change_reason(self, changing_lines: List[int], from_gua: str, to_gua: str) -> str:
        """生成翻转原因的可读文本"""
        line_names = ['初', '二', '三', '四', '五', '上']
        affected = [line_names[i] for i in changing_lines if 0 <= i < 6]
        return (
            f"动爻在{'、'.join(affected)}爻，"
            f"态势由「{from_gua}」翻转为「{to_gua}」。"
            f"执行策略已自动切换。"
        )
