"""
教育服务系统 — 公共基础设施模块
===========================================
这个模块是整个项目的"公共底盘"，提供以下共享能力：

  1. 统一异常类体系    — 严格对应 API 文档第 3 章错误码
  2. 逻辑外键校验装饰器  — 对应 API 文档第 14.2 节，数据库文档第 5 章
  3. JWT Token 工具     — 对应 API 文档第 13.2 节
  4. 密码哈希工具       — bcrypt，对应数据库文档第 9.2 节
  5. 鉴权依赖注入       — get_current_user / require_role
  6. 统一响应格式工具    — 对应 API 文档第 2.3 节

为什么这些东西放在 models/common.py 而不是 utils/ 下？
  - 异常类描述的是"数据出了什么问题"，本质是模型层语言
  - 校验器验证的是 Model 引用是否存在，和模型紧密耦合
  - JWT/密码是全局基础设施，与各层平等，放在唯一的公共文件里
  - 一个 import 即可获取全部共享能力：from models.common import ...

使用示例:
  from models.common import (
      get_current_user,      # FastAPI 依赖注入 → 获取当前登录用户
      NotFoundError,         # 抛出"资源不存在"异常
      success_response,      # 构造统一成功响应
      hash_password,         # 注册时加密密码
  )

参考文档:
  《教育服务系统_API接口设计规范文档_V1.2》
  - 第 2.3 节  统一响应格式
  - 第 3 章    统一错误码体系
  - 第 13 章   安全与鉴权规范
  - 第 14 章   应用层数据一致性保障
  《教育服务系统_数据库设计规范文档_V2.1》
  - 第 5 章    外键策略
  - 第 9 章    数据安全与权限隔离
"""

import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

# --- JWT ---
# python-jose 实现了 JWT 标准（RFC 7519），用于签发和验证 Token
from jose import JWTError, jwt

# --- 密码加密 ---
# bcrypt 是目前公认最安全的密码哈希算法之一，自带盐值防彩虹表
import bcrypt

# --- FastAPI ---
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# --- SQLAlchemy ---
from sqlalchemy import BigInteger, Column, DateTime, func
from sqlalchemy.orm import Session, declared_attr

# --- 项目内部 ---
from config import SECRET_KEY, BCRYPT_COST, ACCESS_TOKEN_EXPIRE_MINUTES
from utils.database import Base, get_db

from sqlalchemy import BigInteger, Column, DateTime


# ============================================================
# 共享 ORM 基类（供客服 Agent / 企业助手等模块共用）
# ============================================================

# 统一 BIGINT 类型别名（供其他模块 Column(BigIntPrimaryKey, ...) 使用）
BigIntPrimaryKey = BigInteger


class TimestampMixin:
    """创建时间 Mixin"""
    create_time = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")


class UpdateMixin(TimestampMixin):
    """创建+更新时间 Mixin"""
    update_time = Column(
        DateTime, default=datetime.now, onupdate=datetime.now,
        nullable=False, comment="更新时间",
    )

# 日志实例
logger = logging.getLogger(__name__)


# ============================================================
# 第零部分：ORM 公共列定义 & Mixin
# ============================================================
# 供 models/chat.py 等使用旧式 Column() 风格的 Model 复用。
# models/crm.py 使用新式 mapped_column()，不需要这两个定义。
# ============================================================

# BIGINT UNSIGNED AUTO_INCREMENT 主键的快捷定义
# 用法: id = Column(BigIntPrimaryKey, primary_key=True, autoincrement=True)
BigIntPrimaryKey = BigInteger().with_variant(
    __import__("sqlalchemy.dialects.mysql", fromlist=["BIGINT"]).BIGINT(unsigned=True),
    "mysql",
)


class TimestampMixin:
    """create_time + update_time 通用 Mixin，供旧式 Column() Model 继承。"""

    @declared_attr
    def create_time(cls):
        return Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    @declared_attr
    def update_time(cls):
        return Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")


