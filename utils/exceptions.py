"""统一业务异常类 - 对齐 API V1.2 错误码体系"""
from fastapi import HTTPException


class BusinessError(HTTPException):
    """统一业务异常"""
    def __init__(self, code: int, message: str, status_code: int = 400):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "data": None},
        )


class NotFoundError(BusinessError):
    """资源不存在 (404)"""
    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=40401, message=message, status_code=404)


class ReferenceNotFoundError(BusinessError):
    """逻辑外键引用不存在 (404)"""
    def __init__(self, entity: str, id_value: int):
        super().__init__(
            code=40402,
            message=f"{entity}不存在: id={id_value}",
            status_code=404,
        )


class ConflictError(BusinessError):
    """业务冲突 (409)"""
    def __init__(self, message: str):
        super().__init__(code=40901, message=message, status_code=409)


class StateError(BusinessError):
    """状态不允许操作 (422)"""
    def __init__(self, message: str):
        super().__init__(code=40902, message=message, status_code=422)
