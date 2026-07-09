"""
智能报告模块 — 业务服务层
===========================================
实现报告生成的核心业务逻辑:
  1. 按报告类型聚合各业务表数据
  2. 组装 Prompt 并调用 Dify Workflow 生成报告
  3. 保存报告内容并更新状态

设计要点（严格对齐文档规范）:
  ⭐ 异步任务使用独立 Session（SessionLocal），不在请求 Session 中执行
  ⭐ 外部 API（Dify）调用在数据库事务外执行
  ⭐ 数据聚合使用原始 SQL（兼容尚未创建 ORM Model 的表）
  ⭐ 所有逻辑外键在应用层校验
  ⭐ 异常时记录 error_message，状态变为 failed

参考文档:
  《教育服务系统_API接口设计规范文档_V1.2》第 8 章 — 智能报告模块接口
  《教育服务系统_API接口设计规范文档_V1.2》第 11 章 — 异步任务接口规范
  《教育服务系统_API接口设计规范文档_V1.2》第 14 章 — 应用层数据一致性保障
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import DIFY_API_URL, DIFY_API_KEY
from models.report import ReportGeneration
from utils.database import SessionLocal
from utils.dify_client import call_dify_workflow

logger = logging.getLogger(__name__)

# ==================== 报告聚合逻辑 ====================


def aggregate_report_data(
    db: Session,
    report_type: str,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> dict[str, Any]:
    """
    根据报告类型聚合业务数据。

    这是整个报告模块的核心数据聚合函数。不同报告类型从不同的业务表
    拉取数据并汇总成结构化字典，作为 Dify Workflow 的输入。

    Args:
        db: 数据库会话（独立 Session）
        report_type: 报告类型枚举值
        period_start: 统计周期起始日期
        period_end: 统计周期截止日期

    Returns:
        聚合后的结构化数据字典，包含:
          - report_type: 报告类型
          - period: 统计周期信息
          - data: 业务统计数据
          - generated_at: 生成时间戳

    Raises:
        ValueError: 不支持的报告类型
    """
    # 如果未指定周期，默认近 7 天
    if period_end is None:
        period_end = date.today()
    if period_start is None:
        period_start = period_end - timedelta(days=7)

    aggregators = {
        "customer_ops": _aggregate_customer_ops,
        "daily_summary": _aggregate_daily_summary,
        "psych_weekly": _aggregate_psych_weekly,
        "complaint_weekly": _aggregate_complaint_weekly,
        "weekly_summary": _aggregate_weekly_summary,
    }

    aggregator = aggregators.get(report_type)
    if aggregator is None:
        raise ValueError(f"不支持的报告类型: {report_type}")

    logger.info(
        "开始聚合数据: report_type=%s, period=%s ~ %s",
        report_type,
        period_start,
        period_end,
    )

    data = aggregator(db, period_start, period_end)

    return {
        "report_type": report_type,
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "data": data,
        "generated_at": datetime.now().isoformat(),
    }


def _aggregate_customer_ops(
    db: Session, start: date, end: date
) -> dict[str, Any]:
    """
    聚合全域客户经营数据。

    数据来源: crm_lead, crm_follow_up
    输出: 客户来源分布、各状态数量、转化率、流失原因统计
    """
    result: dict[str, Any] = {
        "source": "crm_lead + crm_follow_up",
        "leads_by_status": {},
        "leads_by_source": {},
        "total_leads": 0,
        "follow_ups_count": 0,
        "lost_reasons": [],
    }

    try:
        # 客户状态分布
        rows = db.execute(
            text(
                """
                SELECT status, COUNT(*) as cnt
                FROM crm_lead
                WHERE create_time >= :start AND create_time < :end
                GROUP BY status
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["leads_by_status"] = {row[0]: row[1] for row in rows}
        result["total_leads"] = sum(result["leads_by_status"].values())

        # 客户来源分布
        rows = db.execute(
            text(
                """
                SELECT source_channel, COUNT(*) as cnt
                FROM crm_lead
                WHERE create_time >= :start AND create_time < :end
                GROUP BY source_channel
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["leads_by_source"] = {row[0] or "未知": row[1] for row in rows}

        # 跟进记录数量
        rows = db.execute(
            text(
                """
                SELECT COUNT(*) as cnt
                FROM crm_follow_up
                WHERE create_time >= :start AND create_time < :end
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["follow_ups_count"] = rows[0][0] if rows else 0

        # 流失原因
        rows = db.execute(
            text(
                """
                SELECT lost_reason, COUNT(*) as cnt
                FROM crm_lead
                WHERE status = 'lost'
                  AND create_time >= :start AND create_time < :end
                  AND lost_reason IS NOT NULL
                GROUP BY lost_reason
                ORDER BY cnt DESC
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["lost_reasons"] = [
            {"reason": row[0], "count": row[1]} for row in rows
        ]

    except Exception as e:
        logger.warning("客户数据聚合部分失败: %s，返回已有数据", e)
        result["aggregation_error"] = str(e)

    return result


def _aggregate_daily_summary(
    db: Session, start: date, end: date
) -> dict[str, Any]:
    """
    聚合员工日报汇总数据。

    数据来源: employee_daily_report
    输出: 日报提交情况、关键进展、风险汇总
    """
    result: dict[str, Any] = {
        "source": "employee_daily_report",
        "total_reports": 0,
        "reports_by_date": {},
        "risks": [],
        "key_progress": [],
    }

    try:
        # 日报提交总数
        rows = db.execute(
            text(
                """
                SELECT COUNT(*) as cnt
                FROM employee_daily_report
                WHERE report_date >= :start AND report_date <= :end
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["total_reports"] = rows[0][0] if rows else 0

        # 按日期分布
        rows = db.execute(
            text(
                """
                SELECT report_date, COUNT(*) as cnt
                FROM employee_daily_report
                WHERE report_date >= :start AND report_date <= :end
                GROUP BY report_date
                ORDER BY report_date
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["reports_by_date"] = {
            str(row[0]): row[1] for row in rows
        }

        # 风险汇总
        rows = db.execute(
            text(
                """
                SELECT employee_id, risks, report_date
                FROM employee_daily_report
                WHERE report_date >= :start AND report_date <= :end
                  AND risks IS NOT NULL
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        for row in rows:
            try:
                risks = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                if risks:
                    result["risks"].append({
                        "employee_id": row[0],
                        "date": str(row[2]),
                        "risks": risks,
                    })
            except (json.JSONDecodeError, TypeError):
                pass

    except Exception as e:
        logger.warning("日报数据聚合部分失败: %s，返回已有数据", e)
        result["aggregation_error"] = str(e)

    return result


def _aggregate_psych_weekly(
    db: Session, start: date, end: date
) -> dict[str, Any]:
    """
    聚合学生心理周报数据。

    数据来源: student_psych_record, student_psych_alert
    输出: 情绪趋势、风险等级分布、预警处理情况
    """
    result: dict[str, Any] = {
        "source": "student_psych_record + student_psych_alert",
        "total_records": 0,
        "risk_distribution": {"low": 0, "medium": 0, "high": 0},
        "alerts_created": 0,
        "alerts_resolved": 0,
        "alerts_pending": 0,
        "emotion_trend": [],
    }

    try:
        # 心理记录总数
        rows = db.execute(
            text(
                """
                SELECT COUNT(*) as cnt
                FROM student_psych_record
                WHERE record_date >= :start AND record_date <= :end
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["total_records"] = rows[0][0] if rows else 0

        # 预警统计
        rows = db.execute(
            text(
                """
                SELECT risk_level, COUNT(*) as cnt
                FROM student_psych_alert
                WHERE create_time >= :start AND create_time < :end
                GROUP BY risk_level
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        for row in rows:
            if row[0] in result["risk_distribution"]:
                result["risk_distribution"][row[0]] = row[1]

        # 预警处理状态
        rows = db.execute(
            text(
                """
                SELECT status, COUNT(*) as cnt
                FROM student_psych_alert
                WHERE create_time >= :start AND create_time < :end
                GROUP BY status
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        for row in rows:
            if row[0] == "pending":
                result["alerts_pending"] = row[1]
            elif row[0] == "resolved":
                result["alerts_resolved"] = row[1]
        result["alerts_created"] = (
            result["alerts_pending"] + result["alerts_resolved"]
        )

    except Exception as e:
        logger.warning("心理数据聚合部分失败: %s，返回已有数据", e)
        result["aggregation_error"] = str(e)

    return result


def _aggregate_complaint_weekly(
    db: Session, start: date, end: date
) -> dict[str, Any]:
    """
    聚合投诉处理周报数据。

    数据来源: student_feedback_ticket
    输出: 投诉分类统计、处理时效分析、高频问题
    """
    result: dict[str, Any] = {
        "source": "student_feedback_ticket",
        "total_tickets": 0,
        "by_type": {},
        "by_category": {},
        "by_status": {},
        "avg_resolution_hours": None,
    }

    try:
        # 工单总数
        rows = db.execute(
            text(
                """
                SELECT COUNT(*) as cnt
                FROM student_feedback_ticket
                WHERE create_time >= :start AND create_time < :end
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["total_tickets"] = rows[0][0] if rows else 0

        # 按类型分布
        rows = db.execute(
            text(
                """
                SELECT ticket_type, COUNT(*) as cnt
                FROM student_feedback_ticket
                WHERE create_time >= :start AND create_time < :end
                GROUP BY ticket_type
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["by_type"] = {row[0]: row[1] for row in rows}

        # 按分类分布
        rows = db.execute(
            text(
                """
                SELECT category, COUNT(*) as cnt
                FROM student_feedback_ticket
                WHERE create_time >= :start AND create_time < :end
                GROUP BY category
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["by_category"] = {
            row[0] or "未分类": row[1] for row in rows
        }

        # 按状态分布
        rows = db.execute(
            text(
                """
                SELECT status, COUNT(*) as cnt
                FROM student_feedback_ticket
                WHERE create_time >= :start AND create_time < :end
                GROUP BY status
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        result["by_status"] = {row[0]: row[1] for row in rows}

    except Exception as e:
        logger.warning("投诉数据聚合部分失败: %s，返回已有数据", e)
        result["aggregation_error"] = str(e)

    return result


def _aggregate_weekly_summary(
    db: Session, start: date, end: date
) -> dict[str, Any]:
    """
    聚合综合周报数据（多数据源）。

    聚合以上所有类型的数据，形成综合概况。
    """
    return {
        "customer_ops": _aggregate_customer_ops(db, start, end),
        "daily_summary": _aggregate_daily_summary(db, start, end),
        "psych_weekly": _aggregate_psych_weekly(db, start, end),
        "complaint_weekly": _aggregate_complaint_weekly(db, start, end),
    }


# ==================== 报告生成主流程 ====================


def generate_report_async(report_id: int) -> None:
    """
    异步报告生成主流程（在 BackgroundTasks 中执行）。

    ⭐ 核心原则（对齐 API 文档 11.5 节）:
      1. 使用独立 Session（SessionLocal），不在请求 Session 中执行
      2. 数据聚合在事务中完成
      3. Dify 调用在事务外执行
      4. 结果保存在独立事务中
      5. 异常时更新 status='failed' 并记录 error_message

    执行流程:
      1. 打开独立数据库会话
      2. 查询 report_generation 记录
      3. 聚合业务数据（事务内）
      4. 组装 Prompt 并调用 Dify（事务外）
      5. 解析 Dify 输出（JSON + HTML）
      6. 保存结果（独立事务）
      7. 异常处理：记录错误，更新状态为 failed

    Args:
        report_id: 报告记录 ID
    """
    db = SessionLocal()
    logger.info("异步报告生成开始: report_id=%d", report_id)

    try:
        # ============================================
        # 第 1 步：查询报告记录
        # ============================================
        report = db.query(ReportGeneration).filter_by(id=report_id).first()
        if not report:
            logger.error("报告记录不存在: report_id=%d", report_id)
            return

        # ============================================
        # 第 2 步：聚合业务数据（事务内）
        # ============================================
        with db.begin():
            raw_data = aggregate_report_data(
                db=db,
                report_type=report.report_type,
                period_start=report.period_start,
                period_end=report.period_end,
            )
        # 事务已提交，释放数据库连接

        logger.info(
            "数据聚合完成: report_id=%d, data_keys=%s",
            report_id,
            list(raw_data.get("data", {}).keys()),
        )

        # ============================================
        # 第 3 步：调用 Dify 生成报告（事务外）
        # ============================================
        # ⭐ 关键：Dify 调用必须在数据库事务外！
        # 避免事务长时间持有导致连接池耗尽。
        ai_result = _call_dify_for_report(
            report_type=report.report_type,
            report_title=report.report_title,
            raw_data=raw_data,
        )

        # ============================================
        # 第 4 步：保存结果（独立事务）
        # ============================================
        with db.begin():
            report.report_content = ai_result.get("content")
            report.report_html = ai_result.get("html")
            report.status = "completed"

        logger.info("报告生成成功: report_id=%d", report_id)

    except Exception as e:
        # ============================================
        # 异常处理：记录失败原因
        # ============================================
        error_msg = f"{type(e).__name__}: {str(e)}"[:500]
        logger.error("报告生成失败: report_id=%d, error=%s", report_id, error_msg)

        try:
            with db.begin():
                report = db.query(ReportGeneration).filter_by(id=report_id).first()
                if report:
                    report.status = "failed"
                    report.error_message = error_msg
        except Exception as db_err:
            logger.error(
                "更新报告失败状态时出错: report_id=%d, error=%s",
                report_id,
                db_err,
            )

    finally:
        db.close()
        logger.info("异步报告生成结束: report_id=%d", report_id)


def _call_dify_for_report(
    report_type: str,
    report_title: str,
    raw_data: dict[str, Any],
) -> dict[str, Any]:
    """
    调用 Dify Workflow 生成报告。

    向 Dify 报告生成 Workflow 传入:
      - report_type: 报告类型
      - report_title: 报告标题
      - raw_data: 聚合后的业务数据（JSON 字符串）

    从 Dify 响应中提取:
      - content: 结构化报告内容（JSON，对应 report_content）
      - html: 报告 HTML（对应 report_html）

    Args:
        report_type: 报告类型
        report_title: 报告标题
        raw_data: 聚合数据字典

    Returns:
        {"content": {...}, "html": "..."}

    Raises:
        RuntimeError: Dify 调用失败
        ValueError: Dify 返回格式不正确
    """
    # 组装 Dify Workflow 输入
    workflow_inputs = {
        "report_type": report_type,
        "report_title": report_title,
        "raw_data": json.dumps(raw_data, ensure_ascii=False, default=str),
    }

    logger.info(
        "调用 Dify 报告生成 Workflow: report_type=%s, title=%s",
        report_type,
        report_title,
    )

    try:
        # 调用 Dify Workflow（阻塞模式）
        dify_response = call_dify_workflow(
            inputs=workflow_inputs,
            timeout=180,  # 报告生成可能较慢，给 3 分钟
        )
    except RuntimeError:
        # 如果 Dify API Key 未配置，使用本地模拟逻辑（MVP 演示兜底）
        if not DIFY_API_KEY:
            logger.warning("Dify API Key 未配置，使用模拟报告生成")
            return _generate_fallback_report(report_type, report_title, raw_data)
        raise

    # 解析 Dify 输出
    try:
        data = dify_response.get("data", {})
        outputs = data.get("outputs", {})

        # 从 Dify Workflow 输出节点提取报告内容
        content = outputs.get("report_content") or outputs.get("text") or outputs
        html = outputs.get("report_html") or outputs.get("html") or ""

        # 如果 content 是字符串，尝试解析为 JSON
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                # 不是 JSON，包装为结构化对象
                content = {"summary": content}

        return {
            "content": content,
            "html": str(html) if html else _default_html(report_title, content),
        }

    except Exception as e:
        logger.error("解析 Dify 输出失败: %s, outputs=%s", e, outputs)
        raise ValueError(f"解析 Dify 输出失败: {e}")


def _generate_fallback_report(
    report_type: str,
    report_title: str,
    raw_data: dict[str, Any],
) -> dict[str, Any]:
    """
    MVP 时期的模拟报告生成（Dify 不可用时的兜底方案）。

    当 Dify API Key 未配置或 Dify 不可用时，生成基础的结构化报告，
    确保演示链路不断。

    Args:
        report_type: 报告类型
        report_title: 报告标题
        raw_data: 聚合数据

    Returns:
        模拟的报告内容
    """
    period = raw_data.get("period", {})
    data = raw_data.get("data", {})

    # 构建模拟报告内容
    content = {
        "summary": f"{report_title}已生成（模拟模式）。"
        f"统计周期: {period.get('start', 'N/A')} ~ {period.get('end', 'N/A')}。"
        f"本报告基于 {data.get('source', '多数据源')} 的数据自动生成。",
        "key_findings": [
            "此报告为 MVP 阶段的模拟生成结果",
            "Dify API Key 配置后将启用 AI 生成完整分析",
        ],
        "risks": ["Dify 服务未配置，无法生成完整风险分析"],
        "suggestions": [
            "配置 .env 中的 DIFY_API_KEY 以启用 AI 报告生成",
            "或部署本地 Dify 社区版并配置报告生成 Workflow",
        ],
        "raw_statistics": {
            "total_leads": data.get("total_leads", 0),
            "total_reports": data.get("total_reports", 0),
            "total_tickets": data.get("total_tickets", 0),
            "total_records": data.get("total_records", 0),
        },
    }

    html = _default_html(report_title, content)

    return {"content": content, "html": html}


def _default_html(report_title: str, content: dict) -> str:
    """生成默认的 HTML 报告模板"""
    summary = content.get("summary", "")
    findings = content.get("key_findings", [])
    risks = content.get("risks", [])
    suggestions = content.get("suggestions", [])

    findings_html = "".join(f"<li>{f}</li>" for f in findings)
    risks_html = "".join(f"<li>{r}</li>" for r in risks)
    suggestions_html = "".join(f"<li>{s}</li>" for s in suggestions)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{report_title}</title>
<style>
  body {{ font-family: 'Microsoft YaHei', sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
  h1 {{ color: #1a1a2e; border-bottom: 2px solid #16213e; padding-bottom: 10px; }}
  h2 {{ color: #0f3460; margin-top: 24px; }}
  .summary {{ background: #f0f4ff; padding: 16px; border-radius: 8px; margin: 12px 0; }}
  ul {{ line-height: 1.8; }}
  .footer {{ margin-top: 32px; color: #999; font-size: 12px; border-top: 1px solid #eee; padding-top: 12px; }}
</style>
</head>
<body>
  <h1>{report_title}</h1>
  <div class="summary">{summary}</div>
  <h2>📊 关键发现</h2>
  <ul>{findings_html}</ul>
  <h2>⚠️ 风险预警</h2>
  <ul>{risks_html}</ul>
  <h2>💡 改进建议</h2>
  <ul>{suggestions_html}</ul>
  <div class="footer">本报告由教育服务系统自动生成 | AI 驱动 · 数据驱动决策</div>
</body>
</html>"""
