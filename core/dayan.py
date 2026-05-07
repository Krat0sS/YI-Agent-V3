# -*- coding: utf-8 -*-
"""
大衍筮法引擎 — Agent 决策的数学底座

《周易·系辞上》：
"大衍之数五十，其用四十有九。分而为二以象两，挂一以象三，
 揲之以四，以象四时，归奇于扐以象闰。五岁再闰，故再扐而后挂。
 ……是故四营而成易，十有八变而成卦。"

映射到 Agent：
- 大衍之数五十 = 49 可用工具 + 1 太极常量（send 核心循环）
- 分而为二 = 将工具按相关性分为两组
- 挂一以象三 = 从相关组选出主工具
- 揲之以四 = 四维评估（能力/成本/风险/历史）
- 归奇于扐 = 余数累积为不确定性
- 四营而成易 = 四步完成一爻判定
- 十有八变而成卦 = 6 爻 × 3 变 = 18 变得完整卦象
"""
import json
import time
import random
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from data import execution_log as log


# ═══════════════════════════════════════════════════════════
# 八卦映射表
# ═══════════════════════════════════════════════════════════

# 八卦：三爻组合 → 卦名
TRIGRAMS = {
    ('yang', 'yang', 'yang'): '乾',  # ☰
    ('yang', 'yang', 'yin'):  '兑',  # ☱
    ('yang', 'yin',  'yang'): '离',  # ☲
    ('yang', 'yin',  'yin'):  '震',  # ☳
    ('yin',  'yang', 'yang'): '巽',  # ☴
    ('yin',  'yang', 'yin'):  '坎',  # ☵
    ('yin',  'yin',  'yang'): '艮',  # ☶
    ('yin',  'yin',  'yin'):  '坤',  # ☷
}

