"""
教育服务系统 — 路由注册汇总
===========================================
所有业务模块的路由在这里统一注册到 FastAPI 应用。

工作方式:
  1. 各 routers/*.py 文件定义 APIRouter 实例（router）
  2. main.py 中: from routers import register_routers
  3. register_routers(app) 一次性注册所有路由

路由分组（对应 API 文档第 15.2 节）:
  /api/v1/auth/*        基础设施 — 登录、用户、角色、组织
  /api/v1/profile/*     客户研判 — 资料上传、AI 研判、画像规则
  （后续模块按需扩展）

使用方式（在 main.py 中）:
  from routers import register_routers
  register_routers(app)

参考文档:
  《教育服务系统_API接口设计规范文档_V1.2》
  - 第 1.4 节  数据库表 → 接口模块映射
  - 第 15.2 节 路由标签分组
"""

from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """按唯一入口装配已确认的业务模块。

    ``main.py`` 只调用本函数，避免不同启动入口各自 ``include_router`` 后出现
    漏接口或同一路径重复注册。认证只挂载 ``routers.tools``：旧的 ``routers.auth``
    保留源码供迁移参考，但不注册，避免两个 ``/auth/login`` 返回不同数据结构。

    参数:
        app: 已创建的 FastAPI 应用，所有路由会写入它的 OpenAPI 文档和请求分发表。
    """
    from routers.chat import router as chat_router
    from routers.client import router as client_router
    from routers.crm import crm_router, employee_router
    from routers.assistant import router as assistant_router
    from routers.daily_report import router as daily_report_router
    from routers.profile import router as profile_router
    from routers.report import router as report_router
    from routers.report_action import router as report_action_router
    from routers.report_assistant import router as report_assistant_router
    from routers.report_data import router as report_data_router
    from routers.report_schedule import router as report_schedule_router
    from routers.student import router as student_router
    from routers.student_chat import router as student_chat_router
    from routers.tools import router as tools_router

    # tools.py 是当前唯一认证实现，响应统一为 {code, message, data}。
    app.include_router(tools_router, prefix="/api/v1", tags=["基础设施"])
    app.include_router(crm_router, prefix="/api/v1/crm", tags=["企业助手"])
    app.include_router(employee_router, prefix="/api/v1/employee", tags=["员工日报"])
    app.include_router(assistant_router, prefix="/api/v1", tags=["智能助手"])

    # chat 路由自身已声明 /api/v1 前缀；再次添加会得到错误的 /api/v1/api/v1 路径。
    app.include_router(chat_router)
    app.include_router(client_router)
    app.include_router(profile_router, prefix="/api/v1", tags=["客户研判"])
    app.include_router(daily_report_router, prefix="/api/v1/report", tags=["智能日报"])
    app.include_router(report_router, prefix="/api/v1/reports", tags=["智能报告"])
    app.include_router(report_assistant_router, prefix="/api/v1/reports/assistant", tags=["智能报告助手"])
    app.include_router(report_schedule_router, prefix="/api/v1/report-schedules", tags=["报告计划"])
    app.include_router(report_action_router, prefix="/api/v1/report-actions", tags=["报告行动"])
    app.include_router(report_data_router, prefix="/api/v1/report-data", tags=["报告数据"])
    app.include_router(student_router, prefix="/api/v1/student", tags=["学生服务"])
    app.include_router(student_chat_router, prefix="/api/v1", tags=["学生智能助手"])
