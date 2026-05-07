# -*- coding: utf-8 -*-
"""
卦象-工具效果表 — 让Agent"第一次慢第二次快"

每次工具执行后记录：卦象 × 工具 → 成功/失败/耗时
下次同卦象下选择工具时，优先选成功率高的
"""

import sqlite3
import time
import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ToolScore:
    """工具在某卦象下的效果评分"""
    tool_name: str
    success_count: int
    fail_count: int
    avg_duration_ms: float
    success_rate: float
    total_uses: int


class GuaToolEffectiveness:
    """
    卦象-工具效果追踪器
    
    使用：
        eff = GuaToolEffectiveness("data/gua_effectiveness.db")
        
        # 记录
        eff.record("乾为天", "ab_click", success=True, duration_ms=150)
        
        # 查询最佳工具
        best = eff.query_best_tools("乾为天", ["ab_click", "file_read", "ab_open"])
        # → [ToolScore("ab_click", 95% success, ...), ...]
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'gua_effectiveness.db')
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gua_tool_effectiveness (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hexagram TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                duration_ms REAL DEFAULT 0,
                timestamp REAL NOT NULL,
                session_id TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gua_tool 
            ON gua_tool_effectiveness(hexagram, tool_name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON gua_tool_effectiveness(timestamp)
        """)
        conn.commit()
        conn.close()

    def record(self, hexagram: str, tool_name: str, success: bool,
               duration_ms: float = 0, session_id: str = ""):
        """
        记录一次工具执行效果
        
        Args:
            hexagram: 当前卦名
            tool_name: 工具名
            success: 是否成功
            duration_ms: 执行耗时（毫秒）
            session_id: 会话ID
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO gua_tool_effectiveness (hexagram, tool_name, success, duration_ms, timestamp, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (hexagram, tool_name, 1 if success else 0, duration_ms, time.time(), session_id)
        )
        conn.commit()
        conn.close()

    def query_best_tools(self, hexagram: str, candidate_tools: List[str],
                         limit: int = 5) -> List[ToolScore]:
        """
        查询某卦象下效果最好的工具（全量聚合，v1 兼容）

        按成功率降序排列，同成功率按平均耗时升序

        Args:
            hexagram: 卦名
            candidate_tools: 候选工具列表
            limit: 返回数量

        Returns:
            按效果排序的 ToolScore 列表
        """
        if not candidate_tools:
            return []

        conn = sqlite3.connect(self.db_path)
        placeholders = ','.join('?' for _ in candidate_tools)

        query = f"""
            SELECT
                tool_name,
                SUM(success) as success_count,
                COUNT(*) - SUM(success) as fail_count,
                AVG(duration_ms) as avg_duration,
                CAST(SUM(success) AS REAL) / COUNT(*) as success_rate,
                COUNT(*) as total
            FROM gua_tool_effectiveness
            WHERE hexagram = ? AND tool_name IN ({placeholders})
            GROUP BY tool_name
            ORDER BY success_rate DESC, avg_duration ASC
            LIMIT ?
        """

        params = [hexagram] + candidate_tools + [limit]
        rows = conn.execute(query, params).fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append(ToolScore(
                tool_name=row[0],
                success_count=row[1],
                fail_count=row[2],
                avg_duration_ms=row[3] or 0,
                success_rate=row[4] or 0,
                total_uses=row[5],
            ))

        # 补充没有记录的工具（默认成功率0.5，视为中性）
        recorded_tools = {r.tool_name for r in results}
        for tool in candidate_tools:
            if tool not in recorded_tools and len(results) < limit:
                results.append(ToolScore(
                    tool_name=tool,
                    success_count=0,
                    fail_count=0,
                    avg_duration_ms=0,
                    success_rate=0.5,  # 无数据时中性
                    total_uses=0,
                ))

        return results

    def query_best_tools_v2(self, hexagram: str, candidate_tools: List[str],
                            limit: int = 5, recent_n: int = 10,
                            short_weight: float = 0.7) -> List[ToolScore]:
        """
        双窗口加权查询 — 近期数据权重更高

        short_weight * 最近 N 次成功率 + (1-short_weight) * 全量成功率

        Args:
            hexagram: 卦名
            candidate_tools: 候选工具列表
            limit: 返回数量
            recent_n: 近期窗口大小
            short_weight: 近期窗口权重 (0.0-1.0)

        Returns:
            按加权效果排序的 ToolScore 列表
        """
        if not candidate_tools:
            return []

        results = []
        for tool in candidate_tools:
            overall = self._query_single(hexagram, tool)
            recent = self._query_single(hexagram, tool, limit=recent_n,
                                         order_by="timestamp DESC")

            if recent.total_uses == 0:
                # 无近期数据，用全量
                score = overall.success_rate
            elif overall.total_uses == 0:
                # 无数据，中性
                score = 0.5
            else:
                score = (short_weight * recent.success_rate
                         + (1 - short_weight) * overall.success_rate)

            results.append(ToolScore(
                tool_name=tool,
                success_count=overall.success_count,
                fail_count=overall.fail_count,
                avg_duration_ms=overall.avg_duration_ms,
                success_rate=score,
                total_uses=overall.total_uses,
            ))

        results.sort(key=lambda x: (-x.success_rate, x.avg_duration_ms))
        return results[:limit]

    def _query_single(self, hexagram: str, tool_name: str,
                      limit: int = None, order_by: str = "success_rate DESC, avg_duration ASC") -> ToolScore:
        """查询单个工具在某卦象下的效果统计

        Args:
            hexagram: 卦名
            tool_name: 工具名
            limit: 限制记录数（用于近期窗口查询）
            order_by: 排序方式
        """
        conn = sqlite3.connect(self.db_path)

        limit_clause = f"ORDER BY {order_by} LIMIT {limit}" if limit is not None else ""
        # 如果有 LIMIT，需要用子查询先排序再聚合
        if limit is not None:
            query = f"""
                SELECT
                    ? as tool_name,
                    SUM(success) as success_count,
                    COUNT(*) - SUM(success) as fail_count,
                    AVG(duration_ms) as avg_duration,
                    CAST(SUM(success) AS REAL) / COUNT(*) as success_rate,
                    COUNT(*) as total
                FROM (
                    SELECT success, duration_ms
                    FROM gua_tool_effectiveness
                    WHERE hexagram = ? AND tool_name = ?
                    ORDER BY {order_by}
                    LIMIT ?
                )
            """
            params = [tool_name, hexagram, tool_name, limit]
        else:
            query = """
                SELECT
                    tool_name,
                    SUM(success) as success_count,
                    COUNT(*) - SUM(success) as fail_count,
                    AVG(duration_ms) as avg_duration,
                    CAST(SUM(success) AS REAL) / COUNT(*) as success_rate,
                    COUNT(*) as total
                FROM gua_tool_effectiveness
                WHERE hexagram = ? AND tool_name = ?
                GROUP BY tool_name
            """
            params = [hexagram, tool_name]

        row = conn.execute(query, params).fetchone()
        conn.close()

        if not row or row[5] == 0:
            return ToolScore(
                tool_name=tool_name, success_count=0, fail_count=0,
                avg_duration_ms=0, success_rate=0.5, total_uses=0,
            )

        return ToolScore(
            tool_name=row[0],
            success_count=row[1],
            fail_count=row[2],
            avg_duration_ms=row[3] or 0,
            success_rate=row[4] or 0,
            total_uses=row[5],
        )

    def get_tool_stats(self, tool_name: str) -> Dict[str, float]:
        """获取某工具在所有卦象下的总体统计"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(success) as successes,
                AVG(duration_ms) as avg_duration
            FROM gua_tool_effectiveness
            WHERE tool_name = ?
        """, (tool_name,)).fetchone()
        conn.close()

        if not row or row[0] == 0:
            return {"total": 0, "success_rate": 0.5, "avg_duration_ms": 0}

        return {
            "total": row[0],
            "success_rate": row[1] / row[0] if row[0] > 0 else 0.5,
            "avg_duration_ms": row[2] or 0,
        }

    def get_gua_stats(self, hexagram: str) -> Dict[str, any]:
        """获取某卦象下的整体统计"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("""
            SELECT 
                COUNT(DISTINCT tool_name) as tool_count,
                COUNT(*) as total_calls,
                AVG(CAST(success AS REAL)) as overall_success_rate
            FROM gua_tool_effectiveness
            WHERE hexagram = ?
        """, (hexagram,)).fetchone()
        conn.close()

        return {
            "tool_count": row[0] or 0,
            "total_calls": row[1] or 0,
            "overall_success_rate": row[2] or 0.5,
        }

    def get_recent_stats(self, limit: int = 100) -> Dict[str, dict]:
        """
        获取最近 limit 条记录中每个工具的聚合统计。
        返回格式：{ tool_name: { 'total': int, 'fail_count': int, 'fail_rate': float }, ... }
        用于 Phase 3 自我优化引擎的模式检测。
        """
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT tool_name,
                   COUNT(*) AS total,
                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS fail_count
            FROM (
                SELECT tool_name, success
                FROM gua_tool_effectiveness
                ORDER BY id DESC
                LIMIT ?
            )
            GROUP BY tool_name
        """, (limit,)).fetchall()
        conn.close()

        stats = {}
        for tool, total, fail_count in rows:
            stats[tool] = {
                'total': total,
                'fail_count': fail_count,
                'fail_rate': fail_count / total if total > 0 else 0.0
            }
        return stats

    def cleanup_old_records(self, days: int = 30):
        """清理超过N天的旧记录"""
        cutoff = time.time() - (days * 86400)
        conn = sqlite3.connect(self.db_path)
        deleted = conn.execute(
            "DELETE FROM gua_tool_effectiveness WHERE timestamp < ?", (cutoff,)
        ).rowcount
        conn.commit()
        conn.close()
        return deleted
