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
    """
    向 FastAPI 应用注册所有业务路由模块。

    参数:
        app: FastAPI 应用实例

    注册模式:
        app.include_router(router, prefix="/api/v1/xxx", tags=["分组名"])

    分组说明:
        - "基础设施": 登录认证、用户管理、角色、组织架构
        - "客户研判": 客户资料上传、AI 画像研判、画像规则管理
    """
    # 注意: tools（基础设施/auth）路由已在 main.py 中注册，此处不重复
    # ========================================
    # 客户研判模块
    # ========================================
    from routers.profile import router as profile_router

    app.include_router(
        profile_router,
        prefix="/api/v1",
        tags=["客户研判"],
    )

    # ========================================
    # ★ 后续模块扩展示例（取消注释即可启用）
    # ========================================
    # from routers.crm import router as crm_router
    # app.include_router(crm_router, prefix="/api/v1", tags=["企业助手"])
    #
    # from routers.student import router as student_router
    # app.include_router(student_router, prefix="/api/v1", tags=["学生助手"])
    #
    # from routers.chat import router as chat_router
    # app.include_router(chat_router, prefix="/api/v1", tags=["客服Agent"])
    #
    # from routers.report import router as report_router
    # app.include_router(report_router, prefix="/api/v1", tags=["智能报告"])
