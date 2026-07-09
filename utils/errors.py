"""
教育服务系统 - 统一错误码与异常类
严格对齐《API 接口设计规范文档 V1.2》第 3 章

错误码分段:
  0          — 成功
  40001-40099 — 参数校验错误
  40101-40199 — 认证错误
  40301-40399 — 权限错误
  40401-40499 — 资源不存在
  40901-40999 — 业务冲突
  42201-42299 — 业务规则校验失败
  50001-50099 — 服务器内部错误
  50201-50299 — 外部服务调用失败
"""
from fastapi import HTTPException
from typing import Any, Optional


# ==================== 统一业务异常基类 ====================

class BusinessError(HTTPException):
    """统一业务异常（对齐文档 3.3 节）"""

    def __init__(
        self,
        code: int,
        message: str,
        status_code: int = 400,
        data: Any = None,
    ):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "data": data},
        )


# ==================== 资源不存在 (40401-40499) ====================

class NotFoundError(BusinessError):
    """资源不存在（40401）"""

    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=40401, message=message, status_code=404)


class ReferenceNotFoundError(BusinessError):
    """⭐ 逻辑外键引用不存在（40402，V1.1 新增）"""

    def __init__(self, entity: str, id_value: int):
        super().__init__(
            code=40402,
            message=f"{entity}不存在: id={id_value}",
            status_code=404,
        )


# ==================== 业务冲突 (40901-40999) ====================

class ConflictError(BusinessError):
    """业务冲突（40901）"""

    def __init__(self, message: str):
        super().__init__(code=40901, message=message, status_code=409)


class StateError(BusinessError):
    """状态不允许操作（40902）"""

    def __init__(self, message: str):
        super().__init__(code=40902, message=message, status_code=422)


# ==================== 认证错误 (40101-40199) ====================

class AuthError(BusinessError):
    """认证失败（40101-40103）"""

    def __init__(self, code: int = 40101, message: str = "未登录"):
        super().__init__(code=code, message=message, status_code=401)


# ==================== 权限错误 (40301-40399) ====================

class ForbiddenError(BusinessError):
    """无权限访问（40301）"""

    def __init__(self, message: str = "无权限访问"):
        super().__init__(code=40301, message=message, status_code=403)


class DataAccessError(BusinessError):
    """数据越权（40302）"""

    def __init__(self, message: str = "数据越权"):
        super().__init__(code=40302, message=message, status_code=403)


# ==================== 参数校验错误 (40001-40099) ====================

class ValidationError(BusinessError):
    """参数校验失败（40001）"""

    def __init__(self, message: str = "参数校验失败"):
        super().__init__(code=40001, message=message, status_code=400)


# ==================== 业务规则校验失败 (42201-42299) ====================

class BusinessRuleError(BusinessError):
    """业务规则校验失败（42201-42205）"""

    def __init__(self, code: int = 42201, message: str = "业务规则校验失败"):
        super().__init__(code=code, message=message, status_code=422)


# ==================== 外部服务错误 (50201-50299) ====================

class ExternalServiceError(BusinessError):
    """外部服务调用失败（50201-50202）"""

    def __init__(self, code: int = 50201, message: str = "外部服务调用失败"):
        super().__init__(code=code, message=message, status_code=502)
