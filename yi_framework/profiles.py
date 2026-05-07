# -*- coding: utf-8 -*-
"""
卦象 → 执行参数 硬映射

核心设计：
- 8个三爻卦各维护一组基础属性（能量、风险、行动倾向）
- 64个六爻卦的 ExecutionProfile 由上下卦属性自动组合计算
- 不经过LLM，纯确定性数学

八卦属性来源：《说卦传》核心描述 → 工程化数值映射
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Optional


@dataclass
class ExecutionProfile:
    """卦象决定的执行参数 — 直接控制执行引擎行为"""
    max_retries: int = 1          # 最大重试次数 (0-3)
    parallel: bool = False        # 是否并行执行
    risk_tolerance: float = 0.5   # 风险容忍度 (0.0-1.0)
    ask_human: bool = False       # 是否请求人工确认
    timeout_seconds: int = 30     # 单步超时（秒）
    rollback: str = "none"        # 回滚策略: "none" / "step_back" / "full"
    explanation: str = ""         # 卦象解释文本

    def merge(self, overrides: dict) -> 'ExecutionProfile':
        """合并外部覆盖参数（用于动爻切换时的部分更新）"""
        import dataclasses
        d = dataclasses.asdict(self)
        d.update(overrides)
        return ExecutionProfile(**d)


# ═══════════════════════════════════════════════════════════
# 八卦基础属性（三爻卦）
# 每个属性 0.0~1.0，由卦象的工程语义决定
# ═══════════════════════════════════════════════════════════

@dataclass
class TrigramAttributes:
    """三爻卦的工程属性"""
    energy: float       # 能量/主动性 (0=纯被动, 1=纯主动)
    risk: float         # 风险等级 (0=安全, 1=危险)
    action: float       # 行动倾向 (0=静止等待, 1=全力执行)
    stability: float    # 稳定性 (0=剧变, 1=恒定)
    # 以下用于生成解释文本
    name_zh: str        # 中文名
    symbol: str         # 卦象符号
    essence: str        # 本质描述


# 8个三爻卦的基础属性
# 来源：《说卦传》"乾健坤顺，震动巽入，坎陷离丽，艮止兑说"
TRIGRAM_ATTRIBUTES: Dict[str, TrigramAttributes] = {
    '乾': TrigramAttributes(
        energy=1.0, risk=0.2, action=1.0, stability=0.8,
        name_zh='乾', symbol='☰', essence='刚健主动，纯阳之势'
    ),
    '坤': TrigramAttributes(
        energy=0.0, risk=0.1, action=0.0, stability=1.0,
        name_zh='坤', symbol='☷', essence='柔顺承载，纯阴之态'
    ),
    '震': TrigramAttributes(
        energy=0.8, risk=0.4, action=0.9, stability=0.3,
        name_zh='震', symbol='☳', essence='震动奋起，雷发行动'
    ),
    '巽': TrigramAttributes(
        energy=0.4, risk=0.3, action=0.5, stability=0.6,
        name_zh='巽', symbol='☴', essence='渗透入散，柔而渐进'
    ),
    '坎': TrigramAttributes(
        energy=0.3, risk=0.9, action=0.3, stability=0.2,
        name_zh='坎', symbol='☵', essence='陷危险难，需谨慎前行'
    ),
    '离': TrigramAttributes(
        energy=0.6, risk=0.3, action=0.6, stability=0.7,
        name_zh='离', symbol='☲', essence='附丽明亮，依附而行'
    ),
    '艮': TrigramAttributes(
        energy=0.1, risk=0.1, action=0.0, stability=1.0,
        name_zh='艮', symbol='☶', essence='静止阻止，止而不动'
    ),
    '兑': TrigramAttributes(
        energy=0.5, risk=0.2, action=0.4, stability=0.5,
        name_zh='兑', symbol='☱', essence='愉悦开口，柔和表达'
    ),
}

# 64卦名映射：(内卦, 外卦) → 卦名
HEXAGRAM_NAMES: Dict[Tuple[str, str], str] = {
    ('乾', '乾'): '乾为天', ('乾', '兑'): '天泽履', ('乾', '离'): '天火同人',
    ('乾', '震'): '天雷无妄', ('乾', '巽'): '天风姤', ('乾', '坎'): '天水讼',
    ('乾', '艮'): '天山遁', ('乾', '坤'): '天地否',
    ('兑', '乾'): '泽天夬', ('兑', '兑'): '兑为泽', ('兑', '离'): '泽火革',
    ('兑', '震'): '泽雷随', ('兑', '巽'): '泽风大过', ('兑', '坎'): '泽水困',
    ('兑', '艮'): '泽山咸', ('兑', '坤'): '泽地萃',
    ('离', '乾'): '火天大有', ('离', '兑'): '火泽睽', ('离', '离'): '离为火',
    ('离', '震'): '火雷噬嗑', ('离', '巽'): '火风鼎', ('离', '坎'): '火水未济',
    ('离', '艮'): '火山旅', ('离', '坤'): '火地晋',
    ('震', '乾'): '雷天大壮', ('震', '兑'): '雷泽归妹', ('震', '离'): '雷火丰',
    ('震', '震'): '震为雷', ('震', '巽'): '雷风恒', ('震', '坎'): '雷水解',
    ('震', '艮'): '雷山小过', ('震', '坤'): '雷地豫',
    ('巽', '乾'): '风天小畜', ('巽', '兑'): '风泽中孚', ('巽', '离'): '风火家人',
    ('巽', '震'): '风雷益', ('巽', '巽'): '巽为风', ('巽', '坎'): '风水涣',
    ('巽', '艮'): '风山渐', ('巽', '坤'): '风地观',
    ('坎', '乾'): '水天需', ('坎', '兑'): '水泽节', ('坎', '离'): '水火既济',
    ('坎', '震'): '水雷屯', ('坎', '巽'): '水风井', ('坎', '坎'): '坎为水',
    ('坎', '艮'): '水山蹇', ('坎', '坤'): '水地比',
    ('艮', '乾'): '山天大畜', ('艮', '兑'): '山泽损', ('艮', '离'): '山火贲',
    ('艮', '震'): '山雷颐', ('艮', '巽'): '山风蛊', ('艮', '坎'): '山水蒙',
    ('艮', '艮'): '艮为山', ('艮', '坤'): '山地剥',
    ('坤', '乾'): '地天泰', ('坤', '兑'): '地泽临', ('坤', '离'): '地火明夷',
    ('坤', '震'): '地雷复', ('坤', '巽'): '地风升', ('坤', '坎'): '地水师',
    ('坤', '艮'): '地山谦', ('坤', '坤'): '坤为地',
}

# 反向映射：卦名 → (内卦, 外卦)
HEXAGRAM_REVERSE: Dict[str, Tuple[str, str]] = {
    v: k for k, v in HEXAGRAM_NAMES.items()
}


def derive_profile(hexagram_name: str) -> ExecutionProfile:
    """
    从卦象结构自动推导执行参数。
    
    推导规则（全部确定性，不调LLM）：
    - 内卦 → 内部状态（资源、能量）
    - 外卦 → 外部环境（风险、阻碍）
    - 上下卦属性组合 → 行为参数
    
    Args:
        hexagram_name: 64卦名，如"乾为天"、"坎为水"
    
    Returns:
        ExecutionProfile: 直接可注入执行引擎的参数
    """
    if hexagram_name not in HEXAGRAM_REVERSE:
        # 未知卦名，返回安全默认值
        return ExecutionProfile(
            max_retries=1, parallel=False, risk_tolerance=0.3,
            ask_human=True, timeout_seconds=20, rollback="step_back",
            explanation=f"未知卦象「{hexagram_name}」，采用谨慎策略"
        )

    inner_name, outer_name = HEXAGRAM_REVERSE[hexagram_name]
    inner = TRIGRAM_ATTRIBUTES[inner_name]
    outer = TRIGRAM_ATTRIBUTES[outer_name]

    # ═══ 推导规则 ═══

    # 重试次数：外卦风险越高，重试越多
    # 坎(0.9)→3次, 震(0.4)→1次, 乾(0.2)→0次, 坤(0.1)→0次
    if outer.risk >= 0.7:
        max_retries = 3
    elif outer.risk >= 0.4:
        max_retries = 1
    else:
        max_retries = 0

    # 并行：内卦能量高 且 外卦稳定时并行
    # 乾(1.0×0.8=0.8)→True, 坤(0.0×1.0=0.0)→False
    parallel = (inner.energy * outer.stability) > 0.6

    # 风险容忍：内卦能量高时容忍高风险，内卦被动时容忍低风险
    # 乾(能量1.0)→高容忍, 坤(能量0.0)→低容忍, 坎(能量0.3)→低容忍
    risk_tolerance = round(inner.energy * 0.7 + (1.0 - outer.risk) * 0.3, 2)

    # 求助人类：内卦能量低（被动/无力）时求助
    # 坤(0.0)→求助, 艮(0.1)→求助, 乾(1.0)→不求助
    ask_human = inner.energy < 0.2

    # 超时：内卦能量越高，给越多时间（高能量=复杂操作需要更多时间）
    timeout_seconds = int(15 + 45 * inner.energy)

    # 回滚策略：
    # - 内外卦都低能量 → full（完全回滚）
    # - 外卦高风险 → step_back（逐步回滚）
    # - 其他 → none
    if inner.energy < 0.2 and outer.energy < 0.2:
        rollback = "full"
    elif outer.risk > 0.6:
        rollback = "step_back"
    else:
        rollback = "none"

    # 解释文本
    explanation = (
        f"{inner.name_zh}（{inner.essence}）下，"
        f"{outer.name_zh}（{outer.essence}）上。"
        f"建议：{'并行执行' if parallel else '顺序执行'}，"
        f"{'请求人工确认' if ask_human else '自主执行'}，"
        f"风险容忍{'高' if risk_tolerance > 0.6 else '中' if risk_tolerance > 0.3 else '低'}。"
    )

    return ExecutionProfile(
        max_retries=max_retries,
        parallel=parallel,
        risk_tolerance=risk_tolerance,
        ask_human=ask_human,
        timeout_seconds=timeout_seconds,
        rollback=rollback,
        explanation=explanation,
    )


def get_all_profiles() -> Dict[str, ExecutionProfile]:
    """生成全部64卦的ExecutionProfile，用于调试和测试"""
    return {name: derive_profile(name) for name in HEXAGRAM_REVERSE.keys()}


def format_profile(hexagram_name: str, profile: ExecutionProfile) -> str:
    """格式化输出卦象和执行参数，用于日志"""
    return (
        f"☯️ {hexagram_name}\n"
        f"  重试: {profile.max_retries} | 并行: {'是' if profile.parallel else '否'} | "
        f"风险容忍: {profile.risk_tolerance}\n"
        f"  求助: {'是' if profile.ask_human else '否'} | 超时: {profile.timeout_seconds}s | "
        f"回滚: {profile.rollback}\n"
        f"  {profile.explanation}"
    )


def is_crisis(profile: ExecutionProfile) -> bool:
    """判断当前 Profile 是否处于危机状态

    危机条件：风险容忍极低 且 需要完全回滚
    替代 dayan.py 的 action_hint 危机检测（full_stop / humble_rollback / rollback_request）
    """
    return profile.risk_tolerance < 0.15 and profile.rollback == "full"


# ═══════════════════════════════════════════════════════════
# v3.0: 卦象工具索引（参谋模式，非司令模式）
# 卦象生成参考提示，LLM 自主决定是否采纳
# ═══════════════════════════════════════════════════════════

def generate_tool_hint(hexagram_name: str,
                       changing_lines: list,
                       effectiveness=None,
                       all_tool_names: list = None) -> str:
    """
    卦象作为工具索引，生成参考提示（不是硬约束）。
    LLM 可自主决定是否采纳。

    Args:
        hexagram_name: 当前卦名
        changing_lines: 动爻位置列表 (0-5)
        effectiveness: GuaToolEffectiveness 实例，可选
        all_tool_names: 当前可用工具名列表，可选

    Returns:
        提示文本，注入 system message
    """
    # 1. 经典建议：从上下卦属性推导态势描述
    advice = hexagram_name
    if hexagram_name in HEXAGRAM_REVERSE:
        inner_name, outer_name = HEXAGRAM_REVERSE[hexagram_name]
        inner_attr = TRIGRAM_ATTRIBUTES.get(inner_name)
        outer_attr = TRIGRAM_ATTRIBUTES.get(outer_name)
        if inner_attr and outer_attr:
            advice = f"内卦{inner_name}（{inner_attr.essence}），外卦{outer_name}（{outer_attr.essence}）"

    # 2. 历史最佳工具（从 effectiveness DB 查）
    top_tools_str = "无历史数据"
    if effectiveness and all_tool_names:
        try:
            scores = effectiveness.query_best_tools(hexagram_name, all_tool_names, limit=3)
            if scores:
                top_tools_str = ", ".join(
                    f"{s.tool_name}({s.success_rate:.0%}成功率, {s.total_uses}次)" for s in scores
                )
        except Exception:
            pass

    # 3. 动爻描述
    if changing_lines:
        line_names = ['初', '二', '三', '四', '五', '上']
        lines_str = "、".join(line_names[i] for i in changing_lines if i < 6) + "爻动"
    else:
        lines_str = "无动爻"

    return (
        f"[卦象索引] {hexagram_name}，{lines_str}\n"
        f"态势：{advice}\n"
        f"历史高效工具：{top_tools_str}\n"
        f"（以上仅供参考，你可以结合具体任务自主选择工具和策略）"
    )