# ============================================================
# 第一部分：统一响应格式工具
# ============================================================
# 对应 API 文档第 2.3 节。所有接口返回统一的 {code, message, data} 三段式。
# 在整个项目中直接调用这两个函数，而不是手动构造 dict，确保响应格式一致。
# ============================================================


def success_response(
    data: Any = None,
    message: str = "success",
    code: int = 0,
) -> Dict[str, Any]:
    """
    构造成功响应的标准格式。

    参数:
        data:    响应数据体，可以是单对象(dict)、列表(list)、分页对象(dict) 或 None
        message: 给前端的提示信息，默认 "success"
        code:    业务状态码，成功固定为 0

    返回格式:
        {"code": 0, "message": "success", "data": {...}}

    使用示例:
        return success_response(data=user_dict)
        return success_response(data={"items": [...], "total": 50, "page": 1, "page_size": 20})
    """
    return {
        "code": code,
        "message": message,
        "data": data,
    }


def error_response(
    code: int,
    message: str,
    data: Any = None,
) -> Dict[str, Any]:
    """
    构造错误响应的标准格式（通常由异常类间接调用，一般不需要手动使用）。

    返回格式:
        {"code": 40001, "message": "参数校验失败", "data": null}
    """
    return {
        "code": code,
        "message": message,
        "data": data,
    }


# ============================================================
# 第二部分：统一异常类体系
# ============================================================
# 严格对应 API 文档第 3 章错误码体系。
#
# 错误码分段（API 文档 3.1 节）:
#   0          成功
#   40001-40099 参数校验错误
#   40101-40199 认证错误
#   40301-40399 权限错误
#   40401-40499 资源不存在
#   40901-40999 业务冲突
#   42201-42299 业务规则校验失败
#   50001-50099 服务器内部错误
#
# 使用方式:
#   raise NotFoundError("用户不存在")
#   raise ConflictError("该用户已报名此活动")
#   raise ReferenceNotFoundError("活动", event_id)
#
# FastAPI 遇到 HTTPException 会自动返回 JSON:
#   {"code": 40401, "message": "用户不存在", "data": null}
# ============================================================


class BusinessError(HTTPException):
    """
    统一业务异常基类。

    所有的业务错误都通过抛出这个类（或其子类）来处理。
    FastAPI 会自动捕获 HTTPException 并返回标准 JSON 响应。

    子类可以预设 code 和 status_code，调用时只需要传 message。

    参数:
        code:        业务错误码（见 API 文档 3.2 节错误码明细）
        message:     人类可读的错误描述
        status_code: HTTP 状态码（400/401/403/404/409/422/500）
    """

    def __init__(self, code: int, message: str, status_code: int = 400):
        # 把错误码和消息放入 detail 字段（API 文档 2.3 节错误响应格式）
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "data": None},
        )


# --- 资源不存在类（HTTP 404）---

class NotFoundError(BusinessError):
    """
    资源不存在异常。

    HTTP 状态码: 404
    错误码:      40401

    使用场景:
      - 查询/更新/删除时 ID 对应的记录不存在
      - GET /users/999 → 用户 999 不存在
    """

    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=40401, message=message, status_code=404)


class ReferenceNotFoundError(BusinessError):
    """
    逻辑外键引用不存在异常（⭐ V1.1 新增）。

    HTTP 状态码: 404
    错误码:      40402

    这是无物理外键策略下的关键异常。
    当插入记录时，其引用的 {entity}_id 对应的父记录不存在时抛出。

    使用场景:
      - 报名时 event_id 对应的活动不存在
      - 创建跟进记录时 lead_id 对应的客户不存在
      - 提交请假时 student_id 对应的学生不存在
    """

    def __init__(self, entity: str, id_value: int):
        super().__init__(
            code=40402,
            message=f"{entity}不存在: id={id_value}",
            status_code=404,
        )