# 六十四卦：(内卦, 外卦) → (卦名, 行动建议)
HEXAGRAMS = {
    ('乾', '乾'): ('乾为天',    'full_execute'),       # 纯阳，全速推进
    ('乾', '兑'): ('天泽履',    'execute_with_care'),   # 阳刚在外，小心行事
    ('乾', '离'): ('天火同人',  'execute_with_watch'),   # 阳明并行，执行+观察
    ('乾', '震'): ('天雷无妄',  'execute_with_caution'), # 阳刚遇动，谨慎执行
    ('乾', '巽'): ('天风姤',    'execute_with_watch'),   # 阳遇柔风，顺势执行
    ('乾', '坎'): ('天水讼',    'pause_and_resolve'),    # 阳刚遇险，先解决冲突
    ('乾', '艮'): ('天山遁',    'execute_partial'),      # 阳遇止，部分执行
    ('乾', '坤'): ('天地否',    'pause_ask'),            # 阴阳对立，暂停沟通
    ('兑', '乾'): ('泽天夬',    'execute_decisive'),     # 泽上天，果断执行
    ('兑', '兑'): ('兑为泽',    'execute_gently'),       # 纯兑，温和执行
    ('兑', '离'): ('泽火革',    'execute_with_change'),  # 泽火相遇，带变革执行
    ('兑', '震'): ('泽雷随',    'execute_follow'),       # 随顺执行
    ('兑', '巽'): ('泽风大过',  'execute_heavy'),        # 负担过重，简化执行
    ('兑', '坎'): ('泽水困',    'stop_analyze'),         # 困境，停下来分析
    ('兑', '艮'): ('泽山咸',    'execute_resonate'),     # 感应执行
    ('兑', '坤'): ('泽地萃',    'gather_then_execute'),  # 聚集资源再执行
    ('离', '乾'): ('火天大有',  'full_execute'),         # 光明在天，大力执行
    ('离', '兑'): ('火泽睽',    'execute_divided'),      # 分歧执行，需协调
    ('离', '离'): ('离为火',    'execute_bright'),       # 纯明，清晰执行
    ('离', '震'): ('火雷噬嗑',  'execute_breakthrough'), # 噬嗑，突破执行
    ('离', '巽'): ('火风鼎',    'execute_transform'),    # 鼎新，转型执行
    ('离', '坎'): ('火水未济',  'step_by_step'),         # 未完成，分步走
    ('离', '艮'): ('火山旅',    'execute_travel'),       # 旅，移动式执行
    ('离', '坤'): ('火地晋',    'execute_advance'),      # 晋升，稳步推进
    ('震', '乾'): ('雷天大壮',  'execute_powerful'),     # 大壮，强力执行
    ('震', '兑'): ('雷泽归妹',  'execute_return'),       # 归妹，回归执行
    ('震', '离'): ('雷火丰',    'execute_abundant'),     # 丰盛，充裕执行
    ('震', '震'): ('震为雷',    'execute_shock'),        # 纯震，冲击式执行
    ('震', '巽'): ('雷风恒',    'execute_persistent'),   # 恒久，持续执行
    ('震', '坎'): ('雷水解',    'execute_resolve'),      # 解，解决问题后执行
    ('震', '艮'): ('雷山小过',  'execute_minor'),        # 小过，小幅执行
    ('震', '坤'): ('雷地豫',    'execute_prepare'),      # 豫，预备后执行
    ('巽', '乾'): ('风天小畜',  'execute_normal'),       # 小畜，正常执行
    ('巽', '兑'): ('风泽中孚',  'execute_trust'),        # 中孚，信任执行
    ('巽', '离'): ('风火家人',  'execute_family'),       # 家人，协调执行
    ('巽', '震'): ('风雷益',    'execute_benefit'),      # 益，增益执行
    ('巽', '巽'): ('巽为风',    'execute_cautious'),     # 纯巽，谨慎执行
    ('巽', '坎'): ('风水涣',    'execute_disperse'),     # 涣散，分散执行
    ('巽', '艮'): ('风山渐',    'step_by_step'),         # 渐进，分步执行
    ('巽', '坤'): ('风地观',    'observe_first'),        # 观察先行
    ('坎', '乾'): ('水天需',    'wait_then_execute'),    # 需，等待后执行
    ('坎', '兑'): ('水泽节',    'execute_limited'),      # 节制，有限执行
    ('坎', '离'): ('水火既济',  'execute_complete'),     # 既济，完整执行
    ('坎', '震'): ('水雷屯',    'execute_sprout'),       # 屯，萌芽式执行
    ('坎', '巽'): ('水风井',    'execute_deep'),         # 井，深层执行
    ('坎', '坎'): ('坎为水',    'execute_with_risk'),    # 纯坎，高风险执行
    ('坎', '艮'): ('水山蹇',    'stop_difficulty'),      # 蹇，困难重重
    ('坎', '坤'): ('水地比',    'execute_together'),     # 比，协作执行
    ('艮', '乾'): ('山天大畜',  'retry_then_execute'),   # 大畜，积蓄后执行
    ('艮', '兑'): ('山泽损',    'execute_reduce'),       # 损，精简执行
    ('艮', '离'): ('山火贲',    'execute_decorate'),     # 贲，修饰后执行
    ('艮', '震'): ('山雷颐',    'execute_nourish'),      # 颐，滋养式执行
    ('艮', '巽'): ('山风蛊',    'fix_then_continue'),    # 蛊，先修复再继续
    ('艮', '坎'): ('山水蒙',    'execute_learn'),        # 蒙，学习式执行
    ('艮', '艮'): ('艮为山',    'stop_analyze'),         # 纯艮，完全停止
    ('艮', '坤'): ('山地剥',    'rollback_request'),     # 剥，回滚请求
    ('坤', '乾'): ('地天泰',    'recover_easy'),         # 泰，轻松恢复
    ('坤', '兑'): ('地泽临',    'execute_approach'),     # 临，接近执行
    ('坤', '离'): ('地火明夷',  'execute_hidden'),       # 明夷，隐藏执行
    ('坤', '震'): ('地雷复',    'recover_step'),         # 复，逐步恢复
    ('坤', '巽'): ('地风升',    'recover_rise'),         # 升，上升恢复
    ('坤', '坎'): ('地水师',    'execute_command'),      # 师，指令式执行
    ('坤', '艮'): ('地山谦',    'humble_rollback'),      # 谦，谦逊回滚
    ('坤', '坤'): ('坤为地',    'full_stop'),            # 纯坤，完全停止
}


# ═══════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════

@dataclass
class YaoResult:
    """一爻的判定结果"""
    position: int              # 爻位 (1-6)
    yan_type: str              # 'old_yang' | 'young_yang' | 'young_yin' | 'old_yin'
    remainder: int             # 最终余数 (0-3)
    changes: List[int]         # 三次变的余数 [r1, r2, r3]
    confidence: float          # 置信度 (0-1)
    reasoning: str             # 判定依据
    tool_name: Optional[str]   # 关联的工具名（如果是工具选择爻）

    @property
    def polarity(self) -> str:
        """返回 'yang' 或 'yin'"""
        return 'yang' if self.yan_type in ('old_yang', 'young_yang') else 'yin'


