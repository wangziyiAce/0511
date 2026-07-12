"""智能报告助手 — 报告能力目录。

本模块从 ``REPORT_REGISTRY`` 动态生成 LLM 可选的报告类型列表。
不单独维护第二份报告类型配置，确保与注册表始终同步。

职责：
- 从 Registry 读取十类报告元数据
- 附加助手模块维护的业务关键词（用于本地关键词降级匹配）
- 按当前用户角色过滤可访问的报告类型
- 返回 ``ReportTypeOption`` 列表供 LLM Structured Output 选择
"""

from __future__ import annotations

from services.reporting.assistant.schemas import ReportTypeOption
from services.reporting.registry import REPORT_REGISTRY, ReportDefinition


# ---------------------------------------------------------------------------
# 业务关键词映射 — 助手模块维护
# 报告类型定义本身来自 Registry，这里只附加关键词用于本地降级匹配
# ---------------------------------------------------------------------------

REPORT_KEYWORDS: dict[str, list[str]] = {
    "application_risk": ["申请", "材料", "截止", "风险", "文书", "签证材料"],
    "sales_funnel": ["销售", "漏斗", "转化", "线索", "签约", "商机"],
    "channel_roi": ["渠道", "投放", "ROI", "划算", "推广", "广告", "成本"],
    "service_sla": ["服务", "SLA", "响应", "时效", "变慢", "超时"],
    "psych_weekly": ["心理", "预警", "情绪", "心理咨询"],
    "complaint_weekly": ["投诉", "处理", "纠纷", "高频问题"],
    "customer_ops": ["客户", "经营", "运营", "流失", "客户分析"],
    "daily_summary": ["日报", "每日", "今天工作", "昨日工作"],
    "weekly_summary": ["周报", "综合", "经营", "老板", "管理层", "跨模块"],
    "action_closure": ["行动", "闭环", "完成率", "逾期", "目标达成"],
}


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def build_report_catalog(
    *,
    user_role_code: str | None = None,
) -> list[ReportTypeOption]:
    """从 REPORT_REGISTRY 动态生成当前角色可选的报告类型列表。

    本函数是报告类型信息的唯一来源。LLM 的 ``report_type`` 输出必须来自
    此列表，意图解析器会将其作为 Structured Output 的约束条件传入。

    Args:
        user_role_code: 当前用户角色。为 None 时返回所有类型但标记 allowed=False。

    Returns:
        ReportTypeOption 列表，按 report_type 字母排序。
    """
    options: list[ReportTypeOption] = []
    for report_type, definition in REPORT_REGISTRY.items():
        allowed = _is_role_allowed(user_role_code, definition)
        keywords = REPORT_KEYWORDS.get(report_type, [])
        options.append(
            ReportTypeOption(
                report_type=report_type,
                label=definition.label,
                default_period_rule=definition.default_period_rule,
                allowed=allowed,
                keywords=keywords,
            )
        )
    options.sort(key=lambda o: o.report_type)
    return options


def get_allowed_report_types(user_role_code: str | None) -> set[str]:
    """返回当前角色有权访问的报告类型编码集合。

    用于意图解析后的权限校验和 LLM 白名单约束。
    """
    return {
        option.report_type
        for option in build_report_catalog(user_role_code=user_role_code)
        if option.allowed
    }


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _is_role_allowed(role_code: str | None, definition: ReportDefinition) -> bool:
    """判断指定角色是否有权访问该报告类型。

    admin 无条件通过；其他角色必须在 allowed_roles 白名单中。
    未登录用户（role_code=None）返回 False。
    """
    if role_code is None:
        return False
    if role_code == "admin":
        return True
    return role_code in definition.allowed_roles
