# -*- coding: utf-8 -*-
"""
YI-Framework — 易经态势感知引擎

核心理念：卦象不是装饰，是Agent的操作系统。
- ExecutionProfile 由卦象结构自动推导，不手写64条
- YiRuntime 实时监测动爻，态势翻转立即切换策略
- gua_tool_effectiveness 让经验回流，第一次慢第二次快
"""

from .profiles import ExecutionProfile, derive_profile, TRIGRAM_ATTRIBUTES, generate_tool_hint
from .runtime import YiRuntime, StrategyChangeEvent
from .effectiveness import GuaToolEffectiveness