@dataclass
class GuaResult:
    """完整卦象结果（六爻）"""
    hexagram_name: str         # 卦名
    inner_trigram: str         # 内卦名
    outer_trigram: str         # 外卦名
    action_hint: str           # 行动建议
    lines: List[YaoResult]     # 六爻
    total_changes: int = 18    # 总变数
    tool_sequence: List[str] = field(default_factory=list)  # 推荐工具序列
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return {
            'hexagram_name': self.hexagram_name,
            'inner_trigram': self.inner_trigram,
            'outer_trigram': self.outer_trigram,
            'action_hint': self.action_hint,
            'lines': [
                {
                    'position': l.position,
                    'yan_type': l.yan_type,
                    'remainder': l.remainder,
                    'changes': l.changes,
                    'confidence': round(l.confidence, 3),
                    'tool_name': l.tool_name,
                }
                for l in self.lines
            ],
            'tool_sequence': self.tool_sequence,
            'elapsed_ms': self.elapsed_ms,
        }

    def summary(self) -> str:
        """给用户看的简短摘要"""
        yao_symbols = {
            'old_yang': '⚌', 'young_yang': '⚎',
            'young_yin': '⚍', 'old_yin': '⚏'
        }
        symbols = ' '.join(yao_symbols.get(l.yan_type, '?') for l in reversed(self.lines))
        return f"☯️ {self.hexagram_name} {symbols} → {self.action_hint}"


@dataclass
class SeparationResult:
    """分二的结果"""
    relevant: List[str]        # 相关工具列表
    irrelevant: List[str]      # 不相关工具列表
    relevance_scores: Dict[str, float]  # 每个工具的相关性分数


@dataclass
class SiYingResult:
    """四营（四维评估）的结果"""
    capability: float          # 能力匹配度 (0-1)
    cost: float               # 成本效率 (0-1)
    risk: float               # 风险评估 (0-1, 越低越好)
    history: float            # 历史成功率 (0-1)
    total_score: float        # 综合得分
    remainder: int            # 余数 (0-3)
    details: str              # 评估详情


# ═══════════════════════════════════════════════════════════
# 六爻维度定义
# ═══════════════════════════════════════════════════════════

# 六爻对应 Agent 决策链的六个维度
LINE_DIMENSIONS = {
    1: {
        'name': '反馈层',
        'description': '执行结果是否满足预期',
        'evaluate': '_eval_feedback',       # 评估函数名
    },
    2: {
        'name': '执行层',
        'description': '执行过程中是否需要干预',
        'evaluate': '_eval_execution',
    },
    3: {
        'name': '参数层',
        'description': '工具的参数怎么调',
        'evaluate': '_eval_params',
    },
    4: {
        'name': '选择层',
        'description': '具体用哪个工具',
        'evaluate': '_eval_selection',
    },
    5: {
        'name': '编排层',
        'description': '多个工具/技能的执行顺序',
        'evaluate': '_eval_orchestration',
    },
    6: {
        'name': '战略层',
        'description': '这个任务值不值得做',
        'evaluate': '_eval_strategy',
    },
}


# ═══════════════════════════════════════════════════════════
# 第一营：分而为二
# ═══════════════════════════════════════════════════════════

