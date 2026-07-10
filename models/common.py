"""数据库 ORM 模型基类 - 统一时间戳"""
from sqlalchemy import BigInteger, Column, DateTime, Integer, func
from utils.database import Base


# 生产库是 MySQL，主键按规范使用 BIGINT；测试规范使用 SQLite 内存库，
# SQLite 只有 INTEGER PRIMARY KEY 才会触发自增，因此这里做方言级兼容。
BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    """统一时间戳混入类，供需要 create_time/update_time 的业务表复用。"""
    create_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    update_time = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
