"""安全与鉴权工具"""
from typing import Optional

from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from config import settings
from utils.exceptions import BusinessError


_dify_service_token_scheme = HTTPBearer(
    scheme_name="DifyServiceToken",
    description="Dify HTTP 节点调用 FastAPI 白名单接口的服务令牌",
    auto_error=False,
)


def verify_dify_service_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_dify_service_token_scheme),
) -> None:
    """校验 Dify 服务 Token（白名单接口鉴权）"""
    # 使用 HTTPBearer 让 Swagger 通过 Authorize 按钮发送 Authorization 头。
    if credentials is None or not credentials.credentials.strip():
        raise BusinessError(code=40301, message="无效的服务令牌", status_code=403)
    token = credentials.credentials.strip()
    # Service Token 与用户 JWT 分离，只用于 Dify HTTP 节点调用白名单接口。
    if token != settings.DIFY_SERVICE_TOKEN:
        raise BusinessError(code=40301, message="服务令牌校验失败", status_code=403)