def separate_tools(user_input: str, tool_names: List[str],
                   tool_descriptions: Dict[str, str] = None) -> SeparationResult:
    """
    分而为二以象两。

    将 49 个工具按与当前任务的相关性分为两组。
    使用语义映射 + n-gram 双重匹配。

    Args:
        user_input: 用户输入
        tool_names: 可用工具名列表
        tool_descriptions: 工具描述字典 {name: description}

    Returns:
        SeparationResult 对象
    """
    text = user_input.strip().lower()
    relevance_scores = {}

    # 语义映射：与 _calc_capability 共享同一套
    semantic_map = {
        'organize': (['整理', '收拾', '归类', '分类', '清理'], 0.30),
        'scan': (['扫描', '查看', '看看', '列出'], 0.15),
        'find': (['查找', '找', '搜索'], 0.20),
        'search': (['搜索', '搜', '查', '查找', '找'], 0.30),
        'browser': (['浏览器', '网页', '网站', 'github', 'http', '打开网页'], 0.30),
        'desktop': (['桌面', '屏幕', '鼠标'], 0.15),
        'screenshot': (['截图', '截屏'], 0.25),
        'run_command': (['执行', '运行', '命令', 'cmd', '删除', '删'], 0.15),
        'read': (['读', '看', '查看', '打开文件'], 0.15),
        'write': (['写', '创建', '保存'], 0.15),
        'edit': (['编辑', '修改', '改'], 0.15),
        'move': (['移动', '搬', '转移'], 0.15),
        'remember': (['记住', '记忆', '记下'], 0.20),
        'recall': (['回忆', '想起', '之前'], 0.20),
        'check': (['检查', '状态', '看看'], 0.15),
    }

    action_pairs = {
        '整理': 'organize', '扫描': 'scan', '搜索': 'search',
        '查找': 'find', '打开': 'browser', '截图': 'screenshot',
        '执行': 'run', '记住': 'remember', '查看': 'read',
        '修改': 'edit', '移动': 'move', '检查': 'check',
        '删除': 'run_command', '删': 'run_command',
    }

    def ngrams(s, n):
        return [s[i:i+n] for i in range(len(s)-n+1)]

    def fuzzy_match(keyword: str, text: str) -> bool:
        """中文模糊匹配：关键词的字符按顺序出现在文本中，允许间隔"""
        if keyword in text:
            return True
        idx = 0
        for ch in text:
            if idx < len(keyword) and ch == keyword[idx]:
                idx += 1
        return idx == len(keyword)

    user_tokens = set(ngrams(text, 2)) | set(ngrams(text, 3)) | set(ngrams(text, 4))
    user_tokens |= set(text)

    for name in tool_names:
        name_lower = name.lower()
        score = 0.0

        # 1. 语义映射匹配（主要）- 检查所有匹配类别，取最高分
        best_semantic = 0.0
        matched_cats = 0
        for category, (keywords, weight) in semantic_map.items():
            if category in name_lower:
                matched = sum(1 for kw in keywords if fuzzy_match(kw, text))
                if matched > 0:
                    s = min(weight, matched * (weight / 1.5))
                    matched_cats += 1
                    best_semantic = max(best_semantic, s)
        score += best_semantic
        # 多类别匹配加分
        if matched_cats >= 2:
            score += 0.10 * (matched_cats - 1)

        # 2. 动作动词匹配（高权重）
        for cn_action, en_tool in action_pairs.items():
            if fuzzy_match(cn_action, text) and en_tool in name_lower:
                score += 0.25
                break

        # 3. n-gram 匹配（补充）
        tool_text = (name_lower + " " + (tool_descriptions or {}).get(name, "").lower())
        tool_tokens = set(ngrams(tool_text, 2)) | set(ngrams(tool_text, 3)) | set(tool_text)
        if tool_tokens:
            intersection = user_tokens & tool_tokens
            ngram_score = len(intersection) / max(len(user_tokens), 1)
            score += ngram_score * 0.3  # n-gram 权重较低

        relevance_scores[name] = min(1.0, score)

    # 分二：相关（>阈值）vs 不相关
    threshold = 0.05
    relevant = [n for n in tool_names if relevance_scores.get(n, 0) > threshold]
    irrelevant = [n for n in tool_names if relevance_scores.get(n, 0) <= threshold]

    # 如果相关组太少（<2），降低阈值
    if len(relevant) < 2:
        threshold = 0.02
        relevant = [n for n in tool_names if relevance_scores.get(n, 0) > threshold]
        irrelevant = [n for n in tool_names if relevance_scores.get(n, 0) <= threshold]

    return SeparationResult(
        relevant=relevant,
        irrelevant=irrelevant,
        relevance_scores=relevance_scores,
    )


# ═══════════════════════════════════════════════════════════
# 第二营：挂一以象三
# ═══════════════════════════════════════════════════════════

def hang_one(separation: SeparationResult,
             user_input: str) -> Tuple[str, float]:
    """
    挂一以象三。

    从相关组中选出一个"主工具"——匹配度最高的那个。
    "三"指天、地、人三才：工具是"地"（承载），用户意图是"天"（方向），
    Agent 是"人"（执行者）。

    Returns:
        (主工具名, 匹配分数)
    """
    if not separation.relevant:
        return None, 0.0

    # 按相关性分数排序，取最高
    scored = [(name, separation.relevance_scores.get(name, 0))
              for name in separation.relevant]
    scored.sort(key=lambda x: x[1], reverse=True)

    best_name, best_score = scored[0]
    return best_name, best_score


# ═══════════════════════════════════════════════════════════
# 第三营：揲之以四
# ═══════════════════════════════════════════════════════════

