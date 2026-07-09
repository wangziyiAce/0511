"""
教育服务系统 - FastAPI 应用入口
海外留学教育平台 — 客服 Agent · 客户研判 · CRM · 学生服务 · 智能报告

严格对齐《API 接口设计规范文档 V1.2》：
  - 第 15 章 Swagger 文档配置
  - 第 4.4 节健康检查格式
  - 第 1.2 节接口设计原则（/api/v1 前缀 + 统一响应格式）
  - 第 13 章双 Token 鉴权机制（用户 JWT + Dify Service Token）
"""
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from config import get_settings
from schemas.common import success_response

settings = get_settings()


# ==================== 应用生命周期 ====================
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用启动 & 关闭事件"""
    # ---- 启动 ----
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    print(f"📦 数据库: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    print(f"🔧 DEBUG 模式: {settings.DEBUG}")
    print(f"📖 Swagger 文档: http://localhost:8000/docs")
    print(f"📖 ReDoc 文档:   http://localhost:8000/redoc")

    from utils.database import check_db_connection
    db_ok = await check_db_connection()
    if db_ok:
        print("✅ 数据库连接正常")
    else:
        print("⚠️  数据库连接失败，请检查 .env 配置")

    yield

    # ---- 关闭 ----
    print("👋 应用正在关闭...")
    from utils.database import dispose_engine
    await dispose_engine()
    print("🔌 数据库连接池已释放")


# ==================== FastAPI 实例 ====================
app = FastAPI(
    title=settings.APP_NAME,
    description="""
## 教育服务系统（留学服务智能平台）API 文档

基于 **FastAPI + Dify + MySQL** 的 AI 驱动教育服务系统。

⭐ **数据库无物理外键**，所有关联关系通过应用层维护。

### 模块概览
| 模块 | 说明 |
|------|------|
| 🔐 **认证** | 用户登录与 JWT 鉴权 |
| 💬 **客服 Agent** | 课程查询、活动报名、在线会话 |
| 📋 **企业助手** | CRM 客户管理、日报提交与汇总 |
| 🎓 **学生助手** | 请假审批、投诉处理、心理预警、申请进度 |
| 📊 **智能报告** | 报告生成与异步查询 |
| 🎯 **客户研判** | 资料上传与 AI 画像研判 |

### 鉴权方式
- **用户接口** → `Authorization: Bearer {JWT Token}`
- **Dify 白名单接口** → `Authorization: Bearer {DIFY_SERVICE_TOKEN}`
    """,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# ==================== CORS 中间件 ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== OpenAPI 自定义（双 Token 认证方案） ====================
def custom_openapi():
    """自定义 OpenAPI schema，添加双 Token 认证方式（对齐文档 15.1 节）"""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "用户 JWT Token（24 小时有效）",
        },
        "DifyServiceToken": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Service Token",
            "description": "Dify HTTP 节点调用 FastAPI 白名单接口的服务令牌（固定值）",
        },
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# ==================== 注册路由 ====================
# 路由标签严格对齐文档 15.2 节 + 1.4 节表→接口模块映射
# 注：后续按模块拆分更多 router（courses/events/employee/auth），当前为 MVP 骨架
from routers import chat, crm, profile, report, student, tools

app.include_router(chat.router,    prefix="/api/v1/chat",     tags=["💬 客服 Agent"])
app.include_router(crm.router,     prefix="/api/v1/crm",      tags=["📋 企业助手 - CRM"])
app.include_router(student.router, prefix="/api/v1/student",  tags=["🎓 学生助手"])
app.include_router(report.router,  prefix="/api/v1/reports",  tags=["📊 智能报告"])
app.include_router(profile.router, prefix="/api/v1/profile",  tags=["🎯 客户研判"])
app.include_router(tools.router,   prefix="/api/v1/tools",    tags=["🔧 系统工具"])


# ==================== 根路径 ====================
@app.get("/", tags=["基础设施"], include_in_schema=False)
async def root():
    """项目根路径 — 返回基本信息"""
    return success_response(data={
        "project": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    })


# ==================== 健康检查 ====================
@app.get("/api/v1/health", tags=["基础设施"], summary="健康检查")
async def health_check():
    """
    健康检查接口（对齐文档 4.4 节）

    返回数据库和 Dify 连通性状态。
    """
    from utils.database import check_db_connection
    db_ok = await check_db_connection()

    # Dify 连通性简单检测（仅尝试 DNS 解析或跳过）
    dify_ok = bool(settings.DIFY_API_KEY)

    return success_response(data={
        "status": "healthy" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "database": "connected" if db_ok else "disconnected",
        "dify": "configured" if dify_ok else "not_configured",
    })


# ==================== 全局异常处理器 ====================
from fastapi import Request
from fastapi.responses import JSONResponse
from utils.errors import BusinessError
from schemas.common import error_response


@app.exception_handler(BusinessError)
async def business_error_handler(_request: Request, exc: BusinessError):
    """统一业务异常 → 标准错误响应"""
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": 50001, "message": str(exc.detail), "data": None}
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(422)
async def validation_exception_handler(_request: Request, exc):
    """Pydantic 请求体验证失败 → 40001"""
    errors = exc.errors() if hasattr(exc, "errors") else []
    messages = []
    for err in errors:
        field = " → ".join(str(loc) for loc in err.get("loc", []))
        messages.append(f"{field}: {err.get('msg', '')}")
    detail_msg = "; ".join(messages) if messages else "参数校验失败"
    return JSONResponse(
        status_code=400,
        content=error_response(40001, detail_msg),
    )


@app.exception_handler(500)
async def internal_error_handler(_request: Request, _exc: Exception):
    """未预期异常 → 50001"""
    return JSONResponse(
        status_code=500,
        content=error_response(50001, "服务器内部错误"),
    )
