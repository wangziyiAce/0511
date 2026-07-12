"""客户画像研判路由"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def profile_root():
    return {"module": "客户画像研判", "status": "ok"}
"""
客户研判模块 — API 路由
===========================================
处理客户资料上传、AI 研判、画像规则管理相关的 HTTP 请求。

路由前缀: /api/v1/profile

对应 API 文档:
  - 第 9.1 节  接口清单
  - 第 9.2 节  POST /api/v1/profile/upload
  - 第 9.3 节  POST /api/v1/profile/{source_id}/analyze
  - 第 9.4 节  GET  /api/v1/profile/{source_id}

数据流（需求文档 4.1 节）:
  上传 → customer_source → AI 研判 → customer_profile → 查询结果

异步模式（API 文档第 11 章）:
  POST /upload → 创建 customer_source → 立即返回 source_id
  POST /{source_id}/analyze → 触发后台 AI 研判 → 状态变为 pending
  GET /{source_id} → 轮询 parse_status（pending → success / failed）
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

# --- 公共基础 ---
from models.common import (
    NotFoundError,
    ValidationError,
    get_current_user,
    success_response,
    verify_dify_token,
)

# --- 数据模型 ---
from models.crm import CustomerProfile, CustomerSource
from models.user import SysUser

# --- Schema ---
from schemas import PaginationParams
from schemas.crm import (
    AnalyzeRequest,
    CustomerSourceResponse,
    ProfileRuleCreate,
    ProfileRuleResponse,
    ProfileRuleUpdate,
)

# --- Service ---
from services.profile_service import (
    _extract_file_content,
    _llm_match_analysis,
    create_profile_rule,
    execute_analysis,
    get_profile_detail,
    list_customer_sources,
    list_profile_rules,
    trigger_analysis,
    update_profile_rule,
    upload_customer_source,
)

# --- 数据库 ---
from utils.database import get_db

# ============================================================
# 路由实例
# ============================================================
# prefix="/api/v1/profile" 由 main.py 中 include_router 统一设置
router = APIRouter(tags=["客户研判"])

# 上传配置（从 .env 读取，无硬编码）
from config import UPLOAD_DIR, MAX_UPLOAD_SIZE
# 允许的文件类型
ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".txt", ".docx"}


# ============================================================
# 一、客户资料上传
# ============================================================

