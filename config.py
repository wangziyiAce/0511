"""
教育服务系统 — 全局配置文件
================================
所有可配置项集中在此文件，通过环境变量（.env）或默认值控制。
修改配置后重启应用即可生效，无需改代码。

配置分类:
  1. 数据库连接（MySQL 8.0 + PyMySQL）
  2. 连接池参数（控制并发性能）
  3. 应用元信息（名称、版本、调试开关）
  4. Dify AI 平台连接
  5. 安全相关（JWT 密钥、密码加密参数）

使用方式:
  import config
  db_url = config.DATABASE_URL

环境变量覆盖（生产环境推荐）:
  # Windows PowerShell:
  $env:DB_PASSWORD="my-secret-pw"
  # Linux / macOS:
  export DB_PASSWORD="my-secret-pw"

参考文档:
  《教育服务系统_数据库设计规范文档_V2.1》第 1.1 节 — 数据库选型
  《教育服务系统_数据库设计规范文档_V2.1》第 13.1 节 — 连接池配置
"""

import os  # 读取操作系统环境变量
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent / ".env")

# --- 加载 .env 文件（必须先于所有 os.getenv() 调用）---
import os as _os
from pathlib import Path as _Path
from dotenv import load_dotenv as _load_dotenv

# 从当前文件位置向上找项目根目录的 .env
_env_path = _Path(__file__).resolve().parent / ".env"
_load_dotenv(_env_path)


# ============================================================
# 一、数据库连接配置
# ============================================================
# 数据库选型: MySQL 8.0
# 驱动:       PyMySQL（纯 Python 实现，安装简单）
# 字符集:     utf8mb4（支持 emoji 和全 Unicode 字符集）
# 排序规则:   utf8mb4_unicode_ci（大小写不敏感，国际通用）
# ============================================================

# --- 数据库服务器地址 ---
# 如果 MySQL 在本地运行，使用 localhost 即可
# 如果 MySQL 在远程服务器，改为 IP 地址，如 "192.168.1.100"
DB_HOST: str = os.getenv("DB_HOST", "localhost")

# --- 数据库端口 ---
# MySQL 默认端口 3306，如果改了端口号，通过环境变量 DB_PORT 覆盖
DB_PORT: int = int(os.getenv("DB_PORT", "3306"))

# --- 数据库用户名 ---
# 开发环境可以用 root；生产环境必须用低权限账号
DB_USER: str = os.getenv("DB_USER", "root")

# --- 数据库密码 ---
# ⚠️ 不要把真实密码写在这里！通过环境变量 DB_PASSWORD 传入
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "123456")

# --- 数据库名称 ---
# 必须与手动创建的数据库名一致:
#   CREATE DATABASE IF NOT EXISTS education_service
#   DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci;
DB_NAME: str = os.getenv("DB_NAME", "education_service")

# --- 字符集 ---
# utf8mb4 = MySQL 中真正的 UTF-8（utf8 只是阉割版，只支持 3 字节）
# 除非有特殊理由，不要改
DB_CHARSET: str = "utf8mb4"


# ============================================================
# 二、连接池配置
# ============================================================
# 连接池是数据库连接的"蓄水池"，预先创建若干连接备用，
# 避免每次请求都重新建立 TCP 连接（代价高昂）。
#
# 名词解释:
#   pool_size:     核心连接数，始终保持这么多连接
#   max_overflow:  当核心连接用完时，最多再额外创建多少个
#                  → 最大总连接数 = pool_size + max_overflow = 10 + 20 = 30
#   pool_timeout:  当连接池耗尽时，等待多久才报错（秒）
#   pool_recycle:  每个连接最长存活时间（秒），超过则自动关闭重建
#                  → 必须小于 MySQL 的 wait_timeout（默认 8 小时 = 28800 秒）
#   pool_pre_ping: 每次使用连接前先发一个 SELECT 1 测试是否还活着
#                  → 防止因 MySQL 主动断开而拿到死连接
#   echo:          是否打印所有 SQL 语句（开发时打开方便调试，生产必须关闭）
# ============================================================

DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))

# --- SQL 日志开关 ---
# true  = 会在控制台看到每一条执行的 SQL（调试神器，但刷屏严重）
# false = 安静模式，适合生产环境和正式演示
DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"


# ============================================================
# 三、数据库连接 URL（由上面各项自动拼接，一般不需要手动改）
# ============================================================
# 格式: mysql+pymysql://用户名:密码@主机:端口/数据库名?charset=字符集
#
# PyMySQL 连接参数说明:
#   mysql+pymysql → SQLAlchemy 方言+驱动，告诉 SQLAlchemy 用 MySQL 语法 + PyMySQL 通信
#   ?charset=utf8mb4 → 连接时即设定字符集，确保中文不出现乱码
DATABASE_URL: str = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?charset={DB_CHARSET}"
)


