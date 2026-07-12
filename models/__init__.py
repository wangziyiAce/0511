"""ORM model exports and registry."""

from models.chat import ChatMessage, ChatSession, CourseProject, EventLecture, EventRegistration
from models.user import SysOrganization, SysRole, SysUser


def load_all_models() -> None:
    """Import every ORM module so all tables share one metadata registry."""

    import models.chat  # noqa: F401
    import models.crm  # noqa: F401
    import models.knowledge  # noqa: F401
    import models.report  # noqa: F401
    import models.student  # noqa: F401
    import models.user  # noqa: F401


__all__ = [
    "SysRole", "SysUser", "SysOrganization", "CourseProject",
    "EventLecture", "EventRegistration", "ChatSession", "ChatMessage",
    "load_all_models",
]
