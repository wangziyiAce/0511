"""智能报告助手 — 多轮上下文与实体引用解析。

本模块负责：
1. 解析用户消息中的实体引用（"第一个""第二个""最高风险"等）
2. 验证客户端传入的 ``ReferencedEntity`` 是否允许访问
3. 提供多轮追问所需的最小上下文验证

架构位置：
    用户自然语言 → ContextResolver → 明确 entity_id → 只读工具

设计原则（来自 Iteration 计划）：
- 中文序号优先使用确定性规则，不完全依赖 LLM
- 客户端上下文不可信，必须重新校验权限和数据存在性
- 无法确定时返回 None，由 service 层触发澄清
"""

from __future__ import annotations

import logging
from typing import Optional

from services.reporting.assistant.schemas import (
    ReferencedEntity,
    ReportConversationContext,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 中文序号映射 — 确定性规则，不依赖 LLM
# ---------------------------------------------------------------------------

_ORDINAL_MAP: dict[str, int] = {
    "第一": 1, "第一个": 1, "第1": 1, "第1个": 1,
    "第二": 2, "第二个": 2, "第2": 2, "第2个": 2,
    "第三": 3, "第三个": 3, "第3": 3, "第3个": 3,
    "第四": 4, "第四个": 4, "第4": 4, "第4个": 4,
    "第五": 5, "第五个": 5, "第5": 5, "第5个": 5,
}

# 语义引用关键词
_SEMANTIC_REF_KEYWORDS = [
    "最严重的", "最高风险", "风险最高的", "最危险的",
    "刚才最高风险的", "刚才最严重的",
    "刚才第一个", "刚才的", "那个",
]


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def resolve_entity_reference(
    *,
    message: str,
    context: ReportConversationContext,
) -> Optional[ReferencedEntity]:
    """解析用户消息中的实体引用。

    优先级：
    1. 用户显式 entity_id（如 application_id、report_id 数字）
    2. 明确中文序号引用（"第一个""第二个"）
    3. 语义引用（"最高风险""最严重的"）
    4. 上一轮唯一实体（只有一个 referenced_entity 时）
    5. 无法确定 → 返回 None，调用方应触发澄清

    Args:
        message: 用户当前消息。
        context: 前端传回的会话上下文。

    Returns:
        解析出的 ReferencedEntity，无法确定时返回 None。
    """
    entities = context.referenced_entities or []

    # ---- 优先级 1：显式 entity_id ----
    # 匹配纯数字 ID（4-8 位）或字母前缀 ID（如 A1024、APP2048）
    import re
    explicit_ids = re.findall(r'\b([A-Za-z]*\d{4,8})\b', message)
    if explicit_ids:
        for eid in explicit_ids:
            # 精确匹配 entity_id
            for entity in entities:
                if str(entity.entity_id) == eid:
                    logger.debug("显式 entity_id 匹配: %s", eid)
                    return entity
            # 也尝试匹配 report_id（纯数字）
            if eid.isdigit() and context.last_report_id and str(context.last_report_id) == eid:
                return ReferencedEntity(
                    position=0,
                    entity_type="report",
                    entity_id=str(context.last_report_id),
                    display_name=f"报告 #{context.last_report_id}",
                    source_report_id=context.last_report_id,
                )

    # ---- 优先级 2：中文序号引用 ----
    for keyword, position in _ORDINAL_MAP.items():
        if keyword in message:
            if not entities:
                return None  # 有引用但无上下文 → 需要澄清
            if position > len(entities):
                return None  # 越界 → 需要澄清
            target = entities[position - 1]
            logger.debug("序号引用: '%s' → position=%d entity=%s", keyword, position, target.entity_id)
            return target

    # ---- 优先级 3：语义引用 ----
    for keyword in _SEMANTIC_REF_KEYWORDS:
        if keyword in message:
            if not entities:
                return None
            # 找最高风险的实体（按 risk_score 或 risk_level）
            best = _find_highest_risk_entity(entities)
            if best:
                logger.debug("语义引用: '%s' → entity=%s", keyword, best.entity_id)
                return best
            return entities[0]  # 降级：取第一个

    # ---- 优先级 4：上一轮唯一实体 ----
    if len(entities) == 1:
        # 检查消息是否看起来像追问（包含疑问词或简短）
        follow_up_indicators = ["为什么", "怎么", "如何", "是什么", "多少", "哪个", "什么", "这个", "那个"]
        if any(ind in message for ind in follow_up_indicators) or len(message) < 15:
            logger.debug("唯一实体默认引用: entity=%s", entities[0].entity_id)
            return entities[0]

    # ---- 优先级 5：无法确定 ----
    return None


def validate_context_access(
    *,
    context: ReportConversationContext,
    current_user_id: int,
    current_user_role: str,
    accessible_report_ids: set[int],
) -> bool:
    """验证客户端传入的上下文是否可被当前用户访问。

    检查项：
    1. last_report_id 是否在用户可访问范围内
    2. referenced_entities 中的 source_report_id 是否合法
    3. entity_id 是否存在于对应报告中（由工具层验证）

    Args:
        context: 客户端传回的会话上下文。
        current_user_id: 当前用户 ID。
        current_user_role: 当前用户角色。
        accessible_report_ids: 当前用户可访问的报告 ID 集合。

    Returns:
        True 表示上下文合法可用。
    """
    # 管理角色可访问所有
    if current_user_role in ("admin", "manager", "team_leader"):
        return True

    # 检查 last_report_id
    if context.last_report_id and context.last_report_id not in accessible_report_ids:
        logger.warning(
            "用户 %d 试图访问不可达报告 %d",
            current_user_id,
            context.last_report_id,
        )
        return False

    # 检查 referenced_entities 的 source_report_id
    for entity in (context.referenced_entities or []):
        if entity.source_report_id and entity.source_report_id not in accessible_report_ids:
            logger.warning(
                "用户 %d 引用了不可达报告的实体: report=%d entity=%s",
                current_user_id,
                entity.source_report_id,
                entity.entity_id,
            )
            return False

    return True


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _find_highest_risk_entity(entities: list[ReferencedEntity]) -> Optional[ReferencedEntity]:
    """从实体列表中找到风险最高的那个。

    优先按 risk_score 降序，其次按 risk_level（high>medium>low）。
    """
    risk_order = {"high": 3, "medium": 2, "low": 1}

    best = None
    best_score = -1
    best_risk = -1

    for entity in entities:
        metadata = entity.metadata or {}
        score = metadata.get("risk_score", 0)
        level = risk_order.get(metadata.get("risk_level", ""), 0)

        if score > best_score or (score == best_score and level > best_risk):
            best_score = score
            best_risk = level
            best = entity

    return best