# --- 业务冲突类（HTTP 409）---

class ConflictError(BusinessError):
    """
    业务冲突异常。

    HTTP 状态码: 409
    错误码:      40901

    使用场景:
      - 重复报名同一活动（唯一约束冲突）
      - 用户名已存在
      - 并发修改导致状态已被更新
    """

    def __init__(self, message: str):
        super().__init__(code=40901, message=message, status_code=409)


# --- 状态机/业务规则类（HTTP 422）---

class StateError(BusinessError):
    """
    状态不允许操作异常。

    HTTP 状态码: 422
    错误码:      40902（注意：虽然 HTTP 422，但错误码段是 409xx 业务冲突）

    使用场景:
      - 终态客户回退（signed → new 不允许）
      - 活动状态不允许报名（已结束/已取消）
      - 已审批的请假重复审批
    """

    def __init__(self, message: str):
        super().__init__(code=40902, message=message, status_code=422)


class AuthError(BusinessError):
    """
    认证失败异常。

    HTTP 状态码: 401
    错误码:      40103

    对应 API 文档第 3.2 节错误码 40103。
    用于登录场景：用户名或密码错误、账号被禁用等。

    使用场景:
      - 用户名或密码错误
      - 账号已被禁用
      - 账号不存在
    """

    def __init__(self, message: str):
        super().__init__(code=40103, message=message, status_code=401)


class ValidationError(BusinessError):
    """
    参数校验失败异常。

    HTTP 状态码: 400
    错误码:      40001

    使用场景:
      - 必填字段缺失
      - 字段格式不正确
      - 枚举值不在允许范围内
    """

    def __init__(self, message: str = "参数校验失败"):
        super().__init__(code=40001, message=message, status_code=400)


# ============================================================
# 第三部分：逻辑外键校验装饰器
# ============================================================
# ⭐ 对应 API 文档第 14.2 节，数据库文档第 5 章。
#
# 由于数据库全面禁用物理外键，所有 {entity}_id 字段的引用完整性
# 必须在应用层（Python 代码）显式校验。
#
# 这个装饰器提供了一种声明式的校验方式:
#   在被装饰的函数执行前，自动查询数据库确认引用记录存在。
#   如果不存在则抛出 ReferenceNotFoundError。
#
# 使用示例:
#   @validate_entity_exists(SysUser, "student_id", "学生")
#   def create_leave(db: Session, student_id: int, ...):
#       ...
#
# 工作原理:
#   1. 函数调用前 → 从 kwargs 中取出 field_name 的值
#   2. 如果值不为 None → SELECT EXISTS(SELECT 1 FROM entity_model WHERE id=?)
#   3. 不存在 → raise ReferenceNotFoundError
#   4. 存在   → 正常执行函数
# ============================================================


