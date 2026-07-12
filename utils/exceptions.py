"""统一业务异常类 — 复用 models.common 中的权威定义，避免重复类导致异常处理器漏捕获。

所有模块应只通过 models.common.BusinessError 抛出业务异常，
main.py 的 business_error_handler 才能统一拦截并返回 {code, message, data}。
"""

from models.common import BusinessError, NotFoundError, ConflictError  # noqa: F401


class ReferenceNotFoundError(BusinessError):
    """逻辑外键引用不存在 (404)"""
    def __init__(self, entity: str, id_value: int):
        super().__init__(
            code=40402,
            message=f"{entity}不存在: id={id_value}",
            status_code=404,
        )


class StateError(BusinessError):
    """状态不允许操作 (422)"""
    def __init__(self, message: str):
        super().__init__(code=40902, message=message, status_code=422)
