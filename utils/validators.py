"""应用层逻辑外键校验装饰器 - 对齐数据库 V2.1 第 5 章"""
from functools import wraps
from sqlalchemy.orm import Session
from utils.exceptions import ReferenceNotFoundError


def validate_entity_exists(entity_model, field_name: str, error_entity_name: str):
    """校验逻辑外键指向的实体是否存在"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            entity_id = kwargs.get(field_name)
            if entity_id is not None:
                session: Session = kwargs.get("db")
                if session is None:
                    raise RuntimeError("函数必须包含 db 参数")
                exists = session.query(
                    session.query(entity_model).filter_by(id=entity_id).exists()
                ).scalar()
                if not exists:
                    raise ReferenceNotFoundError(error_entity_name, entity_id)
            return func(*args, **kwargs)
        return wrapper
    return decorator
