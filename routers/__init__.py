"""Central router registry for all education service modules."""

from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """Register each router exactly once with its established prefix."""

    from routers.assistant import router as assistant_router
    from routers.chat import router as chat_router
    from routers.crm import crm_router, employee_router
    from routers.profile import router as profile_router
    from routers.report import router as report_router
    from routers.student import router as student_router
    from routers.student_chat import router as student_chat_router
    from routers.tools import router as tools_router

    app.include_router(tools_router, prefix="/api/v1", tags=["基础设施"])
    app.include_router(profile_router, prefix="/api/v1", tags=["客户研判"])
    app.include_router(crm_router, prefix="/api/v1/crm", tags=["企业助手"])
    app.include_router(employee_router, prefix="/api/v1/employee", tags=["员工日报"])
    app.include_router(assistant_router, prefix="/api/v1", tags=["智能助手"])
    app.include_router(student_router, prefix="/api/v1/student", tags=["学生智能助手"])
    app.include_router(student_chat_router, prefix="/api/v1")
    app.include_router(report_router, prefix="/api/v1/report", tags=["智能报告"])
    app.include_router(chat_router)