def si_ying_evaluate(tool_name: str, user_input: str,
                     recent_calls: List[dict] = None) -> SiYingResult:
    """
    揲之以四，以象四时。

    对候选工具做四维评估：
    1. 能力匹配度 — 这个工具能完成任务吗？
    2. 成本效率 — 调用成本如何？
    3. 风险评估 — 失败概率多大？
    4. 历史成功率 — 过去用得怎么样？

    每维得分 0-1，综合后取余数。

    Returns:
        SiYingResult 对象
    """
    # 1. 能力匹配度：基于工具名和用户输入的匹配
    capability = _calc_capability(tool_name, user_input)

    # 2. 成本效率：基于工具类型估算
    cost = _calc_cost_efficiency(tool_name)

    # 3. 风险评估：基于工具的历史失败率
    risk = _calc_risk(tool_name, recent_calls)

    # 4. 历史成功率
    history = _calc_history_success(tool_name, recent_calls)

    # 综合得分（加权平均）
    total_score = (
        capability * 0.35 +
        cost * 0.15 +
        (1 - risk) * 0.25 +  # 风险越低越好
        history * 0.25
    )

    # 余数：将得分映射到 0-3
    # 0 = 极好, 1 = 好, 2 = 一般, 3 = 差
    remainder = 3 - int(total_score * 4)
    remainder = max(0, min(3, remainder))

    return SiYingResult(
        capability=round(capability, 3),
        cost=round(cost, 3),
        risk=round(risk, 3),
        history=round(history, 3),
        total_score=round(total_score, 3),
        remainder=remainder,
        details=f"能力={capability:.2f} 成本={cost:.2f} 风险={risk:.2f} 历史={history:.2f}"
    )


def _calc_capability(tool_name: str, user_input: str) -> float:
    """计算工具能力匹配度"""

    def fuzzy_match(keyword: str, text: str) -> bool:
        """中文模糊匹配：关键词的字符按顺序出现在文本中，允许间隔"""
        if keyword in text:
            return True
        # 字符级模糊：关键词的每个字符按顺序出现在文本中
        idx = 0
        for ch in text:
            if idx < len(keyword) and ch == keyword[idx]:
                idx += 1
        return idx == len(keyword)

    text = user_input.lower()
    name = tool_name.lower()

    # 基础分
    base = 0.3

    # 中文语义映射：工具类别 → (关键词, 权重)
    # 关键词支持模糊匹配（字符间可有其他字符）
    semantic_map = {
        'organize': (['整理', '收拾', '归类', '分类', '清理'], 0.30),
        'scan': (['扫描', '查看', '看看', '列出'], 0.15),
        'find': (['查找', '找', '搜索'], 0.20),
        'search': (['搜索', '搜', '查', '查找', '找'], 0.30),
        'browser': (['浏览器', '网页', '网站', 'github', 'http', '打开网页'], 0.30),
        'desktop': (['桌面', '屏幕', '鼠标'], 0.15),
        'screenshot': (['截图', '截屏', '截屏', '截个图', '截个屏'], 0.25),
        'run_command': (['执行', '运行', '命令', 'cmd', '删除', '删'], 0.15),
        'read': (['读', '看', '查看', '打开文件'], 0.15),
        'write': (['写', '创建', '保存'], 0.15),
        'edit': (['编辑', '修改', '改'], 0.15),
        'move': (['移动', '搬', '转移'], 0.15),
        'remember': (['记住', '记忆', '记下'], 0.20),
        'recall': (['回忆', '想起', '之前'], 0.20),
        'check': (['检查', '状态', '看看'], 0.15),
    }

    best_semantic_score = 0.0
    best_category = None
    matched_categories = 0
    for category, (keywords, weight) in semantic_map.items():
        if category in name:
            matched = sum(1 for kw in keywords if fuzzy_match(kw, text))
            if matched > 0:
                score = min(weight, matched * (weight / 1.5))
                matched_categories += 1
                if score > best_semantic_score:
                    best_semantic_score = score
                    best_category = category
    base += best_semantic_score

    # 多类别匹配加分：同时命中多个语义类别的工具更精准
    if matched_categories >= 2:
        base += 0.10 * (matched_categories - 1)

    # 动作动词匹配：额外加分（比语义匹配权重更高，因为是用户明确意图）
    action_pairs = {
        '整理': 'organize', '扫描': 'scan', '搜索': 'search',
        '查找': 'find', '打开': 'browser', '截图': 'screenshot',
        '执行': 'run', '记住': 'remember', '查看': 'read',
        '修改': 'edit', '移动': 'move', '检查': 'check',
        '删除': 'run_command', '删': 'run_command',
    }
    action_matched = False
    for cn_action, en_tool in action_pairs.items():
        if fuzzy_match(cn_action, text) and en_tool in name:
            base += 0.25
            action_matched = True
            break

    # 如果是万能工具 run_command，给一个保底分
    if 'run_command' in name:
        base = max(base, 0.4)

    return min(1.0, base)


