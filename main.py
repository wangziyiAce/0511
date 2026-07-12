"""教育服务系统 FastAPI 统一入口。

该文件合并 GitHub 最新业务模块与本地客服 Agent 模块，负责应用生命周期、
统一异常处理、健康检查和全部业务路由注册。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import APP_DEBUG, APP_NAME, APP_VERSION
from models.common import BusinessError as CommonBusinessError
from routers.assistant import router as assistant_router
from routers.chat import router as chat_router
from routers.crm import crm_router, employee_router
from routers.profile import router as profile_router
from routers.report import router as report_router
from routers.student import router as student_router
from routers.student_chat import router as student_chat_router
from routers.tools import router as tools_router
from services.crm_service import BizError
from utils.database import init_db
from utils.exceptions import BusinessError as AgentBusinessError


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用启动时初始化已注册模型，关闭时交还控制权。"""

    init_db()
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    debug=APP_DEBUG,
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)


# GitHub CRM 模块使用的业务异常。
@app.exception_handler(BizError)
def biz_error_handler(_, exc: BizError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


def _business_error_response(_, exc):
    """兼容公共模块与客服 Agent 的统一业务异常响应。"""

    return JSONResponse(status_code=exc.status_code, content=exc.detail)


app.add_exception_handler(CommonBusinessError, _business_error_response)
if AgentBusinessError is not CommonBusinessError:
    app.add_exception_handler(AgentBusinessError, _business_error_response)


@app.get("/health", tags=["系统"])
def health_check():
    """服务健康检查，不访问数据库。"""

    return {"status": "ok", "service": APP_NAME, "version": APP_VERSION}


# ============================================================
# 路由注册：GitHub 业务模块 + 本地客服 Agent 模块
# ============================================================

# 基础设施：登录、用户、角色、组织等。
app.include_router(tools_router, prefix="/api/v1", tags=["基础设施"])

# 客户研判：资料上传、画像规则、AI 研判。
app.include_router(profile_router, prefix="/api/v1", tags=["客户研判"])

# 企业助手与员工日报。
app.include_router(crm_router, prefix="/api/v1/crm", tags=["企业助手"])
app.include_router(employee_router, prefix="/api/v1/employee", tags=["员工日报"])
app.include_router(assistant_router, prefix="/api/v1", tags=["智能助手"])

# 学生智能助手与学生对话。
app.include_router(student_router, prefix="/api/v1/student", tags=["学生智能助手"])
app.include_router(student_chat_router, prefix="/api/v1")

# 智能报告。
app.include_router(report_router, prefix="/api/v1/report", tags=["智能报告"])

# 客服 Agent：课程、活动、活动报名、客服会话与消息。
# chat_router 自身已经声明 prefix="/api/v1"，此处不再叠加前缀。
app.include_router(chat_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
