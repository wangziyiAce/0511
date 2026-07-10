"""教育服务系统 - FastAPI 主入口"""
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from utils.exceptions import BusinessError
from utils.response import error_response
from routers import chat
from config import settings

app = FastAPI(
    title="教育服务系统 API",
    description="""
## 教育服务系统（留学服务智能平台）API 文档

基于 FastAPI + Dify + MySQL 的 AI 驱动教育服务系统。

⭐ 数据库无物理外键，所有关联关系通过应用层维护。

### 客服 Agent 模块
- **课程**：课程查询
- **活动**：活动查询、活动报名
- **会话**：会话管理、消息记录
    """,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理：所有错误都收敛为 API 规范要求的 {code,message,data}。
@app.exception_handler(BusinessError)
async def business_error_handler(request, exc: BusinessError):
    # Service 层主动抛出的业务异常已经带有准确的业务错误码。
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail if isinstance(exc.detail, dict)
        else error_response(50001, str(exc.detail)),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    # 兼容 FastAPI/依赖项抛出的 HTTPException，避免响应外层出现 detail。
    if isinstance(exc.detail, dict) and {"code", "message"}.issubset(exc.detail):
        content = {**exc.detail, "data": exc.detail.get("data")}
    else:
        content = error_response(exc.status_code, str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    # Pydantic 参数校验失败统一映射到参数错误码，HTTP 状态仍保持 422。
    return JSONResponse(
        status_code=422,
        content=error_response(40001, f"参数校验失败: {exc.errors()}"),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    # 未预期异常不向调用方暴露堆栈，统一包装为服务器内部错误。
    return JSONResponse(
        status_code=500,
        content=error_response(50001, f"服务器内部错误: {str(exc)}"),
    )


# 注册客服 Agent 模块路由
app.include_router(chat.router)


# # 健康检查
# @app.get("/api/v1/health", tags=["基础设施"])
# def health_check():
#     return {
#         "code": 0,
#         "message": "success",
#         "data": {
#             "status": "healthy",
#             "version": settings.APP_VERSION,
#             "module": "客服 Agent",
#         },
#     }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