def _calc_cost_efficiency(tool_name: str) -> float:
    """计算成本效率（基于工具类型）"""
    # 低成本工具（纯本地操作）
    low_cost = ['list_files', 'scan_files', 'find_files', 'check_directory',
                'read_file', 'recall', 'remember', 'set_preference',
                'ab_get_text', 'ab_get_html', 'ab_get_title', 'ab_get_url']
    # 中等成本工具
    medium_cost = ['organize', 'move', 'batch', 'edit', 'write', 'run_command',
                   'ab_click', 'ab_fill', 'ab_type', 'ab_press', 'ab_snapshot']
    # 高成本工具（需要网络或外部服务）
    high_cost = ['browser', 'web_search', 'vision', 'ab_screenshot', 'ab_open', 'ab_eval']

    name = tool_name.lower()
    if any(kw in name for kw in low_cost):
        return 0.9
    elif any(kw in name for kw in high_cost):
        return 0.4
    elif any(kw in name for kw in medium_cost):
        return 0.7
    return 0.6


def _calc_risk(tool_name: str, recent_calls: List[dict] = None) -> float:
    """计算风险评估（失败概率）"""
    if not recent_calls:
        return 0.3  # 无历史数据，默认中等风险

    tool_calls = [c for c in recent_calls if c.get('tool_name') == tool_name]
    if not tool_calls:
        return 0.3

    failures = sum(1 for c in tool_calls if not c.get('success', 1))
    return failures / len(tool_calls)


def _calc_history_success(tool_name: str, recent_calls: List[dict] = None) -> float:
    """计算历史成功率"""
    if not recent_calls:
        return 0.5  # 无历史数据，默认中等

    tool_calls = [c for c in recent_calls if c.get('tool_name') == tool_name]
    if not tool_calls:
        return 0.5

    successes = sum(1 for c in tool_calls if c.get('success', 1))
    return successes / len(tool_calls)


# ═══════════════════════════════════════════════════════════
# 第四营：归奇于扐
# ═══════════════════════════════════════════════════════════

def calculate_remainder(r1: int, r2: int, r3: int) -> Tuple[str, int]:
    """
    归奇于扐以象闰。

    汇总三次变的余数，判定爻性。

    大衍筮法的余数规则：
    - 老阳（9）= 余数 0 → old_yang（变爻，确定性极高）
    - 少阳（7）= 余数 1 → young_yang（正常执行）
    - 少阴（8）= 余数 2 → young_yin（需谨慎）
    - 老阴（6）= 余数 3 → old_yin（变爻，不确定性极高）

    Returns:
        (爻性, 综合余数)
    """
    total = r1 + r2 + r3

    # 三营余数各 0-3，总和 0-9
    # 映射策略：根据总余数判定确定性
    # 0-2: 非常确定（老阳/少阳）
    # 3-4: 较确定（少阳）
    # 5-6: 有些不确定（少阴）
    # 7-9: 非常不确定（老阴）
    if total <= 2:
        yan_type = 'old_yang'    # 非常确定，直接执行
    elif total <= 4:
        yan_type = 'young_yang'  # 比较确定，正常执行
    elif total <= 6:
        yan_type = 'young_yin'   # 有些不确定，需要谨慎
    else:
        yan_type = 'old_yin'     # 非常不确定，需要暂停

    remainder = total % 4
    return yan_type, remainder


# ═══════════════════════════════════════════════════════════
# 一变：四营完成一爻
# ═══════════════════════════════════════════════════════════

