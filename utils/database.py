"""
数据库连接管理 — SQLAlchemy 同步引擎 + 会话工厂
====================================================
这个文件是整个应用与 MySQL 通信的唯一入口。所有数据库操作都
通过这里的 engine（引擎）、session（会话）和 Base（基类）完成。

核心组件:
  1. engine        — 数据库引擎，管理底层连接池
  2. SessionLocal  — 会话工厂，每次请求从这里拿一个会话
  3. Base          — ORM 基类，所有表 Model 都继承它
  4. get_db()      — FastAPI 依赖注入函数，自动获取和释放会话
  5. init_db()     — 应用启动时自动创建所有表

关键概念:
  会话(Session)  = 一次"数据库对话"。查询、插入、更新、删除都在会话中进行。
                 会话结束时统一提交（commit）或回滚（rollback），保证数据一致性。

  连接池 = 预创建的一批 TCP 连接。没有连接池的话，每个 HTTP 请求都要重新
          连接 MySQL（三次握手 + 认证，~50ms），连接池把连接复用起来，大幅提速。

使用示例:
  from utils.database import SessionLocal
  db = SessionLocal()
  user = db.query(SysUser).filter_by(username="admin").first()
  db.close()

  # 在 FastAPI 路由中（推荐方式）:
  @router.get("/users")
  def list_users(db: Session = Depends(get_db)):
      return db.query(SysUser).all()
      # 不需要手动 close，get_db 会自动处理

参考文档:
  《教育服务系统_数据库设计规范文档_V2.1》第 1.1 节 — 数据库选型
  《教育服务系统_数据库设计规范文档_V2.1》第 13.1 节 — 连接池配置
"""

from typing import Generator

# --- SQLAlchemy 核心组件 ---
# create_engine: 创建数据库引擎（连接池的拥有者）
from sqlalchemy import create_engine

# DeclarativeBase: 声明式 ORM 基类，继承它就能自动映射 Python 类 → 数据库表
# Session:         数据库会话对象（类型注解用）
# sessionmaker:    会话工厂函数，封装了创建 Session 的配置
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# QueuePool: 队列连接池（先进先出，最通用的连接池类型）
from sqlalchemy.pool import QueuePool

# --- 从配置文件中导入各项参数 ---
from config import (
    DATABASE_URL,        # 完整的数据库连接字符串
    DB_ECHO,             # 是否打印 SQL 日志
    DB_POOL_SIZE,        # 核心连接数
    DB_MAX_OVERFLOW,     # 溢出连接数上限
    DB_POOL_TIMEOUT,     # 等待连接超时（秒）
    DB_POOL_RECYCLE,     # 连接最大存活时间（秒）
)


# ============================================================
# 一、数据库引擎（Engine）
# ============================================================
# Engine 是整个数据库通信的核心对象。它:
#   1. 管理连接池（持有所有数据库连接）
#   2. 将 Python 的 ORM 操作翻译成各数据库的 SQL 方言（MySQL/Oracle/SQLite...）
#   3. 执行 SQL 并返回结果
#
# 整个应用应该只有一个 Engine 实例（单例模式），
# SQLAlchemy 内部已经保证 create_engine() 多次调用返回同一对象。
# ============================================================

engine = create_engine(
    # --- 数据库连接 URL ---
    # 格式: mysql+pymysql://user:pass@host:port/db?charset=utf8mb4
    DATABASE_URL,

    # --- 连接池类型 ---
    # QueuePool = 队列池，适合多线程并发场景（FastAPI 的每个请求一个线程）
    # 备选: NullPool（无连接池，每次新建，仅测试用）、StaticPool（单连接，仅 SQLite 内存库用）
    poolclass=QueuePool,

    # --- 核心连接数 ---
    # 连接池始终维持这么多条"热"连接，拿来即用。
    # 10 适合中小并发，如果 QPS 很高可以调到 20~30。
    # 但不要无脑加，MySQL 端也要相应调高 max_connections。
    pool_size=DB_POOL_SIZE,

    # --- 溢出连接数 ---
    # 当核心连接全部被占用时，最多额外创建 20 条"临时"连接。
    # 总连接数上限 = pool_size + max_overflow = 10 + 20 = 30。
    # 临时连接用完后会被关闭（不回到池中）。

    max_overflow=DB_MAX_OVERFLOW,

    # --- 连接获取超时 ---
    # 当连接池耗尽（30 条全在用），新来的请求等待多少秒后才报错。
    # 30 秒是比较宽松的值，给高峰流量留缓冲。
    pool_timeout=DB_POOL_TIMEOUT,

    # --- 连接自动回收时间 ---
    # MySQL 默认在连接空闲 8 小时后主动断开（wait_timeout=28800）。
    # pool_recycle 设为 3600（1 小时），保证在 MySQL 断开之前我们先主动回收。
    # 规则: pool_recycle 必须 < MySQL wait_timeout
    pool_recycle=DB_POOL_RECYCLE,

    # --- 连接预检 ---
    # 每次从连接池取出连接时，先发一条 SELECT 1 测试连接是否还活着。
    # 如果 MySQL 已经断开（网络闪断 / 重启），则自动重新连接，对上层无感知。
    # 代价: 每次 +1 次网络往返（~1ms），但换来极高的稳定性，非常值得。
    pool_pre_ping=True,

    # --- SQL 日志 ---
    # 开发调试时在 config.py 中设置 DB_ECHO=true，可以看到每条 SQL。
    # 生产环境务必设为 false，否则日志量爆炸。
    echo=DB_ECHO,
)


