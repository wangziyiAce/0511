"""统一响应格式工具"""
from typing import Any, Optional


def success_response(data: Any = None, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def paginated_response(items: list, total: int, page: int, page_size: int) -> dict:
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
    return {"code": code, "message": message, "data": None}