def one_change(position: int, user_input: str,
               tool_names: List[str] = None,
               tool_descriptions: Dict[str, str] = None,
               recent_calls: List[dict] = None,
               context: dict = None) -> YaoResult:
    """
    四营而成易 — 一次完整的四营操作，判定一个爻。

    Args:
        position: 爻位 (1-6)
        user_input: 用户输入
        tool_names: 可用工具列表
        tool_descriptions: 工具描述
        recent_calls: 最近的工具调用记录
        context: 额外上下文（之前的爻结果等）

    Returns:
        YaoResult 对象
    """
    tool_names = tool_names or []
    context = context or {}

    # ── 第一营：分二 ──
    separation = separate_tools(user_input, tool_names, tool_descriptions)
    # 余数：不相关工具数的不确定性
    r1 = len(separation.irrelevant) % 4
    if r1 > 2:
        r1 = 3 - r1  # 归一化到 0-3

    # ── 第二营：挂一 ──
    main_tool, match_score = hang_one(separation, user_input)
    # 余数：匹配偏差
    r2 = int((1 - match_score) * 4)
    r2 = max(0, min(3, r2))

    # ── 第三营：揲四 ──
    if main_tool:
        si_ying = si_ying_evaluate(main_tool, user_input, recent_calls)
        r3 = si_ying.remainder
    else:
        r3 = 3  # 没有合适工具，最大不确定性

    # ── 第四营：归奇 ──
    yan_type, remainder = calculate_remainder(r1, r2, r3)

    # 计算置信度
    confidence = 1 - (remainder / 3)  # 余数越小越确定

    # 推理说明
    reasoning = (
        f"分二: 相关{len(separation.relevant)}个/不相关{len(separation.irrelevant)}个(r1={r1}) | "
        f"挂一: {main_tool}(匹配={match_score:.2f}, r2={r2}) | "
        f"揲四: {'无合适工具' if not main_tool else si_ying.details}(r3={r3}) | "
        f"归奇: r={remainder} → {yan_type}"
    )

    return YaoResult(
        position=position,
        yan_type=yan_type,
        remainder=remainder,
        changes=[r1, r2, r3],
        confidence=round(confidence, 3),
        reasoning=reasoning,
        tool_name=main_tool,
    )


# ═══════════════════════════════════════════════════════════
# 十有八变而成卦
# ═══════════════════════════════════════════════════════════

def eighteen_changes(user_input: str,
                     tool_names: List[str] = None,
                     tool_descriptions: Dict[str, str] = None,
                     recent_calls: List[dict] = None) -> GuaResult:
    """
    十有八变而成卦。

    6 爻 × 3 变 = 18 次计算，得出完整卦象。

    每爻做 3 次四营计算，取多数决：
    - 3 次中 2 次以上为同一爻性 → 采用
    - 否则取最后一次

    Args:
        user_input: 用户输入
        tool_names: 可用工具列表
        tool_descriptions: 工具描述
        recent_calls: 最近的工具调用记录

    Returns:
        GuaResult 对象
    """
    start = time.time()
    lines = []
    context = {}
    tool_sequence = []

    for position in range(1, 7):
        # 每爻做 3 变
        three_changes = []
        for change_idx in range(3):
            yao = one_change(
                position=position,
                user_input=user_input,
                tool_names=tool_names,
                tool_descriptions=tool_descriptions,
                recent_calls=recent_calls,
                context=context,
            )
            three_changes.append(yao)

        # 多数决：取 3 变中出现最多的爻性
        type_counts = {}
        for yc in three_changes:
            type_counts[yc.yan_type] = type_counts.get(yc.yan_type, 0) + 1

        final_type = max(type_counts, key=type_counts.get)

        # 如果 3 次全不同（各 1 票），取最后一次
        if max(type_counts.values()) == 1:
            final_type = three_changes[-1].yan_type

        # 合并 3 变的余数
        all_changes = [c for yc in three_changes for c in yc.changes]
        avg_remainder = sum(yc.remainder for yc in three_changes) // 3
        avg_confidence = sum(yc.confidence for yc in three_changes) / 3

        # 选出最佳工具（3 变中置信度最高的）
        best_yao = max(three_changes, key=lambda y: y.confidence)
        best_tool = best_yao.tool_name

        final_yao = YaoResult(
            position=position,
            yan_type=final_type,
            remainder=avg_remainder,
            changes=[yc.remainder for yc in three_changes],
            confidence=round(avg_confidence, 3),
            reasoning=f"3变多数决: {[yc.yan_type for yc in three_changes]} → {final_type}",
            tool_name=best_tool,
        )

        lines.append(final_yao)
        context[f'line_{position}'] = final_yao

        if best_tool and best_tool not in tool_sequence:
            tool_sequence.append(best_tool)

    # 取下三爻为内卦，上三爻为外卦
    inner_lines = tuple(lines[i].polarity for i in range(3))   # 爻 1,2,3
    outer_lines = tuple(lines[i].polarity for i in range(3, 6)) # 爻 4,5,6

    inner_trigram = TRIGRAMS.get(inner_lines, '未知')
    outer_trigram = TRIGRAMS.get(outer_lines, '未知')

    # 查卦象表
    hexagram_key = (inner_trigram, outer_trigram)
    hexagram_name, action_hint = HEXAGRAMS.get(hexagram_key, ('未知卦', 'full_stop'))

    elapsed_ms = int((time.time() - start) * 1000)

    return GuaResult(
        hexagram_name=hexagram_name,
        inner_trigram=inner_trigram,
        outer_trigram=outer_trigram,
        action_hint=action_hint,
        lines=lines,
        total_changes=18,
        tool_sequence=tool_sequence,
        elapsed_ms=elapsed_ms,
    )


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def dayan_diagnose(user_input: str,
                   tool_names: List[str] = None,
                   tool_descriptions: Dict[str, str] = None,
                   recent_calls: List[dict] = None) -> GuaResult:
    """
    大衍筮法诊断主入口。

    替代原有的 _taiji_diagnose()，提供完整的六爻十八变卦象。

    Args:
        user_input: 用户输入
        tool_names: 可用工具名列表
        tool_descriptions: 工具描述字典
        recent_calls: 最近工具调用记录

    Returns:
        GuaResult 对象
    """
    result = eighteen_changes(
        user_input=user_input,
        tool_names=tool_names,
        tool_descriptions=tool_descriptions,
        recent_calls=recent_calls,
    )

    # 写入诊断日志
    try:
        log.log_diagnosis(
            inner_state=result.inner_trigram,
            outer_state=result.outer_trigram,
            inner_score=result.lines[0].confidence if result.lines else 0,
            outer_score=result.lines[3].confidence if len(result.lines) > 3 else 0,
            hexagram=result.hexagram_name,
            action_hint=result.action_hint,
            downstream_skill=', '.join(result.tool_sequence[:3]) if result.tool_sequence else None,
            elapsed_ms=result.elapsed_ms,
        )
    except Exception:
        pass  # 日志写入失败不影响诊断

    return result