# ============================================================
# 二、会话工厂（SessionLocal）
# ============================================================
# SessionLocal 是一个"会话工厂"，每次调用 SessionLocal() 都创建一个新会话。
#
# 会话（Session）是什么？
#   会话 = 一次数据库交互的上下文。它:
#   - 跟踪所有待提交的变更（新增/修改/删除）
#   - 提供了一级缓存（同一个会话内查同一条记录只发一次 SQL）
#   - 在 commit() 时把所有变更打包成一个事务写到数据库
#
# 参数说明:
#   autocommit=False  → 手动控制 commit，防止意外提交（重要数据安全设置）
#   autoflush=False   → 手动控制 flush，避免在查询前自动把脏数据刷到数据库
#   bind=engine       → 绑定到上面的引擎
# ============================================================

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,   # 禁止自动提交。必须显式调用 db.commit() 才会写入数据库
    autoflush=False,    # 禁止自动刷新。需要时手动 db.flush()，给开发者完全控制权
)


# ============================================================
# 三、ORM 基类（Base）
# ============================================================
# 所有数据库表的 Python Model 都必须继承这个 Base。
# SQLAlchemy 通过 Base 的元数据（metadata）知道有哪些表、哪些字段。
#
# 使用方式:
#   from utils.database import Base
#   class SysUser(Base):
#       __tablename__ = "sys_user"
#       id = mapped_column(...)
#
# 原理:
#   DeclarativeBase 内部维护了一个 MetaData 对象，
#   所有继承 Base 的类会自动注册到 MetaData 中。
#   调用 Base.metadata.create_all() 时，一次性创建所有已注册的表。
# ============================================================

class Base(DeclarativeBase):
    """所有 ORM Model 的基类。继承它即可获得自动表映射能力。"""
    pass  # 不需要额外代码，所有逻辑在 DeclarativeBase 内部


# ============================================================
# 四、FastAPI 依赖注入：获取数据库会话（get_db）
# ============================================================
# 这是 FastAPI 推荐的标准写法。每个 HTTP 请求:
#   1. 进入路由函数前 → 创建一个新的数据库会话
#   2. 路由函数执行中 → 使用这个会话进行数据库操作
#   3. 路由函数结束后 → 无论成功还是报错，都会关闭会话，归还连接到连接池
#
# 使用示例:
#   @router.get("/users")
#   def list_users(db: Session = Depends(get_db)):
#       # db 就是一个数据库会话，直接用来查询
#       return db.query(SysUser).all()
#
# 为什么要用依赖注入？
#   - 不用每个函数都写 try/finally 关闭连接（get_db 帮你做了）
#   - 测试时可以轻松替换成测试数据库的会话
#   - 框架自动管理会话生命周期，避免连接泄漏
# ============================================================

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依赖注入: 为每个请求创建数据库会话，请求结束后自动关闭。

    返回值类型 Generator[产出类型, 接收类型, 返回类型]
    - 产出类型 Session → 给路由函数用的是数据库会话
    - 接收类型 None   → 路由函数不会向生成器发送值
    - 返回类型 None   → 生成器结束时没有返回值
    """
    # 1. 从连接池获取一个连接，创建新会话
    db = SessionLocal()
    try:
        # 2. 把会话交给路由函数使用
        yield db
    finally:
        # 3. 无论路由函数是否抛异常，这里都会执行
        #    关闭会话 → 归还连接到连接池 → 避免连接泄漏
        db.close()


# ============================================================
# 五、数据库初始化：自动建表（init_db）
# ============================================================
# 在应用启动时调用一次，自动创建所有 Model 对应的数据库表。
# 如果表已存在则跳过（不会删除已有数据）。
#
# 工作原理:
#   1. import models.xxx → 触发 Python 执行 Model 类定义
#      → Model 类自动注册到 Base.metadata
#   2. Base.metadata.create_all() → 扫描 metadata 中所有已注册的表
#      → 对每个表发一条 CREATE TABLE IF NOT EXISTS ... SQL
#
# ⚠️ 注意事项:
#   - 只创建表，不创建数据库。数据库 eduaction_service 需要手动 CREATE DATABASE
#   - 不会自动修改已有表。如果改了 Model 加了字段，需要手动 ALTER TABLE 或删库重建
#     生产环境建议用 Alembic 做数据库迁移（见数据库设计规范第 15 章）
# ============================================================

def init_db() -> None:
    """
    创建所有已注册 Model 对应的数据库表。

    在 main.py 的 lifespan 中调用，确保应用启动时表结构就绪。

    如果后续新增了 Model 模块（如 models/student.py），
    需要在这个函数里添加对应的 import 语句来触发注册。
    """
    # --- 导入所有 Model 模块（触发类定义 → 自动注册到 Base.metadata）---
    # 为什么用 import 而不是 from import？
    #   只要 Python 执行过这个模块，其中的 class Xxx(Base): 就会执行，
    #   执行时自动把表信息注册到 Base.metadata。不需要用到具体的类名。
    #
    # noqa: F401 告诉 lint 工具"这个 import 没被直接使用是有意为之的"
    import models.user     # noqa: F401  注册 sys_role / sys_user / sys_organization
    import models.crm      # noqa: F401  注册 profile_rule / customer_source / customer_profile

    # ★ 后续新增模块示例（取消注释并替换为实际的模块名）:
    import models.student   # noqa: F401
    # import models.knowledge # noqa: F401
    # import models.report    # noqa: F401

    # --- 执行建表 ---
    # create_all() 会对 metadata 中每个表执行 CREATE TABLE IF NOT EXISTS
    # 已存在的表不受影响，不会丢数据
    Base.metadata.create_all(bind=engine)

    # --- 执行种子数据 ---
    # 建表后检查并插入角色、管理员等必要初始数据
    # 使用独立 Session 避免与请求事务冲突
    session = SessionLocal()
    try:
        from services.student_service import seed_data
        seed_data(session)
    finally:
        session.close()
