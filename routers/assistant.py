"""
企业智能助手 — API 路由
===========================================
处理员工与智能助手的对话交互。

路由前缀: /api/v1/assistant

接口清单:
  POST /chat                   发送消息，助手回复
  GET  /sessions               查询会话列表
  GET  /sessions/{id}/messages 查询会话历史

使用场景:
  员工在聊天框输入自然语言，助手识别意图后：
    - 查询数据（NL2SQL）
    - 执行操作（NL2API）
    - 或闲聊回复
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.common import get_current_user
from models.user import SysUser
from schemas.crm import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantMessageResponse,
    AssistantSessionResponse,
)
from services.assistant_service import AssistantService
from utils.database import get_db

router = APIRouter(tags=["智能助手"])


@router.post(
    "/assistant/chat",
    summary="发送消息",
    description="""
与智能助手对话。

**支持的意图类型：**
- 查询数据（NL2SQL）：如"有多少个联系中的客户"、"最近一周新增了几个客户"
- 执行操作（NL2API）：如"帮我录入新客户王五"、"更新客户3号的状态为联系中"
- 闲聊：其他问题

**首次对话：** 不传 session_id，后端自动创建新会话
**多轮对话：** 传入之前返回的 session_id，保持上下文
""",
)
def chat(
    request: AssistantChatRequest,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发送消息给智能助手。"""
    service = AssistantService(db)
    response = service.chat(request, current_user.id)
    return {"code": 0, "message": "success", "data": response.model_dump()}


@router.get(
    "/assistant/sessions",
    summary="会话列表",
    description="查询当前员工的智能助手会话列表。",
)
def list_sessions(
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询员工的会话列表。"""
    service = AssistantService(db)
    sessions = service.list_sessions(current_user.id)
    return {
        "code": 0,
        "message": "success",
        "data": {"items": [s.model_dump() for s in sessions]},
    }


@router.get(
    "/assistant/sessions/{session_id}/messages",
    summary="会话历史",
    description="查询某个会话的消息历史记录。",
)
def list_messages(
    session_id: str,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询会话消息历史。"""
    service = AssistantService(db)
    messages = service.list_messages(session_id, current_user.id)
    return {
        "code": 0,
        "message": "success",
        "data": {"items": [m.model_dump() for m in messages]},
    }