def validate_entity_exists(
    entity_model: type,     # SQLAlchemy Model 类，如 SysUser
    field_name: str,        # 函数参数名，如 "student_id"
    error_entity_name: str, # 中文实体名，用于错误消息，如 "学生"
) -> Callable:
    """
    校验逻辑外键指向的实体是否存在的装饰器。

    本装饰器会在被装饰函数执行前，校验 field_name 对应的 entity_model 记录是否存在。

    参数:
        entity_model:      SQLAlchemy Model 类（如 SysUser, CRMLead, EventLecture）
        field_name:        函数参数名（如 "student_id", "lead_id", "event_id"）
        error_entity_name: 人类可读的实体名称，用于错误消息（如 "学生", "意向客户", "活动"）
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)  # 保留原函数的 __name__ 和 docstring，方便调试和 Swagger
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 1. 从函数参数中取出要校验的 ID 值
            entity_id = kwargs.get(field_name)
            if entity_id is not None:
                # 2. 从参数中获取数据库会话（所有 Service 函数都应包含 db 参数）
                session: Optional[Session] = kwargs.get("db")
                if session is None:
                    # 遍历位置参数找 Session 类型的
                    for arg in args:
                        if isinstance(arg, Session):
                            session = arg
                            break

                if session is not None:
                    # 3. 使用 EXISTS 子查询校验记录存在（比 COUNT 更高效，找到即返回）
                    exists = session.query(
                        session.query(entity_model)
                        .filter_by(id=entity_id)
                        .exists()
                    ).scalar()
                    if not exists:
                        raise ReferenceNotFoundError(error_entity_name, entity_id)
                else:
                    # 如果没有 db 参数，跳过校验（可能是测试环境或其他场景）
                    logger.warning(
                        f"validate_entity_exists: 未找到 db 参数，跳过 {error_entity_name} id={entity_id} 的校验"
                    )

            # 4. 校验通过，执行原函数
            return func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# 第四部分：密码哈希工具
# ============================================================
# 对应数据库文档第 9.2 节敏感数据保护。
#
# 使用 bcrypt 算法:
#   - 自动生成随机盐值（salt），相同密码两次哈希结果不同
#   - 成本因子 12 → 单次哈希约 0.3 秒（平衡安全与性能）
#   - 输出格式: $2b$12$...（固定 60 字符）
#
# 为什么用 bcrypt 而不是 SHA256？
#   SHA256 太快了，攻击者可以用 GPU 每秒尝试数十亿个密码。
#   bcrypt 刻意设计得很慢，加大暴力破解成本。
# ============================================================


def hash_password(password: str) -> str:
    """
    将明文密码加密为 bcrypt 哈希值。

    参数:
        password: 明文密码（如 "123456"）

    返回:
        bcrypt 哈希字符串，60 字符（如 "$2b$12$LJ3m4ys3GZfnYMz8kVsKa..."）

    使用场景: 用户注册、修改密码时调用
    """
    # 将密码编码为 UTF-8 字节（bcrypt 要求 bytes 输入）
    password_bytes = password.encode("utf-8")
    # 生成随机盐值 + 计算哈希
    # gensalt() 使用默认 cost=12（在 config.py 中可配）
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    hashed = bcrypt.hashpw(password_bytes, salt)
    # 返回字符串形式存入数据库
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否与哈希值匹配。

    参数:
        plain_password:  用户输入的明文密码
        hashed_password: 数据库中存储的 bcrypt 哈希值

    返回:
        True  = 密码正确
        False = 密码错误

    使用场景: 用户登录时调用
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ============================================================
# 第五部分：JWT Token 工具
# ============================================================
# 对应 API 文档第 13.2 节 JWT Token 设计。
#
# JWT (JSON Web Token) 是一种无状态的鉴权方案:
#   用户登录后，服务端签发一个 Token（签名防篡改）
#   后续请求携带 Token，服务端验证签名即可知道是谁，无需查数据库
#
# Token 结构 (三段 Base64 拼接):
#   Header.Payload.Signature
#   - Header:  算法类型（HS256）+ Token 类型（JWT）
#   - Payload: 用户信息（sub=user_id, username, user_type...）+ 过期时间
#   - Signature: 用 SECRET_KEY 对前两段签名，防篡改
#
# Payload 字段（对应 API 文档 13.2 节）:
#   sub       → user_id（JWT 标准字段，subject 的缩写）
#   username  → 登录账号
#   user_type → 用户类型（student/employee/admin），对齐 sys_user.user_type
#   role_id   → 角色 ID，对齐 sys_user.role_id
#   exp       → 过期时间戳（JWT 标准字段）
#   iat       → 签发时间戳（JWT 标准字段）
# ============================================================

# JWT 签名算法
ALGORITHM = "HS256"

# HTTP Bearer Token 解析器
# 自动从请求头 Authorization: Bearer xxx 中提取 Token
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(
    user_id: int,
    username: str,
    user_type: str,
    role_id: Optional[int] = None,
) -> str:
    """
    为用户签发 JWT Access Token。

    参数:
        user_id:   用户主键（对应 sys_user.id）
        username:  登录账号（对应 sys_user.username）
        user_type: 用户类型（student/employee/admin，对应 sys_user.user_type）
        role_id:   角色 ID（对应 sys_user.role_id）

    返回:
        JWT Token 字符串，格式: xxxxx.yyyyy.zzzzz

    有效期: 由 config.ACCESS_TOKEN_EXPIRE_MINUTES 决定（默认 480 分钟 = 8 小时）
    """
    # 当前 UTC 时间
    now = datetime.now(timezone.utc)
    # 过期时间 = 当前时间 + 有效期
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # 构造 Payload（对应 API 文档 13.2 节）
    payload = {
        "sub": str(user_id),    # JWT 标准：主题（subject），必须是字符串
        "username": username,
        "user_type": user_type,
        "role_id": role_id,
        "iat": now,             # JWT 标准：签发时间（issued at）
        "exp": expire,          # JWT 标准：过期时间（expiration）
    }

    # 用 SECRET_KEY 签名，生成 Token
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def verify_token(token: str) -> Dict[str, Any]:
    """
    验证 JWT Token 并返回 Payload。

    参数:
        token: JWT Token 字符串

    返回:
        Payload 字典，包含 sub/username/user_type/role_id 等

    异常:
        HTTPException(40102): Token 无效或已过期（对应 API 文档错误码 40102）
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        # JWTError 是 python-jose 的统一异常父类
        # 包含: ExpiredSignatureError(过期), JWTClaimsError(claims 无效) 等
        raise HTTPException(
            status_code=401,
            detail={
                "code": 40102,
                "message": f"Token 无效或已过期: {str(e)}",
                "data": None,
            },
        )


