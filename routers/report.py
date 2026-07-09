"""智能报告路由"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def report_root():
    return {"module": "智能报告", "status": "ok"}
