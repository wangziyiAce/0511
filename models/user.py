"""客服Agent - 用户 ORM 模型（客服 Agent 模块依赖 sys_user）"""
from sqlalchemy import Column, BigInteger, String, Enum
from utils.database import Base
from models.common import BigIntPrimaryKey, TimestampMixin


class SysUser(Base, TimestampMixin):
    """统一用户表的最小 ORM 映射，供客服 Agent 做 user_id 逻辑外键校验。"""

    __tablename__ = "sys_user"

    id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True, comment="主键")
    username = Column(String(64), nullable=False, comment="登录账号")
    password_hash = Column(String(255), nullable=False, comment="bcrypt 密码哈希")
    real_name = Column(String(64), nullable=False, comment="真实姓名")
    user_type = Column(
        Enum("student", "employee", "admin", name="user_type_enum"),
        nullable=False,
        comment="用户类型",
    )
    role_id = Column(BigInteger, default=None, comment="关联角色ID → sys_role（逻辑关联）")
    department = Column(String(128), default=None, comment="所属部门/院系")
    contact_info = Column(String(128), default=None, comment="联系方式（手机/邮箱）")
    avatar_url = Column(String(512), default=None, comment="头像URL")
    status = Column(
        Enum("normal", "disabled", name="user_status_enum"),
        nullable=False,
        default="normal",
        comment="账号状态",
    )

    def __init__(self, **kwargs):
        # 测试/历史脚本可能仍使用 role 和 0/1 状态；入库前映射为规范字段。
        role = kwargs.pop("role", None)
        if role is not None and "user_type" not in kwargs:
            kwargs["user_type"] = role
        if "real_name" not in kwargs and "username" in kwargs:
            kwargs["real_name"] = kwargs["username"]
        if kwargs.get("status") == 1:
            kwargs["status"] = "normal"
        elif kwargs.get("status") == 0:
            kwargs["status"] = "disabled"
        super().__init__(**kwargs)