# ============================================================
# 第六部分：鉴权依赖注入
# ============================================================
# FastAPI 的依赖注入系统允许在路由函数执行前插入鉴权逻辑。
#
# 依赖链:
#   get_current_user → 验证 Token + 查数据库 → 返回 SysUser 对象
#   require_role    → 调用 get_current_user + 校验角色
#
# 使用示例:
#   @router.get("/users")
#   def list_users(current_user = Depends(get_current_user)):
#       # current_user 就是 SysUser ORM 对象
#       ...
#
#   @router.delete("/admin-only")
#   def admin_only(current_user = Depends(require_role(["admin"]))):
#       ...
#
# 鉴权流程:
#   1. 从请求头 Authorization: Bearer xxx 提取 Token
#   2. 验证 Token 签名 + 是否过期
#   3. 从 Payload 中取出 user_id
#   4. 查询 sys_user 表确认用户存在且未被禁用
#   5. 返回 SysUser ORM 对象给路由函数
#
# 数据权限隔离（对应 API 文档第 13.4 节 + 数据库文档第 9.1 节）:
#   get_current_user 只负责"你是谁"的认证
#   数据权限（"你能看什么"）在各自的 Service 层做过滤
# ============================================================


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """
    从请求中获取当前登录用户（FastAPI 依赖注入）。

    流程:
      1. 提取 Authorization: Bearer {token}
      2. 验证 Token 签名和有效期
      3. 查数据库确认用户存在且未被禁用
      4. 返回 SysUser ORM 对象

    参数:
        credentials: HTTP Bearer Token（由 bearer_scheme 自动解析请求头）
        db:          数据库会话（由 get_db 依赖注入）

    返回:
        SysUser ORM 对象（当前登录用户）

    异常:
        40101: 未登录（没有提供 Token）
        40102: Token 无效或已过期
        40103: 用户不存在或已被禁用
    """
    # 1. 检查是否提供了 Token
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": 40101, "message": "未登录，请提供有效的 Token", "data": None},
        )

    # 2. 验证 Token
    payload = verify_token(credentials.credentials)
    user_id_str: str = payload.get("sub")

    if user_id_str is None:
        raise HTTPException(
            status_code=401,
            detail={"code": 40102, "message": "Token 无效：缺少用户标识", "data": None},
        )

    # sub 在 JWT 中必须是字符串，转换回 int
    user_id = int(user_id_str)

    # 3. 查数据库确认用户存在且未被禁用
    # 延迟导入避免循环依赖（models/user.py → models/common.py → models/user.py）
    from models.user import SysUser

    user = db.query(SysUser).filter_by(id=user_id).first()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": 40103, "message": "用户不存在或已被删除", "data": None},
        )

    if user.status == "disabled":
        raise HTTPException(
            status_code=401,
            detail={"code": 40103, "message": "账号已被禁用，请联系管理员", "data": None},
        )

    return user


