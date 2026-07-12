"""
智能报告 — API 路由
===========================================
口述日报（AI 结构化）+ 管理日报查阅。

路由前缀: /api/v1/report  (于 main.py 中挂载)

接口清单:
  POST /api/v1/report/dictate    员工口述日报，AI 自动结构化后落库
  GET  /api/v1/report            管理层查阅日报列表（员工/日期区间筛选）
  GET  /api/v1/report/summary    管理层日报汇总（含 AI 自然语言总览）

鉴权: 统一走 get_current_user（仅登录校验，沿用现有取舍不加角色限制）
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from models.common import get_current_user
from models.user import SysUser
from schemas.crm import (
    DailyReportResponse,
    DailyReportManagementSummary,
    DictateReportRequest,
)
from services.report_service import ReportService
from utils.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["智能报告"])


@router.post("/dictate", summary="口述日报（AI 自动结构化）")
def dictate_report(
    request: DictateReportRequest,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    员工口述日报：后端调用 LLM 将口述原文自动整理为结构化日报并落库。

    - request.raw_content 为员工口述/输入原文（必填）
    - LLM 可用时提取 content / key_progress / risks / next_plan
    - LLM 不可用时降级为 content=raw_content，其余字段留空
    """
    logger.info(
        "POST /api/v1/report/dictate employee=%d date=%s",
        request.employee_id, request.report_date,
    )
    service = ReportService(db)
    report = service.dictate_report(
        employee_id=request.employee_id,
        report_date=request.report_date,
        raw_content=request.raw_content,
        status=request.status,
    )
    return {
        "code": 0,
        "message": "口述日报已生成",
        "data": DailyReportResponse.model_validate(report).model_dump(),
    }

@router.get("/", summary="管理日报查阅 - 列表")
def list_reports(
    employee_id: Optional[int] = Query(None, description="员工ID"),
    start_date: Optional[date] = Query(None, description="起始日期"),
    end_date: Optional[date] = Query(None, description="截止日期"),
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理层按员工 / 日期区间查阅日报列表。"""
    logger.info("GET /api/v1/report employee=%d", employee_id)
    service = ReportService(db)
    reports = service.list_reports(
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "code": 0,
        "message": "success",
        "data": [DailyReportResponse.model_validate(r).model_dump() for r in reports],
    }


@router.get("/summary", summary="管理日报查阅 - 汇总（含 AI 总览）")
def report_summary(
    report_date: date = Query(..., description="汇总日期"),
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理层日报汇总：团队提交情况 + 每人关键进展/风险 + AI 总览文本。"""
    logger.info("GET /api/v1/report/summary date=%s", report_date)
    service = ReportService(db)
    result = service.get_management_summary(report_date=report_date)
    return {
        "code": 0,
        "message": "success",
        "data": result.model_dump(),
    }