@router.post("/profile/upload", summary="上传客户资料")
async def api_upload_customer_source(
    # --- 文件上传（可选）---
    file: Optional[UploadFile] = File(default=None, description="PDF/Excel/TXT 文件（最大 10MB）"),
    # --- 文本内容（可选）---
    content_text: Optional[str] = Form(default=None, description="文本资料（与 file 至少提供一个）"),
    # --- 来源类型（必填）---
    source_type: str = Form(
        ...,
        description="来源类型: text / pdf_resume / excel / import / manual",
    ),
    # --- 鉴权 + 数据库 ---
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传/录入客户资料。

    对应 API 文档第 9.2 节 POST /api/v1/profile/upload。

    Content-Type: multipart/form-data（支持文件 + 文本混合）

    业务规则:
      - file 和 content_text 至少提供一个
      - 文件类型限制: pdf/xlsx/xls/txt/docx
      - 文件大小限制: 10MB
      - 上传成功创建 customer_source 记录，parse_status='pending'

    返回:
      {source_id, source_type, file_name, file_url, parse_status, create_time}
    """
    # 1. 参数校验
    if not file and not content_text:
        raise ValidationError("file 和 content_text 至少提供一个")

    # 2. 处理文件上传
    file_url: Optional[str] = None
    file_name: Optional[str] = None

    if file:
        # --- 文件类型校验 ---
        ext = os.path.splitext(file.filename or "")[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"不支持的文件类型: {ext}，允许的类型: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # --- 文件大小校验 ---
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise ValidationError(f"文件大小超过限制: {MAX_UPLOAD_SIZE // 1024 // 1024}MB")

        # --- 存储文件 ---
        # 按年月分目录存储，防止单目录文件过多
        from datetime import datetime

        date_prefix = datetime.now().strftime("%Y/%m")
        upload_path = os.path.join(UPLOAD_DIR, date_prefix)
        os.makedirs(upload_path, exist_ok=True)

        # 生成唯一文件名（UUID + 原始扩展名），防止覆盖
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(upload_path, unique_name)

        with open(file_path, "wb") as f:
            f.write(content)

        # 构建数据库存储路径（以 /uploads/ 开头的相对路径）
        file_url = f"/{file_path.replace(os.sep, '/')}"
        file_name = file.filename or unique_name

        # --- 提取文件文本内容（对应需求 CR-003）---
        # 提取的文本与手动输入的 content_text 合并，供 AI 研判使用
        extracted = _extract_file_content(file_path, ext)
        if extracted:
            content_text = (content_text or "") + "\n" + extracted

    # 3. 创建来源记录
    source = upload_customer_source(
        db=db,
        source_type=source_type,
        operator_id=current_user.id,  # 记录操作人
        content_text=content_text,
        file_url=file_url,
        file_name=file_name,
    )

    # 4. 返回响应
    return success_response(
        data={
            "source_id": source.id,
            "source_type": source.source_type,
            "file_name": source.file_name,
            "file_url": source.file_url,
            "parse_status": source.parse_status,
            "create_time": source.create_time.isoformat(),
        },
        message="资料已上传",
    )


# ============================================================
# 一-B、客户资料上传（JSON 版本，供 Dify HTTP 节点调用）
# ============================================================


@router.post("/profile/upload-json", summary="上传客户资料(JSON)", dependencies=[Depends(verify_dify_token)])
def api_upload_customer_source_json(
    request: dict = Body(...),  # {"content_text":"...", "source_type":"text", "file_url":null, "file_name":null}
    db: Session = Depends(get_db),
):
    """
    纯 JSON 版本的上传接口，供 Dify Chatflow HTTP 节点调用。

    Dify HTTP 节点只能发送 JSON 请求体，不能发 multipart/form-data。
    文件内容由 Dify 文档提取器处理后，以文本形式传入 content_text 字段。

    请求体:
      {"content_text": "提取的文件文本内容", "source_type": "pdf_resume", "file_url": null, "file_name": "简历.pdf"}
    """
    source = upload_customer_source(
        db=db,
        source_type=request.get("source_type", "text"),
        operator_id=None,  # Dify 调用时无用户上下文
        content_text=request.get("content_text"),
        file_url=request.get("file_url"),
        file_name=request.get("file_name"),
    )
    return success_response(
        data={
            "source_id": source.id,
            "source_type": source.source_type,
            "file_name": source.file_name,
            "file_url": source.file_url,
            "parse_status": source.parse_status,
            "create_time": source.create_time.isoformat(),
        },
        message="资料已上传",
    )


# ============================================================
# 三-B、同步研判（供 Dify Chatflow HTTP 节点调用，直接返回结果）
# ============================================================


@router.post("/profile/analyze-direct", summary="同步研判(供Dify调用)", dependencies=[Depends(verify_dify_token)])
def api_analyze_direct(
    request: dict = Body(...),  # {"source_id": 1, "content_text": "客户文本", "rule_content": {...}}
    db: Session = Depends(get_db),
):
    """
    同步执行客户研判，直接返回 LLM 研判结果。供 Dify Chatflow HTTP 节点调用。

    与 /profile/{source_id}/analyze 的区别：
      - 那个是异步（BackgroundTasks + 轮询），给前端页面用
      - 这个是同步（阻塞等待LLM结果），给 Dify Chatflow 用

    请求体:
      {"source_id": 1, "content_text": "..."}
    """

    source_id = request.get("source_id")
    content_text = request.get("content_text", "")

    # 校验来源记录存在
    source = db.query(CustomerSource).filter_by(id=source_id).first()
    if not source:
        raise NotFoundError(f"客户来源记录不存在: id={source_id}")

    # 准备客户数据 + 调用 LLM 进行语义研判（规则从 .md 文件动态加载）
    customer_data = {
        "name": content_text[:64] if content_text else None,
        "raw_text": content_text,
        "source_type": source.source_type,
        "file_name": source.file_name,
    }

    ai_result = _llm_match_analysis(
        customer_data=customer_data,
        content_text=content_text or (source.raw_content or ""),
    )

    # 保存研判结果
    profile = CustomerProfile(
        customer_name=ai_result.get("customer_name"),
        source_id=source_id,
        background_info=ai_result.get("background_info"),
        match_result=ai_result.get("match_result"),
        matched_product=ai_result.get("matched_product"),
        match_score=ai_result.get("match_score"),
        match_reason=ai_result.get("match_reason"),
        recommended_programs=ai_result.get("recommended_programs"),
        evaluator_id=None,  # Dify 调用时无用户上下文
    )
    db.add(profile)
    source.parse_status = "success"
    source.parse_result = ai_result.get("background_info", {})
    db.commit()

    return success_response(data=ai_result, message="研判完成")


# ============================================================
# 二、客户来源查询
# ============================================================

@router.get("/profile/sources", summary="客户来源列表")
def api_list_customer_sources(
    source_type: str = Query(default=None, description="来源类型筛选"),
    parse_status: str = Query(default=None, description="解析状态筛选: pending/success/failed"),
    operator_id: int = Query(default=None, description="操作人 ID 筛选"),
    pagination: PaginationParams = Depends(),
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    分页查询客户来源列表。

    查询参数:
      ?source_type=pdf_resume  — 只看 PDF 简历
      ?parse_status=pending    — 只看待解析的
      ?page=1&page_size=20    — 分页
    """
    result = list_customer_sources(
        db,
        pagination,
        source_type=source_type,
        parse_status=parse_status,
        operator_id=operator_id,
    )
    return success_response(data=result)


# ============================================================
# 三、画像规则管理（⚠️ 字面路径必须在参数路径 /{source_id} 之前定义）
# ============================================================

@router.get("/profile/rules", summary="画像规则列表")
def api_list_profile_rules(
    product_line: str = Query(default=None, description="产品线筛选"),
    status: int = Query(default=None, description="状态筛选: 1=启用 0=禁用"),
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查询画像研判规则列表。

    查询参数:
      ?product_line=硕博连读  — 只看某产品线的规则
      ?status=1              — 只看启用的规则
    """
    rules = list_profile_rules(db, product_line=product_line, status=status)
    return success_response(data={"items": [r.model_dump() for r in rules]})


@router.post("/profile/rules", summary="创建画像规则")
def api_create_profile_rule(
    request: ProfileRuleCreate,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    创建新的画像研判规则。

    请求体:
      {product_line, rule_name, rule_content, match_prompt?, priority?}

    rule_content 示例:
      {conditions: {education: ["本科"], age_range: [22,35]}, weight: {education: 0.3, language: 0.3}}
    """
    rule = create_profile_rule(db, request)
    return success_response(
        data=ProfileRuleResponse.model_validate(rule).model_dump(),
        message="创建成功",
    )


@router.put("/profile/rules/{rule_id}", summary="更新画像规则")
def api_update_profile_rule(
    rule_id: int,
    request: ProfileRuleUpdate,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    更新画像研判规则（部分更新）。

    只传需要修改的字段，未传字段保持不变。
    """
    rule = update_profile_rule(db, rule_id, request)
    return success_response(
        data=ProfileRuleResponse.model_validate(rule).model_dump(),
        message="更新成功",
    )


# ============================================================
# 四、研判结果查询（参数路径，必须在字面路径之后）
# ============================================================

@router.get("/profile/{source_id}", summary="查询研判结果")
def api_get_profile_detail(
    source_id: int,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查询客户研判完整详情（来源 + 画像联合查询）。

    对应 API 文档第 9.4 节 GET /api/v1/profile/{source_id}。

    前端轮询模式:
      1. POST /upload → 获得 source_id
      2. POST /{source_id}/analyze → 触发研判
      3. GET /{source_id}（每隔 2 秒轮询一次）
         - parse_status=pending → 继续等待
         - parse_status=success → 展示匹配结果
         - parse_status=failed  → 展示错误信息
    """
    detail = get_profile_detail(db, source_id)
    return success_response(data=detail.model_dump())


# ============================================================
# 五、触发 AI 研判
# ============================================================

@router.post("/profile/{source_id}/analyze", summary="触发 AI 研判")
def api_trigger_analysis(
    source_id: int,
    request: AnalyzeRequest = AnalyzeRequest(),
    background_tasks: BackgroundTasks = None,  # FastAPI 注入
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    触发 AI 画像研判（异步任务）。

    对应 API 文档第 9.3 节。

    流程:
      1. 校验来源记录存在
      2. 在请求事务中更新状态为 pending
      3. 提交后台任务 → 独立 Session 中执行 AI 调用
      4. 立即返回 source_id（不等待 AI 完成）

    后续通过 GET /profile/{source_id} 轮询结果。
    """
    # 1. 同步校验 + 更新状态为 pending
    result = trigger_analysis(
        db=db,
        source_id=source_id,
        evaluator_id=current_user.id,
        rule_id=request.rule_id,
    )

    # 2. 提交后台异步任务（独立 Session，事务外调用 AI）
    background_tasks.add_task(
        execute_analysis,
        source_id=source_id,
        evaluator_id=current_user.id,
        rule_id=request.rule_id,
    )

    return success_response(data=result, message="研判任务已启动")