def require_role(allowed_roles: List[str]) -> Callable:
    """
    要求当前用户属于指定角色之一（工厂函数，返回依赖）。

    这是一个"依赖工厂"——调用 require_role(["admin"]) 返回一个依赖函数，
    该依赖内部先调用 get_current_user 获取用户，再校验角色。

    参数:
        allowed_roles: 允许的角色编码列表，如 ["admin"] 或 ["admin", "manager"]

    返回:
        FastAPI 依赖函数

    使用示例:
        @router.delete("/users/{user_id}")
        def delete_user(
            user_id: int,
            current_user = Depends(require_role(["admin"])),
            db: Session = Depends(get_db),
        ):
            ...

    异常:
        40301: 无权限访问（对应 API 文档错误码 40301）
    """

    def role_checker(
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        """
        内部依赖函数：校验当前用户是否拥有允许的角色。
        """
        # 延迟导入避免循环依赖
        from models.user import SysRole

        # 查找用户的角色编码
        role = db.query(SysRole).filter_by(id=current_user.role_id).first()
        user_role_code = role.role_code if role else None

        # 检查角色是否在允许列表中
        if user_role_code not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": 40301,
                    "message": "无权限访问：当前角色不允许执行此操作",
                    "data": None,
                },
            )
        return current_user

    return role_checker


# ============================================================
# 第七部分：Dify 服务令牌鉴权
# ============================================================
# 对应 API 文档第 10 章 Dify 工具 API。
#
# Dify Chatflow / Workflow 中的 HTTP 节点调用 FastAPI 时，
# 不使用用户 JWT（因为 Dify 没有登录用户），而是使用预设的服务令牌。
#
# 使用方式（在路由中）:
#   @router.post("/profile/upload-json", dependencies=[Depends(verify_dify_token)])
#
# Dify 侧配置:
#   HTTP 节点 → Authorization: Bearer {DIFY_SERVICE_TOKEN}
#   Token 值从 .env 的 DIFY_SERVICE_TOKEN 中获取
# ============================================================


def verify_dify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """
    校验 Dify 服务令牌。用于保护供 Dify 调用的接口。

    与 get_current_user 的区别:
      - get_current_user: 校验用户 JWT → 返回 SysUser 对象
      - verify_dify_token: 校验固定令牌 → 不返回用户，仅验证身份

    使用场景:
      POST /api/v1/profile/upload-json   — Dify Chatflow 上传客户资料
      POST /api/v1/profile/analyze-direct — Dify Chatflow 同步研判
    """
    from config import DIFY_SERVICE_TOKEN

    # 兼容新旧两个 Token（Dify Chatflow 可能使用任一值）
    ALLOWED_TOKENS = {
        DIFY_SERVICE_TOKEN,
        "d88d70a2a80921cac932aab7efdcd723b1604f175e1b3e41b6f72900d68b0598",
    }

    if credentials is None:
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "message": "无效的服务令牌", "data": None},
        )
    if credentials.credentials not in ALLOWED_TOKENS:
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "message": "服务令牌校验失败", "data": None},
        )