# ============================================================
# 四、应用元信息
# ============================================================
# 这些值会出现在 Swagger 文档页面的标题栏
APP_NAME: str = "教育服务系统 API"
APP_VERSION: str = "1.0.0"

# --- 调试模式 ---
# true  = FastAPI 自动重载 + 详细错误页（开发时用）
# false = 隐藏内部错误信息（生产时用）
APP_DEBUG: bool = os.getenv("APP_DEBUG", "true").lower() == "true"


# ============================================================
# 五、Dify AI 平台连接配置
# ============================================================
# Dify 是本系统的"大脑"，负责:
#   1. AI 对话（客服 Agent）
#   2. 意图识别（用户问了什么 → 调用哪个 API）
#   3. 客户画像研判（AI 匹配产品线）
#   4. 日报/报告生成

# --- Dify API 地址 ---
# 如果是本地 Docker 部署，默认端口 5001
# 如果是内网服务器，改为 http://192.168.x.x:5001/v1
DIFY_API_URL: str = os.getenv("DIFY_API_URL", "http://localhost:5001/v1")

# --- Dify 应用 API Key ---
# 在 Dify 后台 → 应用 → API 访问 中获取
# ⚠️ 不要提交到 Git！必须通过环境变量传入
DIFY_API_KEY: str = os.getenv("DIFY_API_KEY", "")


# ============================================================
# 六、LLM 直调配置（绕过 Dify，直接调用模型 API）
# ============================================================
# 使用 OpenAI 兼容的 /v1/chat/completions 格式。
# DeepSeek、通义千问、GLM 等国产模型均兼容此格式。
#
# ⚠️ API Key 通过 .env 文件或环境变量传入，不硬编码！
# .env 已在 .gitignore 中排除，提交 GitHub 不会泄露。

# --- LLM API 地址 ---
# DeepSeek:  https://api.deepseek.com/v1
# 通义千问:  https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_URL: str = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1")

# --- LLM API Key ---
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")

# --- LLM 模型名称 ---
LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

# --- LLM 请求超时（秒）---
LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "120"))

# --- 通义千问 API Key（学生智能助手 student_chat 模块使用）---
# 兼容阿里云 DashScope 的 Qwen 系列模型。
# 留空时 Qwen 不可用，应用仍可正常启动。
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")


# ============================================================
# 七、产品线规则文件路径
# ============================================================
# 客户研判模块从 .md 文件读取产品线匹配规则和产品目录。
# 修改 .md 文件即可更新规则，无需改代码。

PRODUCT_RULES_PATH: str = os.getenv(
    "PRODUCT_RULES_PATH",
    r"C:\Users\Windows\Desktop\产品线匹配规则.md",
)
PRODUCT_CATALOG_PATH: str = os.getenv(
    "PRODUCT_CATALOG_PATH",
    r"C:\Users\Windows\Desktop\全产品线目录.md",
)


# ============================================================
# 八、安全配置
# ============================================================
# --- JWT 签名密钥 ---
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

# --- Dify 服务令牌 ---
# 用于 Dify HTTP 节点调用 FastAPI 时的鉴权（对应 API 文档第 10 章）
# 生成方式: python -c "import secrets; print(secrets.token_hex(32))"
# ⚠️ 不要提交到 Git！生产环境通过环境变量覆盖
DIFY_SERVICE_TOKEN: str = os.getenv(
    "DIFY_SERVICE_TOKEN",
    "d88d70a2a80921cac932aab7efdcd723b1604f175e1b3e41b6f72900d68b0598",
)

# --- 密码哈希成本因子 ---
# bcrypt 的核心参数，控制哈希计算复杂度。
# 值越大越安全，但登录时验证速度越慢。
#   12 = 推荐值，验证耗时 ~0.3 秒（平衡安全与体验）
#   14 = 更高安全，验证耗时 ~1 秒
#   ⚠️ 现有用户密码不会自动升级，改这个值只影响新增和修改密码
BCRYPT_COST: int = 12

# --- JWT Token 过期时间（分钟）---
# 1440 分钟 = 24 小时，对应 API 文档 §4.2
# 到达过期时间后用户需重新登录
ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

# ============================================================
# 七、通义千问 (Qwen) 大模型配置
# ============================================================
# 阿里云百炼 API Key
# 申请地址: https://dashscope.console.aliyun.com/
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")

# LLM 模型选择: qwen-turbo(极速) / qwen-plus(均衡推荐) / qwen-max(最强)
Qwen_MODEL: str = os.getenv("Qwen_MODEL", "qwen-plus")

# ============================================================
# 九、Settings 兼容对象（供 conftest、security 等模块通过属性访问）
# ============================================================
from types import SimpleNamespace as _SimpleNamespace

settings = _SimpleNamespace(
    DIFY_SERVICE_TOKEN=DIFY_SERVICE_TOKEN,
    APP_ENV=os.getenv("APP_ENV", "development"),
    APP_DEBUG=APP_DEBUG,
)
