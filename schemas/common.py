"""通用 Pydantic Schema - 分页、日期等"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class PaginationParams(BaseModel):
    """通用分页参数"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return min(self.page_size, 100)


class DateRangeParams(BaseModel):
    """日期范围查询"""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
