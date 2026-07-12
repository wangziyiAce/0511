"""ORM 模型统一注册入口。

数据库初始化层调用 ``load_all_models`` 后再读取 ``Base.metadata``，确保用户、
聊天、CRM、学生与报告模块使用同一份 ORM 元数据。
"""
from models.user import SysUser
from models.chat import (
    ChatMessage,
    ChatSession,
    CourseProject,
    EventLecture,
    EventRegistration,
)


def load_all_models() -> None:
    """加载全部 ORM 模型模块，让数据库层能统一发现每一张业务表。"""

    # 学生模块先注册共享表，报告模块随后仅引用其模型，避免同名表重复映射。
    import models.chat  # noqa: F401
    import models.crm  # noqa: F401
    import models.student  # noqa: F401
    import models.report  # noqa: F401
    import models.user  # noqa: F401


__all__ = [
    "SysUser",
    "CourseProject",
    "EventLecture",
    "EventRegistration",
    "ChatSession",
    "ChatMessage",
    "load_all_models",
]