# ═══════════════════════════════════════════════════════════
# 变爻处理：与 change_engine 的桥接
# ═══════════════════════════════════════════════════════════

def get_changing_lines(gua: GuaResult) -> List[YaoResult]:
    """
    获取变爻（老阳和老阴）。

    老阳（old_yang）和老阴（old_yin）是"变爻"——它们会转化为对卦。
    这对应 Agent 决策中的"这个选择可能会反转"。
    """
    return [line for line in gua.lines if line.yan_type in ('old_yang', 'old_yin')]


def get_bian_hexagram(gua: GuaResult) -> Optional[Tuple[str, str, str]]:
    """
    获取变卦（对卦）。

    老阳变阴，老阴变阳，得出新的卦象。
    变卦代表"如果执行后结果反转，会变成什么状态"。
    """
    changing = get_changing_lines(gua)
    if not changing:
        return None  # 没有变爻，不变

    # 构建变后的六爻
    new_polarities = []
    for line in gua.lines:
        if line.yan_type == 'old_yang':
            new_polarities.append('yin')   # 老阳变阴
        elif line.yan_type == 'old_yin':
            new_polarities.append('yang')  # 老阴变阳
        else:
            new_polarities.append(line.polarity)  # 不变

    new_inner = tuple(new_polarities[:3])
    new_outer = tuple(new_polarities[3:])

    new_inner_name = TRIGRAMS.get(new_inner, '未知')
    new_outer_name = TRIGRAMS.get(new_outer, '未知')

    new_key = (new_inner_name, new_outer_name)
    new_name, new_hint = HEXAGRAMS.get(new_key, ('未知卦', 'full_stop'))

    return (new_name, new_inner_name + new_outer_name, new_hint)


# ═══════════════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════════════

def format_gua_message(gua: GuaResult) -> str:
    """格式化卦象消息（给用户看的）"""
    yao_symbols = {
        'old_yang': '⚌ 老阳', 'young_yang': '⚎ 少阳',
        'young_yin': '⚍ 少阴', 'old_yin': '⚏ 老阴',
    }

    lines_str = []
    for line in reversed(gua.lines):  # 从上爻到初爻
        symbol = yao_symbols.get(line.yan_type, '?')
        tool = f" [{line.tool_name}]" if line.tool_name else ""
        conf = f" ({line.confidence:.0%})" if line.confidence < 0.8 else ""
        lines_str.append(f"  {line.position}爻: {symbol}{tool}{conf}")

    header = f"☯️ {gua.hexagram_name}（{gua.inner_trigram}下{gua.outer_trigram}上）"
    action = f"→ {gua.action_hint}"
    tools = f"推荐工具: {' → '.join(gua.tool_sequence)}" if gua.tool_sequence else ""
    time_str = f"耗时: {gua.elapsed_ms}ms"

    # 检查变爻
    changing = get_changing_lines(gua)
    bian = get_bian_hexagram(gua)
    bian_str = ""
    if bian:
        bian_str = f"\n变卦: {bian[0]} → {bian[2]}"

    parts = [header, *lines_str, action, tools, time_str + bian_str]
    return '\n'.join(p for p in parts if p)
