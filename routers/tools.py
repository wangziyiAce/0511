"""工具接口路由"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def tools_root():
    return {"module": "工具接口", "status": "ok"}
"""
基础设施模块 — API 路由
===========================================
处理用户认证、用户管理、角色查询、组织架构相关的 HTTP 请求。

路由前缀: /api/v1/auth

对应 API 文档:
  - 第 4.1 节  接口清单
  - 第 4.2 节  POST /api/v1/auth/login
  - 第 4.3 节  GET  /api/v1/auth/me

所有接口返回统一的 {code, message, data} 三段式响应。

鉴权策略:
  - /login 公开（无需 Token）
  - /me + /users + /roles + /organizations 需要登录（JWT Bearer Token）
  - 创建/更新操作依赖 get_current_user 依赖注入
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

# --- 公共基础 ---
from models.common import (
    NotFoundError,
    get_current_user,
    success_response,
)

# --- 数据模型 ---
from models.user import SysUser

# --- Schema ---
from schemas import PaginationParams
from schemas.student import (
    LoginRequest,
    OrganizationCreate,
    PasswordChangeRequest,
    TokenResponse,
    UserCreate,
    UserUpdate,
)

# --- Service ---
from services.student_service import (
    authenticate_user,
    change_password,
    create_organization,
    create_user,
    get_current_user_info,
    get_organization_tree,
    get_user,
    list_organizations_flat,
    list_roles,
    list_users,
    update_user,
)

# --- 数据库 ---
from utils.database import get_db

# ============================================================
# 路由实例
# ============================================================
# prefix 会由 main.py 中 include_router 统一设置，这里只定义路径
router = APIRouter(tags=["基础设施"])


# ============================================================
# 一、认证接口
# ============================================================

@router.post("/auth/login", summary="用户登录")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    用户登录接口。

    对应 API 文档第 4.2 节。

    流程:
      1. 验证用户名 + 密码（bcrypt 校验）
      2. 签发 JWT Token（24h 有效期）
      3. 返回 Token + 用户信息

    请求体:
      {"username": "admin", "password": "123456"}

    成功响应:
      {code: 0, message: "success", data: {user_id, username, real_name, user_type, access_token, ...}}

    错误响应:
      40103: 用户名或密码错误
      40103: 账号已被禁用
    """
    token_data = authenticate_user(db, request.username, request.password)
    return success_response(data=token_data.model_dump())


@router.get("/auth/me", summary="当前用户信息")
def me(
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取当前登录用户的详细信息。

    对应 API 文档第 4.3 节。

    请求头:
      Authorization: Bearer {access_token}

    成功响应:
      {code: 0, data: {user_id, username, real_name, user_type, department, contact_info, ...}}
    """
    user_info = get_current_user_info(db, current_user)
    return success_response(data=user_info.model_dump())


# ============================================================
# 二、用户管理接口
# ============================================================

@router.get("/auth/users", summary="用户列表")
def api_list_users(
    # --- 筛选参数 ---
    user_type: str = Query(default=None, description="用户类型: student/employee/admin"),
    keyword: str = Query(default=None, description="关键词（匹配 username 或 real_name）"),
    status: str = Query(default=None, description="账号状态: normal/disabled"),
    # --- 分页参数 ---
    pagination: PaginationParams = Depends(),
    # --- 鉴权 + 数据库 ---
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    分页查询用户列表。

    查询参数:
      ?user_type=employee     — 只看员工
      ?keyword=张三           — 模糊搜索
      ?status=normal          — 只看正常账号
      ?page=1&page_size=20    — 分页

    权限:
      所有登录用户均可查看（后续可按角色限制）。
    """
    result = list_users(db, pagination, user_type=user_type, keyword=keyword, status=status)
    return success_response(data=result)


@router.post("/auth/users", summary="创建用户")
def api_create_user(
    request: UserCreate,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    创建新用户。

    请求体:
      {username, password, real_name, user_type, role_id?, department?, contact_info?, avatar_url?}

    业务规则:
      - username 唯一
      - role_id 对应的角色必须存在（逻辑外键校验）
      - 密码将自动 bcrypt 哈希后入库

    权限:
      仅管理员可创建用户（后续可放宽）。
    """
    user = create_user(db, request)
    return success_response(
        data={
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "user_type": user.user_type,
            "status": user.status,
            "create_time": user.create_time.isoformat(),
        },
        message="创建成功",
    )


@router.get("/auth/users/{user_id}", summary="用户详情")
def api_get_user(
    user_id: int,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查询单个用户详情。

    路径参数:
      user_id: 用户主键
    """
    user = get_user(db, user_id)
    from schemas.student import UserResponse

    return success_response(data=UserResponse.model_validate(user).model_dump())


@router.put("/auth/users/{user_id}", summary="更新用户")
def api_update_user(
    user_id: int,
    request: UserUpdate,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    更新用户信息（部分更新）。

    只传需要修改的字段即可，未传字段保持不变。

    路径参数:
      user_id: 用户主键
    """
    user = update_user(db, user_id, request)
    from schemas.student import UserResponse

    return success_response(
        data=UserResponse.model_validate(user).model_dump(),
        message="更新成功",
    )


# ============================================================
# 三、角色查询接口
# ============================================================

@router.get("/auth/roles", summary="角色列表")
def api_list_roles(
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查询所有启用的角色。

    用于:
      - 前端下拉菜单（创建用户时选择角色）
      - 权限判断
      - 系统设置页

    不分页（角色数量固定 5 条）。
    """
    roles = list_roles(db)
    return success_response(data={"items": [r.model_dump() for r in roles]})


# ============================================================
# 四、组织架构接口
# ============================================================


@router.get("/auth/organizations", summary="组织列表（平铺）")
def api_list_organizations(
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查询所有启用的组织（平铺，不含 children 嵌套）。

    用于:
      - 前端下拉菜单
      - 部门选择器
    """
    orgs = list_organizations_flat(db)
    return success_response(data={"items": [o.model_dump() for o in orgs]})


@router.get("/auth/organizations/tree", summary="组织架构树")
def api_organization_tree(
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查询完整组织架构树（children 递归嵌套）。

    用于:
      - 前端树形组件直接渲染
      - 组织架构图

    返回格式:
      [{id, org_name, children: [{id, org_name, children: [...]}]}]
    """
    tree = get_organization_tree(db)
    return success_response(data={"items": [o.model_dump() for o in tree]})


@router.post("/auth/organizations", summary="创建组织节点")
def api_create_organization(
    request: OrganizationCreate,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    创建新的组织节点。

    请求体:
      {org_name, parent_id?, org_type?, sort_order?}

    parent_id 为 null 表示根组织（顶层节点）。
    """
    org = create_organization(db, request)
    from schemas.student import OrganizationResponse

    return success_response(
        data=OrganizationResponse.model_validate(org).model_dump(),
        message="创建成功",
    )


# ============================================================
# 五、密码修改
# ============================================================


@router.put("/auth/users/{user_id}/password", summary="修改密码")
def api_change_password(
    user_id: int,
    request: PasswordChangeRequest,
    current_user: SysUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    修改指定用户的密码。

    业务规则:
      - 必须提供旧密码验证身份
      - 新密码最少 6 位
      - 仅允许修改自己的密码（管理员可修改他人，后续扩展）

    请求体:
      {old_password: "当前密码", new_password: "新密码（最少6位）"}
    """
    change_password(db, user_id, request.old_password, request.new_password)
    return success_response(message="密码修改成功")
