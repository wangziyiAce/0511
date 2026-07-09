"""
教育服务系统 — FastAPI 应用主入口
===========================================
这是整个后端服务的启动文件。FastAPI 应用从这里初始化，
包括: 数据库自动建表、路由注册、生命周期管理。

启动方式（在项目根目录下执行）:
  # 开发模式（修改代码自动重启）:
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  # 生产模式（不自动重启）:
  uvicorn main:app --host 0.0.0.0 --port 8000

  # 指定 workers 数量（利用多核 CPU）:
  uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

API 文档地址（启动后访问）:
  Swagger UI:  http://localhost:8000/docs       （交互式，可以直接在网页上测试接口）
  ReDoc:       http://localhost:8000/redoc       （更适合阅读，排版更美观）

项目架构（分层设计）:
  请求 → routers/（路由层: 定义 URL 和 HTTP 方法）
       → services/（业务层: 核心逻辑、校验、外部调用）
       → models/（数据层: ORM 模型定义）
       → utils/database.py（数据库连接）
       → MySQL

参考文档:
  《教育服务系统_总体架构设计文档_定稿版V1.2》第 7 章 — 后端代码架构
"""

# --- contextlib 标准库 ---
# asynccontextmanager: 把异步生成器函数变成异步上下文管理器，
# 用于 FastAPI 的 lifespan（应用生命周期）管理
from contextlib import asynccontextmanager

# --- FastAPI 框架 ---
from fastapi import FastAPI

# --- 项目内部模块 ---
from config import APP_NAME, APP_VERSION, APP_DEBUG   # 应用元信息
from utils.database import init_db                     # 数据库建表函数


# ============================================================
# 一、应用生命周期管理（lifespan）
# ============================================================
# FastAPI 的 lifespan 是一个异步上下文管理器，管理应用的"出生"到"死亡"。
#
# 启动阶段（yield 之前）:
#   调用 init_db() 创建所有数据库表（已存在的则跳过）。
#   如果将来需要预热缓存、加载配置等，也在这里做。
#
# 运行阶段（yield 期间）:
#   应用正常接受 HTTP 请求。
#
# 关闭阶段（yield 之后）:
#   应用关闭时执行清理工作，如关闭数据库连接池、停止定时任务等。
#   当前 MVP 阶段无需特殊清理（SQLAlchemy 连接池会自动释放）。
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    管理 FastAPI 应用的生命周期: 启动时初始化，关闭时清理。

    参数 app 是 FastAPI 实例（下面创建的那个），由框架自动传入。
    """
    # ===== 应用启动时执行 =====
    # 创建所有 ORM Model 对应的数据库表。
    # 如果表已存在则跳过（CREATE TABLE IF NOT EXISTS）。
    # 不会创建数据库本身，数据库需要提前手动创建。
    init_db()

    # yield 把控制权交给 FastAPI，应用开始接受请求
    yield

    # ===== 应用关闭时执行 =====
    # 这里可以添加清理代码，例如:
    #   - 关闭 Redis 连接
    #   - 停止后台定时任务
    #   - 刷新缓冲区数据
    pass  # MVP 阶段暂无清理需求


# ============================================================
# 二、FastAPI 应用实例
# ============================================================
# 整个应用的核心对象。所有路由注册、中间件、依赖注入都绑定在 app 上。
#
# 参数说明:
#   title   → Swagger 文档页面的标题（会显示在顶部）
#   version → API 版本号（显示在 Swagger 文档中）
#   debug   → 调试模式，true 时显示详细错误信息和交互式调试页面
#   lifespan → 生命周期管理函数（上面定义的）
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    debug=APP_DEBUG,
    lifespan=lifespan,
)


# ============================================================
# 三、健康检查接口
# ============================================================
# 这是一个很简单的端点，用于:
#   1. 确认服务是否在运行（运维监控 / 负载均衡器健康探测）
#   2. 快速验证部署是否成功
#
# 使用:
#   GET http://localhost:8000/health
#   返回: {"status": "ok", "service": "教育服务系统 API", "version": "1.0.0"}
#
# 扩展建议:
#   可以加上数据库连接检查:
#     try: db.execute(text("SELECT 1")); db_status="ok"
#     except: db_status="error"
# ============================================================

@app.get("/health", tags=["系统"])
def health_check():
    """
    服务健康检查端点。返回 200 即表示服务正常运行。

    tags=["系统"] 让这个接口在 Swagger 文档中归入"系统"分组，
    与其他业务接口（用户管理、CRM等）分开显示。
    """
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
    }


# ============================================================
# 四、路由注册（后续按模块逐步启用）
# ============================================================
# 每个 routers/ 下的模块定义了一个 APIRouter 实例（router），
# 在这里通过 app.include_router() 注册到应用上。
#
# 模块分工:
#   routers/user.py    → 用户登录、注册、个人信息管理
#   routers/crm.py     → 客户线索、跟进记录
#   routers/chat.py    → 客服对话
#   routers/profile.py → 客户画像研判
#   routers/student.py → 学生请假、投诉、心理预警
#   routers/report.py  → 报告生成与查询
#   routers/tools.py   → 工具类接口（文件上传、数据导出等）
#
# 当前这些路由模块尚未实现，等对应的 services 和 schemas 开发完成后，
# 取消下面的注释即可启用。
# ============================================================

# --- 路由注册（取消注释即可启用对应的功能模块）---
# from routers import chat, crm, profile, report, student, tools
#
# app.include_router(chat.router,    prefix="/api/v1/chat",    tags=["客服Agent"])
# app.include_router(crm.router,     prefix="/api/v1/crm",     tags=["企业助手"])
# app.include_router(profile.router, prefix="/api/v1/profile", tags=["客户研判"])
# app.include_router(report.router,  prefix="/api/v1/report",  tags=["智能报告"])
# app.include_router(student.router, prefix="/api/v1/student", tags=["学生助手"])
# app.include_router(tools.router,   prefix="/api/v1/tools",   tags=["系统工具"])


# ============================================================
# 五、启动入口（直接运行 python main.py 时触发）
# ============================================================
# 开发时可以直接 python main.py 启动，不需要记 uvicorn 命令行参数。
# 生产环境建议用 uvicorn 命令行启动（支持多 worker）。
# ============================================================

if __name__ == "__main__":
    import uvicorn
    # --- 启动参数说明 ---
    # "main:app"        → 模块名:变量名（本文件的 app 变量）
    # host="0.0.0.0"    → 监听所有网络接口（允许局域网内其他设备访问）
    #                   如果只想本机访问，改为 host="127.0.0.1"
    # port=8000          → HTTP 端口号
    # reload=True        → 代码修改后自动重启（开发神器，生产环境必须关闭）
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
