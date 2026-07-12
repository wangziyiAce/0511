"""
教育服务系统 - 通用 Pydantic Schema
严格对齐《API 接口设计规范文档 V1.2》第 2.3/2.5/12 节

统一响应格式: {code, message, data}
"""
from pydantic import BaseModel, Field
from typing import Optional, Any, Generic, TypeVar
from datetime import date, datetime

T = TypeVar("T")


# ==================== 统一响应模型 ====================

class APIResponse(BaseModel, Generic[T]):
    """统一成功响应（单对象 / 列表 / 分页通用）"""

    code: int = Field(default=0, description="状态码，0=成功")
    message: str = Field(default="success", description="提示信息")
    data: Optional[T] = Field(default=None, description="响应数据")


class ErrorResponse(BaseModel):
    """统一错误响应"""

    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误描述")
    data: None = Field(default=None, description="错误时 data 为 null")


# ==================== 分页模型 ====================

class PaginationParams(BaseModel):
    """通用分页参数（对齐文档 12.1 节）"""

    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数，最大 100")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedData(BaseModel, Generic[T]):
    """分页响应数据（对齐文档 2.3 节）"""

    items: list[T] = Field(default_factory=list, description="数据列表")
    total: int = Field(default=0, description="总条数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页条数")


class CursorPaginationParams(BaseModel):
    """⭐ 游标分页参数（深分页场景，对齐文档 12.2 节）"""

    cursor: Optional[int] = Field(default=None, description="游标 ID")
    limit: int = Field(default=20, ge=1, le=100, description="每页条数")


class CursorPaginatedData(BaseModel, Generic[T]):
    """⭐ 游标分页响应数据（对齐文档 2.3 节）"""

    items: list[T] = Field(default_factory=list, description="数据列表")
    next_cursor: Optional[int] = Field(default=None, description="下一页游标")
    has_more: bool = Field(default=False, description="是否还有更多数据")


# ==================== 日期范围 & 排序 ====================

class DateRangeParams(BaseModel):
    """日期范围查询参数"""

    start_date: Optional[date] = Field(default=None, description="起始日期")
    end_date: Optional[date] = Field(default=None, description="截止日期")


class SortParams(BaseModel):
    """排序参数（对齐文档 12.3 节）"""

    sort_by: str = Field(default="create_time", description="排序字段")
    sort_order: str = Field(default="desc", description="排序方向 asc/desc")


# ==================== 工具函数 ====================

def success_response(
    data: Any = None,
    message: str = "success",
    code: int = 0,
) -> dict:
    """快速构建成功响应字典"""
    return {"code": code, "message": message, "data": data}


def paginated_response(
    items: list,
    total: int,
    page: int,
    page_size: int,
) -> dict:
    """快速构建分页响应字典"""
    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


def error_response(code: int, message: str) -> dict:
    """快速构建错误响应字典"""
    return {"code": code, "message": message, "data": None}
