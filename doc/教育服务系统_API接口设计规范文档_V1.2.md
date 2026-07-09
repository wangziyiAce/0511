# 教育服务系统 — API 接口设计规范文档 V1.2

> **文档版本**：V1.2  
> **编制日期**：2026-07-09  
> **文档状态**：全链路评审定稿版  
> **适用阶段**：MVP 开发 → 答辩演示  
> **对应架构文档**：《教育服务系统_总体架构设计文档_定稿版V1.2》  
> **对应需求文档**：《教育服务系统_需求规格说明书.md》  
> **对应数据库文档**：《教育服务系统_数据库设计规范文档_V2.1.md》  
> **对应 Dify 文档**：《教育服务系统_Dify工作流设计规范文档_V1.1.md》  
> **定稿基线**：架构 V1.2 + 数据库 V2.1 + API V1.2 + Dify V1.1 + 前端 V1.1  
> **核心原则**：Dify 做大脑，FastAPI 做手脚，MySQL 做记忆，**应用层维护数据一致性**

---

## 目录

1. [设计总则](#1-设计总则)
2. [接口规范约定](#2-接口规范约定)
3. [统一错误码体系](#3-统一错误码体系)
4. [认证与鉴权接口](#4-认证与鉴权接口)
5. [客服 Agent 模块接口](#5-客服-agent-模块接口)
6. [企业智能助手模块接口](#6-企业智能助手模块接口)
7. [学生智能助手模块接口](#7-学生智能助手模块接口)
8. [智能报告模块接口](#8-智能报告模块接口)
9. [客户研判模块接口](#9-客户研判模块接口)
10. [Dify 工具 API（白名单）](#10-dify-工具-api白名单)
11. [异步任务接口规范](#11-异步任务接口规范)
12. [分页、排序、筛选规范](#12-分页排序筛选规范)
13. [安全与鉴权规范](#13-安全与鉴权规范)
14. [应用层数据一致性保障（无外键场景）](#14-应用层数据一致性保障无外键场景)
15. [Swagger 文档配置](#15-swagger-文档配置)
16. [接口测试与验收清单](#16-接口测试与验收清单)
17. [附录](#17-附录)

---

## 1. 设计总则

### 1.1 核心接口架构

```text
┌─────────────────────────────────────────────────────────┐
│  调用方                                                   │
│  Vue 3 前端 / Dify WebApp / Swagger / Postman             │
└────────────┬──────────────────────────┬─────────────────┘
             │                          │
    用户 Token (JWT)           Dify Service Token
             │                          │
┌────────────▼──────────┐  ┌────────────▼──────────────────┐
│  用户接口（全量）        │  │  Dify 工具接口（白名单）         │
│  - 所有 CRUD 操作       │  │  - 仅查询 + 部分写入            │
│  - 管理后台操作          │  │  - 白名单约束                   │
│  - 需要完整权限校验       │  │  - DIFY_SERVICE_TOKEN 鉴权     │
└────────────┬──────────┘  └────────────┬──────────────────┘
             │                          │
             └──────────┬───────────────┘
                        │
             ┌──────────▼──────────┐
             │  FastAPI 业务服务层   │
             │  routers / services  │
             │  schemas / models    │
             │  ┌────────────────┐  │
             │  │ 应用层校验层     │  │ ← ⭐ V1.1 新增
             │  │ (存在性/状态机/  │  │
             │  │  并发/级联操作)  │  │
             │  └────────────────┘  │
             └──────────┬──────────┘
                        │
             ┌──────────▼──────────┐
             │  MySQL 8.0          │
             │  ⭐ 无物理外键       │
             │  逻辑关联 + 索引     │
             │  所有 xxx_id 有索引  │
             └─────────────────────┘
```

### 1.2 接口设计原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **统一前缀** | 所有接口使用 `/api/v1` 前缀 |
| 2 | **RESTful 风格** | 资源名词复数，动作通过 HTTP 方法表达 |
| 3 | **统一响应格式** | `{code, message, data}` 三段式 |
| 4 | **Dify 白名单隔离** | Dify 仅可调用白名单内接口，使用独立 Token |
| 5 | **异步任务模式** | 耗时 AI 操作采用"提交任务 → 查询结果"模式 |
| 6 | **分页标准化** | 查询列表接口统一分页参数（含游标分页） |
| 7 | **写操作记录操作人** | 涉及数据变更的接口记录 `operator_id` |
| 8 | **禁止物理删除** | 删除操作统一软删除或状态变更 |
| 9 | **幂等性设计** | 活动报名等操作支持幂等，防止重复提交 |
| 10 | **Swagger 优先** | 所有接口必须在 Swagger 中完整展示 |
| 11 | ⭐ **应用层维护一致性** | 无物理外键场景下，所有关联校验在 Service 层完成 |
| 12 | ⭐ **字段名与数据库严格对齐** | 接口字段名对应数据库表字段名（小写下划线） |

### 1.3 API 版本策略

| 版本 | 前缀 | 说明 |
|------|------|------|
| MVP V1 | `/api/v1` | 本期实现 |
| 后续增强 | `/api/v2` | 不兼容变更时启用新版本 |

### 1.4 数据库表 → 接口模块映射（⭐ V1.1 新增）

| 表前缀 | 模块 | 数据库表 | 接口路由前缀 |
|--------|------|----------|-------------|
| `sys_` | 基础设施 | `sys_user`, `sys_role`, `sys_organization` | `/api/v1/auth` |
| `crm_` | 企业助手 | `crm_lead`, `crm_follow_up` | `/api/v1/crm` |
| `employee_` | 企业助手 | `employee_daily_report` | `/api/v1/employee` |
| `course_` | 客服Agent | `course_project` | `/api/v1/courses` |
| `event_` | 客服Agent | `event_lecture`, `event_registration` | `/api/v1/events` |
| `chat_` | 客服Agent | `chat_session`, `chat_message` | `/api/v1/chat` |
| `student_` | 学生助手 | `student_info`, `student_admin_service`, `student_feedback_ticket` | `/api/v1/student` |
| `student_psych_` | 学生助手 | `student_psych_profile`, `student_psych_record`, `student_psych_alert` | `/api/v1/student/psych` |
| `application_` | 学生助手 | `application_progress` | `/api/v1/student` |
| `academic_` | 学生助手 | `academic_deadline` | `/api/v1/student` |
| `report_` | 智能报告 | `report_generation`, `report_schedule` | `/api/v1/reports` |
| `customer_` | 客户研判 | `customer_source`, `customer_profile` | `/api/v1/profile` |
| `profile_` | 客户研判 | `profile_rule` | `/api/v1/profile` |
| `knowledge_` | 知识库 | `knowledge_base` | `/api/v1/knowledge` |
| `intent_` | 系统辅助 | `intent_config` | `/api/v1/system` |

### 1.5 全链路评审定稿结论（V1.2）

API V1.2 在 V1.1 基础上做定稿确认，不改变 `/api/v1` 前缀和统一响应格式。经全链路评审，接口层最终口径如下：

| 评审项 | 定稿结论 |
|---|---|
| P0 接口冻结 | 健康检查、登录、课程查询、活动查询/报名、CRM 基础写入、学生请假/投诉、报告生成/查询作为 MVP 主链路接口 |
| Dify 白名单 | 仅允许 Dify 使用 `DIFY_SERVICE_TOKEN` 调用第 10 章白名单接口，不允许直接调用后台管理写接口 |
| 客户研判 | 属于业务核心模块，但 3 天 MVP 可作为 P1 验证链路；文本研判优先，PDF / Excel 上传后续增强 |
| 字段命名 | 请求/响应 JSON 字段继续与数据库 V2.1 字段名保持 `snake_case` 对齐 |
| 事务边界 | 所有写操作在 FastAPI Service 层完成；事务中不调用 Dify，异步任务使用独立 Session |
| 前端演示 | Swagger 是 P0 接口验收入口，Vue 后台按前端 V1.1 的 P1 页面策略逐步实现 |

---

## 2. 接口规范约定

### 2.1 URL 路径规范

```text
格式：/api/v1/{module}/{resource}[/{resource_id}][/{sub_resource}][/{action}]

示例：
GET    /api/v1/courses                    # 查询课程列表
GET    /api/v1/courses/{course_id}        # 查询单个课程
POST   /api/v1/events/{event_id}/register # 活动报名（子资源动作）
PUT    /api/v1/crm/leads/{lead_id}/status # 更新客户状态（字段级更新）
```

### 2.2 HTTP 方法约定

| 方法 | 用途 | 幂等性 | 示例 |
|------|------|--------|------|
| GET | 查询资源 | 是 | 查询课程、客户列表 |
| POST | 创建资源 / 触发动作 | 否 | 新增客户、提交请假、生成报告 |
| PUT | 全量更新 / 状态变更 | 是 | 更新客户状态、审批请假 |
| DELETE | 软删除 | 是 | 取消报名 |

### 2.3 统一响应格式

#### 成功响应（单对象）

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "project_name": "雅思冲刺班",
    "price": 8800.00
  }
}
```

#### 成功响应（列表 + 分页）

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

#### 游标分页响应（⭐ V1.1 新增）

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [],
    "next_cursor": 120,
    "has_more": true
  }
}
```

#### 错误响应

```json
{
  "code": 40001,
  "message": "参数校验失败：课程分类不能为空",
  "data": null
}
```

### 2.4 请求体规范

- **Content-Type**：`application/json`
- **字符编码**：UTF-8
- **日期时间格式**：ISO 8601（`2026-07-09T14:30:00`）
- **日期格式**：`2026-07-09`
- **金额单位**：元（人民币），保留两位小数，对应数据库 `DECIMAL(10,2)`
- **手机号格式**：11 位数字字符串

### 2.5 Pydantic Schema 命名规范

| 类型 | 命名格式 | 示例 |
|------|----------|------|
| 请求体 | `{Resource}Create` / `{Resource}Update` / `{Resource}Query` | `LeadCreate`, `LeadUpdate`, `LeadQuery` |
| 响应体 | `{Resource}Response` / `{Resource}ListResponse` | `LeadResponse`, `LeadListResponse` |
| 通用 | `PaginationParams`, `CursorPaginationParams`, `ErrorResponse` | - |

### 2.6 字段命名与数据库对齐规范（⭐ V1.1 新增）

接口 JSON 字段名必须与数据库表字段名保持一一对应（均使用 `snake_case`）：

| 数据库字段 | 接口 JSON 字段 | 说明 |
|-----------|---------------|------|
| `project_name` | `project_name` | 不使用 `name` 简称 |
| `owner_employee_id` | `owner_employee_id` | 不使用 `owner_id` |
| `current_participants` | `current_participants` | 不使用 `registered_count` |
| `create_time` | `create_time` | 不使用 `created_at` |
| `update_time` | `update_time` | 不使用 `updated_at` |
| `customer_name` | `customer_name` | 不使用 `name` |
| `contact_info` | `contact_info` | 不使用 `phone` + `email` 拆分 |
| `intended_country` | `intended_country` | 不使用 `target_country` |
| `intended_major` | `intended_major` | 不使用 `target_major` |
| `event_name` | `event_name` | 不使用 `title` |
| `start_time` | `start_time` | 不使用 `event_date` |
| `file_url` | `file_url` | 文件只存路径 |
| `attachment_url` | `attachment_url` | 附件只存路径 |

> **原则**：响应中的字段名直接映射数据库列名，避免前端因字段名不一致而做额外转换。关联查询返回的冗余字段（如 `owner_name`）使用 `_name` 后缀。

---

## 3. 统一错误码体系

### 3.1 错误码分段

| 区间 | 含义 | HTTP 状态码 |
|------|------|-------------|
| `0` | 成功 | 200 |
| `40001 - 40099` | 参数校验错误 | 400 |
| `40101 - 40199` | 认证错误 | 401 |
| `40301 - 40399` | 权限错误 | 403 |
| `40401 - 40499` | 资源不存在 | 404 |
| `40901 - 40999` | 业务冲突 | 409 |
| `42201 - 42299` | 业务规则校验失败 | 422 |
| `50001 - 50099` | 服务器内部错误 | 500 |
| `50201 - 50299` | 外部服务调用失败 | 502 |

### 3.2 错误码明细

| 错误码 | HTTP | 说明 | 示例场景 |
|--------|------|------|----------|
| `0` | 200 | 成功 | - |
| `40001` | 400 | 参数校验失败 | 必填字段缺失、格式错误 |
| `40002` | 400 | 参数值非法 | 状态值不在枚举范围内 |
| `40101` | 401 | 未登录 | Token 缺失 |
| `40102` | 401 | Token 无效或已过期 | JWT 过期 |
| `40103` | 401 | 用户名或密码错误 | 登录失败 |
| `40301` | 403 | 无权限访问 | 非授权角色访问 |
| `40302` | 403 | 数据越权 | 访问非本人负责的数据 |
| `40401` | 404 | 资源不存在 | 课程/客户/活动 ID 不存在 |
| `40402` | 404 | ⭐ 关联实体不存在 | 创建记录时引用的 `student_id`/`event_id` 不存在 |
| `40901` | 409 | 资源冲突 | 重复报名、唯一约束冲突 |
| `40902` | 409 | 状态不允许操作 | 已终态的客户不允许回退 |
| `42201` | 422 | 活动名额已满 | 报名时名额不足 |
| `42202` | 422 | 活动状态不允许报名 | 活动不是 `upcoming` |
| `42203` | 422 | 请假已审批 | 重复审批 |
| `42204` | 422 | ⭐ 终态不可回退 | `signed`/`lost` 状态不可回到 `new` |
| `42205` | 422 | ⭐ 逻辑外键引用不存在 | 应用层校验父记录不存在 |
| `50001` | 500 | 服务器内部错误 | 未预期异常 |
| `50002` | 500 | 数据库操作失败 | 连接超时、写入失败 |
| `50201` | 502 | Dify 服务调用失败 | 超时、返回非预期格式 |
| `50202` | 502 | AI 输出解析失败 | JSON 格式错误 |

### 3.3 错误响应工具函数

```python
# utils/errors.py
from fastapi import HTTPException
from typing import Optional

class BusinessError(HTTPException):
    """统一业务异常"""
    def __init__(self, code: int, message: str, status_code: int = 400):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "data": None}
        )

class NotFoundError(BusinessError):
    """资源不存在（404）"""
    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=40401, message=message, status_code=404)

class ConflictError(BusinessError):
    """业务冲突（409）"""
    def __init__(self, message: str):
        super().__init__(code=40901, message=message, status_code=409)

class StateError(BusinessError):
    """状态不允许操作（422）"""
    def __init__(self, message: str):
        super().__init__(code=40902, message=message, status_code=422)

# ⭐ V1.1 新增：逻辑外键不存在异常
class ReferenceNotFoundError(BusinessError):
    """逻辑外键引用不存在（404）"""
    def __init__(self, entity: str, id_value: int):
        super().__init__(
            code=40402,
            message=f"{entity}不存在: id={id_value}",
            status_code=404
        )
```

---

## 4. 认证与鉴权接口

### 4.1 接口清单

| 方法 | 路径 | 说明 | MVP | 鉴权 |
|------|------|------|-----|------|
| GET | `/api/v1/health` | 健康检查 | P0 | 无 |
| POST | `/api/v1/auth/login` | 用户登录 | P0 | 无 |
| GET | `/api/v1/auth/me` | 获取当前用户信息 | P1 | JWT |

### 4.2 POST `/api/v1/auth/login` — 用户登录

**请求体：**

```json
{
  "username": "admin",
  "password": "123456"
}
```

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": 1,
    "username": "admin",
    "real_name": "系统管理员",
    "user_type": "admin",
    "role_id": 1,
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 86400
  }
}
```

**错误响应：**

```json
{
  "code": 40103,
  "message": "用户名或密码错误",
  "data": null
}
```

**业务规则：**

1. 密码使用 bcrypt 哈希校验（cost=12）
2. JWT Token 有效期 24 小时
3. 登录成功更新 `sys_user` 的最后登录时间（如扩展字段）
4. 连续 5 次失败锁定账户 30 分钟（P1）
5. ⭐ 返回字段对齐 `sys_user` 表：`real_name`（非 `display_name`）、`user_type`（非 `role`）

### 4.3 GET `/api/v1/auth/me` — 当前用户信息

**请求头：** `Authorization: Bearer {access_token}`

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": 1,
    "username": "admin",
    "real_name": "系统管理员",
    "user_type": "admin",
    "department": "技术部",
    "contact_info": "138****0001",
    "avatar_url": "/uploads/avatars/1.jpg",
    "status": "normal"
  }
}
```

> ⭐ 字段对齐 `sys_user` 表：`real_name`, `user_type`, `department`, `contact_info`, `status`

### 4.4 GET `/api/v1/health` — 健康检查

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "timestamp": "2026-07-09T14:30:00",
    "database": "connected",
    "dify": "connected"
  }
}
```

---

## 5. 客服 Agent 模块接口

### 5.1 接口清单

| 方法 | 路径 | 说明 | MVP | Dify白名单 |
|------|------|------|-----|-----------|
| GET | `/api/v1/courses` | 查询课程列表 | P0 | ✅ |
| GET | `/api/v1/courses/{course_id}` | 查询课程详情 | P1 | - |
| GET | `/api/v1/events` | 查询活动列表 | P0 | ✅ |
| GET | `/api/v1/events/{event_id}` | 查询活动详情 | P1 | - |
| POST | `/api/v1/events/{event_id}/register` | 活动报名 | P0 | ✅ |
| DELETE | `/api/v1/events/{event_id}/register` | 取消报名 | P1 | - |
| POST | `/api/v1/chat/session` | 创建/获取会话 | P1 | ✅ |
| POST | `/api/v1/chat/session/{session_id}/messages` | 保存消息 | P1 | - |

### 5.2 GET `/api/v1/courses` — 查询课程列表

> ⭐ 数据来源：`course_project` 表

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `category` | string | 否 | 课程分类 |
| `keyword` | string | 否 | 关键词搜索（`project_name` LIKE） |
| `min_price` | decimal | 否 | 最低价格 |
| `max_price` | decimal | 否 | 最高价格 |
| `status` | int | 否 | 状态：1=上架 0=下架，默认 1 |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "project_name": "雅思7分冲刺班",
        "category": "语言培训",
        "description": "针对雅思目标7分的学员...",
        "target_audience": "雅思基础5.5分以上",
        "price": 8800.00,
        "duration": "8周",
        "tags": ["名师授课", "小班教学", "模考+讲评"],
        "status": 1,
        "create_time": "2026-06-01T10:00:00"
      }
    ],
    "total": 15,
    "page": 1,
    "page_size": 20
  }
}
```

> ⭐ 字段对齐 `course_project` 表：`project_name`（非 `name`）、`target_audience`（非 `highlights`）、`tags`（JSON 数组）、`status` 使用 `TINYINT`（1/0）

**业务规则：**
1. 默认只返回 `status=1` 的课程
2. 支持按分类、价格区间筛选
3. Dify 调用时，基于接口返回数据组织回复，不得编造课程信息
4. ⭐ 高频查询场景建议 Redis 缓存（5分钟，状态变更时失效），命中 `idx_category` + `idx_status` 索引

### 5.3 GET `/api/v1/events` — 查询活动列表

> ⭐ 数据来源：`event_lecture` 表

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | 状态：`upcoming`/`ongoing`/`ended`/`cancelled`，默认 `upcoming` |
| `event_type` | string | 否 | 类型：`online`/`offline`/`hybrid` |
| `start_date` | date | 否 | 开始日期 |
| `end_date` | date | 否 | 结束日期 |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20 |

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "event_name": "英国留学申请攻略讲座",
        "event_type": "online",
        "description": "详解2026年英国硕士申请流程...",
        "start_time": "2026-07-15T14:00:00",
        "end_time": "2026-07-15T16:00:00",
        "location": "线上 - 腾讯会议",
        "max_participants": 100,
        "current_participants": 45,
        "organizer_id": 2,
        "status": "upcoming",
        "create_time": "2026-07-01T10:00:00"
      }
    ],
    "total": 8,
    "page": 1,
    "page_size": 20
  }
}
```

> ⭐ 字段对齐 `event_lecture` 表：`event_name`（非 `title`）、`start_time`/`end_time`（非 `event_date`）、`event_type` 枚举值 `online`/`offline`/`hybrid`

**业务规则：**
1. 默认只返回 `status=upcoming` 的活动
2. `current_participants` 为应用层维护的实时报名人数
3. ⭐ 查询使用 `idx_status` + `idx_start_time` 复合索引优化
4. ⭐ 活动详情建议缓存 1 分钟，报名时实时查询（绕过缓存）

### 5.4 POST `/api/v1/events/{event_id}/register` — 活动报名

> ⭐ 数据来源：`event_registration` 表，关联 `event_lecture` 表

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `event_id` | int | 是 | 活动 ID（对应 `event_lecture.id`） |

**请求体：**

```json
{
  "user_id": 10,
  "customer_name": "张三",
  "contact_info": "13800000001",
  "remark": "对英国留学感兴趣"
}
```

> ⭐ 字段对齐 `event_registration` 表：`user_id`（逻辑关联 sys_user）、`customer_name`（未注册用户填写）、`contact_info`（联系方式）

**成功响应：**

```json
{
  "code": 0,
  "message": "报名成功",
  "data": {
    "id": 1,
    "event_id": 1,
    "event_name": "英国留学申请攻略讲座",
    "user_id": 10,
    "customer_name": "张三",
    "contact_info": "138****0001",
    "status": "registered",
    "create_time": "2026-07-09T14:30:00"
  }
}
```

**业务规则（严格校验）：**

1. ⭐ **逻辑外键校验**：`event_id` 对应的 `event_lecture` 记录必须存在（应用层 `SELECT` 校验）
2. 活动状态必须为 `upcoming`
3. `current_participants < max_participants`
4. ⭐ 同一 `user_id` 不允许重复报名同一活动（`uk_event_user` 唯一索引兜底）
5. 并发报名最后名额时使用数据库事务 + `SELECT ... FOR UPDATE`
6. 报名成功后 `current_participants + 1`（应用层原子更新）
7. ⭐ 不在事务中调用外部 API（Dify、邮件、短信）
8. ⭐ 如果 `user_id` 非 NULL，必须校验 `sys_user` 记录存在

**并发控制实现（⭐ 对齐数据库文档 V2.1 6.5.3 节）：**

```python
# services/event_service.py
from sqlalchemy.orm import Session
from sqlalchemy import update
from models.event import EventLecture, EventRegistration
from utils.errors import NotFoundError, ConflictError, StateError, ReferenceNotFoundError

def register_for_event(
    db: Session,
    event_id: int,
    user_id: int = None,
    customer_name: str = None,
    contact_info: str = None,
    remark: str = None
):
    # 事务边界：整个报名操作在一个事务中完成
    with db.begin():
        # 1. 悲观锁锁定活动行（SELECT ... FOR UPDATE）
        event = db.query(EventLecture).filter(
            EventLecture.id == event_id
        ).with_for_update().first()

        if not event:
            raise NotFoundError("活动不存在")

        if event.status != "upcoming":
            raise StateError("活动状态不允许报名")

        # 2. 校验名额（在锁内，保证并发安全）
        if event.current_participants >= (event.max_participants or 999999):
            raise StateError("活动名额已满")

        # 3. 幂等校验（uk_event_user 唯一索引兜底）
        if user_id:
            existing = db.query(EventRegistration).filter(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == user_id
            ).first()
            if existing:
                raise ConflictError("该用户已报名此活动")

        # 4. ⭐ 逻辑外键校验：如果 user_id 不为空，校验用户存在
        if user_id:
            user_exists = db.query(
                db.query(SysUser).filter(SysUser.id == user_id).exists()
            ).scalar()
            if not user_exists:
                raise ReferenceNotFoundError("用户", user_id)

        # 5. 插入报名记录
        registration = EventRegistration(
            event_id=event_id,
            user_id=user_id,
            customer_name=customer_name,
            contact_info=contact_info,
            status="registered",
            remark=remark
        )
        db.add(registration)

        # 6. 原子更新名额计数（UPDATE ... SET current_participants = current_participants + 1）
        db.execute(
            update(EventLecture)
            .where(EventLecture.id == event_id)
            .values(current_participants=EventLecture.current_participants + 1)
        )
    # 事务自动提交（不在事务中调用外部 API）

    return registration
```

**错误场景：**

| 场景 | 错误码 | 说明 |
|------|--------|------|
| 活动不存在 | `40401` | 活动 ID 无效 |
| 活动状态不是 upcoming | `40902` | 活动未发布/已结束 |
| 名额已满 | `42201` | current_participants >= max |
| 重复报名 | `40901` | 同 user_id 已报名 |
| ⭐ 用户不存在 | `40402` | user_id 对应的 sys_user 不存在 |

---

## 6. 企业智能助手模块接口

### 6.1 接口清单

| 方法 | 路径 | 说明 | MVP | Dify白名单 |
|------|------|------|-----|-----------|
| GET | `/api/v1/crm/leads` | 查询意向客户列表 | P0 | ✅ |
| POST | `/api/v1/crm/leads` | 新增意向客户 | P0 | - |
| GET | `/api/v1/crm/leads/{lead_id}` | 查询客户详情 | P1 | - |
| PUT | `/api/v1/crm/leads/{lead_id}` | 更新客户信息 | P1 | - |
| PUT | `/api/v1/crm/leads/{lead_id}/status` | 更新客户状态 | P0 | - |
| POST | `/api/v1/crm/leads/{lead_id}/follow-ups` | 新增跟进记录 | P0 | - |
| GET | `/api/v1/crm/leads/{lead_id}/follow-ups` | 查询跟进历史 | P1 | - |
| POST | `/api/v1/employee/daily-reports` | 提交日报 | P1 | - |
| GET | `/api/v1/employee/daily-reports` | 查询日报 | P1 | - |
| GET | `/api/v1/employee/daily-reports/summary` | 日报汇总 | P1 | - |

### 6.2 GET `/api/v1/crm/leads` — 查询意向客户

> ⭐ 数据来源：`crm_lead` 表

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | 状态：`new`/`contacting`/`qualified`/`signed`/`lost` |
| `keyword` | string | 否 | 客户姓名/联系方式模糊搜索 |
| `owner_employee_id` | int | 否 | 负责人 ID（对应 `crm_lead.owner_employee_id`） |
| `create_time_start` | date | 否 | 创建时间起始 |
| `create_time_end` | date | 否 | 创建时间截止 |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20 |

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "customer_name": "张三",
        "contact_info": "138****0001",
        "gender": "M",
        "age": 25,
        "education_level": "本科",
        "intended_country": "英国",
        "intended_major": "计算机",
        "source_channel": "线上咨询",
        "status": "contacting",
        "owner_employee_id": 3,
        "owner_name": "李员工",
        "last_contact_time": "2026-07-05T14:30:00",
        "create_time": "2026-07-01T10:00:00",
        "update_time": "2026-07-05T14:30:00"
      }
    ],
    "total": 50,
    "page": 1,
    "page_size": 20
  }
}
```

> ⭐ 字段对齐 `crm_lead` 表：`customer_name`（非 `name`）、`contact_info`（非 `phone`+`email` 拆分）、`owner_employee_id`（非 `owner_id`）、`intended_country`/`intended_major`、`source_channel`、`last_contact_time`

**权限规则：**
- **员工**：只能看到 `owner_employee_id = current_user.id` 的客户
- **经理**：可查看本部门员工的客户
- **管理员**：可查看全部客户
- ⭐ 数据权限在 Service 层通过 `filter(CRMLead.owner_employee_id == current_user.id)` 实现

### 6.3 POST `/api/v1/crm/leads` — 新增意向客户

**请求体：**

```json
{
  "customer_name": "张三",
  "contact_info": "13800000001",
  "gender": "M",
  "age": 25,
  "education_level": "本科",
  "intended_country": "英国",
  "intended_major": "计算机",
  "source_channel": "线上咨询",
  "background_info": "对UCL计算机硕士感兴趣，GPA 3.5",
  "remark": "高意向客户，需尽快跟进"
}
```

**成功响应：**

```json
{
  "code": 0,
  "message": "创建成功",
  "data": {
    "id": 1,
    "customer_name": "张三",
    "contact_info": "138****0001",
    "status": "new",
    "owner_employee_id": 3,
    "create_time": "2026-07-09T14:30:00"
  }
}
```

**业务规则：**
1. `customer_name` 必填
2. 新客户默认状态 `new`
3. `owner_employee_id` 默认为当前登录用户
4. ⭐ 插入前校验 `owner_employee_id` 对应的 `sys_user` 存在且 `user_type = 'employee'`
5. 数据写入 `crm_lead` 表

**应用层校验伪代码（⭐ V1.1 新增）：**

```python
def create_lead(db: Session, current_user, data: LeadCreate):
    # 1. 校验负责人存在
    owner_id = data.owner_employee_id or current_user.id
    owner = db.query(SysUser).filter(
        SysUser.id == owner_id,
        SysUser.user_type == 'employee',
        SysUser.status == 'normal'
    ).first()
    if not owner:
        raise ReferenceNotFoundError("员工", owner_id)

    # 2. 创建客户
    lead = CRMLead(
        customer_name=data.customer_name,
        contact_info=data.contact_info,
        owner_employee_id=owner_id,
        status='new',
        **data.model_dump(exclude={'owner_employee_id'})
    )
    db.add(lead)
    db.commit()
    return lead
```

### 6.4 PUT `/api/v1/crm/leads/{lead_id}/status` — 更新客户状态

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `lead_id` | int | 是 | 客户 ID（对应 `crm_lead.id`） |

**请求体：**

```json
{
  "status": "signed"
}
```

或变为流失：

```json
{
  "status": "lost",
  "lost_reason": "客户选择其他机构"
}
```

**成功响应：**

```json
{
  "code": 0,
  "message": "状态更新成功",
  "data": {
    "lead_id": 1,
    "old_status": "contacting",
    "new_status": "signed",
    "update_time": "2026-07-09T14:30:00"
  }
}
```

**业务规则（状态机约束 ⭐ 对齐数据库文档 V2.1 6.4.1 节）：**

```
new ──────→ contacting ──────→ qualified ──────→ signed（终态）
  │              │                  │
  └──────────────┴──────────────────┴──────────→ lost（终态，必须填 lost_reason）
```

1. `signed` 和 `lost` 为终态，不能回退到 `new`
2. 变更为 `lost` 时 `lost_reason` 必填
3. ⭐ 使用 `UPDATE ... WHERE id=? AND status=?` 防止并发状态覆盖
4. 非 `owner_employee_id` 不能变更客户状态

**状态变更实现（⭐ 对齐数据库文档 12.2 节条件更新模式）：**

```python
def update_lead_status(db: Session, lead_id: int, new_status: str, lost_reason: str = None, current_user = None):
    # 状态机校验
    VALID_TRANSITIONS = {
        'new': ['contacting', 'lost'],
        'contacting': ['qualified', 'lost'],
        'qualified': ['signed', 'lost'],
        'signed': [],   # 终态，不可变更
        'lost': [],     # 终态，不可变更
    }

    lead = db.query(CRMLead).filter(CRMLead.id == lead_id).first()
    if not lead:
        raise NotFoundError("客户不存在")

    if new_status not in VALID_TRANSITIONS.get(lead.status, []):
        raise StateError(f"状态不允许从 {lead.status} 变更为 {new_status}")

    if new_status == 'lost' and not lost_reason:
        raise BusinessError(40001, "变更为流失状态必须填写流失原因")

    # ⭐ 条件更新防并发：只有当前状态匹配时才更新
    result = db.execute(
        update(CRMLead)
        .where(
            CRMLead.id == lead_id,
            CRMLead.status == lead.status,  # 乐观锁条件
            CRMLead.owner_employee_id == current_user.id
        )
        .values(
            status=new_status,
            lost_reason=lost_reason,
            update_time=func.now()
        )
    )
    if result.rowcount == 0:
        raise ConflictError("状态已被其他操作修改，请刷新后重试")

    db.commit()
```

### 6.5 POST `/api/v1/crm/leads/{lead_id}/follow-ups` — 新增跟进记录

> ⭐ 数据来源：`crm_follow_up` 表

**请求体：**

```json
{
  "follow_type": "phone",
  "content": "客户对英国硕士申请感兴趣，已发送项目资料...",
  "next_plan": "3天后跟进，确认意向"
}
```

**成功响应：**

```json
{
  "code": 0,
  "message": "跟进记录已保存",
  "data": {
    "id": 1,
    "lead_id": 1,
    "employee_id": 3,
    "follow_type": "phone",
    "content": "客户对英国硕士申请感兴趣...",
    "next_plan": "3天后跟进，确认意向",
    "create_time": "2026-07-09T14:30:00"
  }
}
```

> ⭐ 字段对齐 `crm_follow_up` 表：`follow_type` 枚举 `phone`/`wechat`/`meeting`/`email`/`other`、`employee_id`（非 `operator_id`）

**业务规则：**
1. ⭐ 插入前校验 `lead_id` 对应的 `crm_lead` 记录存在（应用层校验）
2. `content` 为必填
3. `employee_id` 记录操作员工（来自当前登录用户）
4. ⭐ 同步更新 `crm_lead.update_time`（在同一事务中）

**应用层校验（⭐ V1.1 新增）：**

```python
def create_follow_up(db: Session, lead_id: int, current_user, data: FollowUpCreate):
    # 1. 逻辑外键校验：客户必须存在
    lead = db.query(CRMLead).filter(CRMLead.id == lead_id).first()
    if not lead:
        raise ReferenceNotFoundError("意向客户", lead_id)

    # 2. 数据权限校验：非负责人不能跟进
    if current_user.user_type == 'employee' and lead.owner_employee_id != current_user.id:
        raise BusinessError(40302, "无权跟进非本人负责的客户")

    with db.begin():
        # 3. 创建跟进记录
        follow_up = CRMFollowUp(
            lead_id=lead_id,
            employee_id=current_user.id,
            **data.model_dump()
        )
        db.add(follow_up)

        # 4. 同步更新客户最后联系时间
        db.execute(
            update(CRMLead)
            .where(CRMLead.id == lead_id)
            .values(last_contact_time=func.now(), update_time=func.now())
        )
    return follow_up
```

### 6.6 POST `/api/v1/employee/daily-reports` — 提交日报

> ⭐ 数据来源：`employee_daily_report` 表

**请求体：**

```json
{
  "report_date": "2026-07-09",
  "raw_content": "今日完成：跟进3个客户...",
  "content": "AI 结构化后的日报内容",
  "key_progress": ["签约1个客户", "跟进5个线索"],
  "risks": ["张三客户流失风险较高"],
  "next_plan": "明日联系新线索5个"
}
```

> ⭐ 字段对齐 `employee_daily_report` 表：`raw_content`（原始输入）、`content`（AI结构化后）、`key_progress`（JSON 数组）、`risks`（JSON 数组）、`report_date`（DATE 类型）

**业务规则：**
1. ⭐ 同一员工同一天只能有一份日报（`uk_employee_date` 唯一索引约束，应用层 UPSERT 兜底）
2. `report_date` 不能是未来日期
3. ⭐ 支持 Dify 将口述内容结构化后通过 API 提交（走用户 Token 或 Dify Token）
4. 新建默认状态 `draft`，可提交为 `submitted`

### 6.7 GET `/api/v1/employee/daily-reports/summary` — 日报汇总

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `start_date` | date | 是 | 汇总起始日期 |
| `end_date` | date | 是 | 汇总截止日期 |

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "period": "2026-07-01 ~ 2026-07-07",
    "total_reports": 35,
    "reporting_rate": "87.5%",
    "risk_count": 2,
    "summary_by_department": [
      {
        "department_name": "咨询部",
        "report_count": 20,
        "risk_count": 1
      }
    ]
  }
}
```

**权限：**
- **员工**：只能看自己的汇总
- **经理**：看本部门汇总
- **管理员**：看全部汇总

---

## 7. 学生智能助手模块接口

### 7.1 接口清单

| 方法 | 路径 | 说明 | MVP | Dify白名单 |
|------|------|------|-----|-----------|
| POST | `/api/v1/student/leave-requests` | 提交请假申请 | P0 | - |
| GET | `/api/v1/student/leave-requests` | 查询请假记录 | P1 | - |
| PUT | `/api/v1/student/leave-requests/{request_id}/approve` | 审批请假 | P0 | - |
| POST | `/api/v1/student/feedback-tickets` | 提交投诉/建议 | P0 | - |
| GET | `/api/v1/student/feedback-tickets` | 查询投诉列表 | P1 | - |
| PUT | `/api/v1/student/feedback-tickets/{ticket_id}` | 处理投诉 | P0 | - |
| POST | `/api/v1/student/psych/record` | 记录心理交互 | P1 | ✅ |
| GET | `/api/v1/student/psych/alerts` | 查询心理预警 | P1 | - |
| PUT | `/api/v1/student/psych/alerts/{alert_id}` | 处理心理预警 | P1 | - |
| GET | `/api/v1/student/applications` | 查询申请进度 | P1 | ✅ |
| GET | `/api/v1/student/deadlines` | 查询 DDL | P1 | - |

### 7.2 POST `/api/v1/student/leave-requests` — 提交请假申请

> ⭐ 数据来源：`student_admin_service` 表（`service_type='leave'`）

**请求体：**

```json
{
  "student_id": 10,
  "service_type": "leave",
  "leave_type": "personal",
  "start_time": "2026-07-10T08:00:00",
  "end_time": "2026-07-12T18:00:00",
  "reason": "家中有事需处理",
  "attachment_url": null
}
```

> ⭐ 字段对齐 `student_admin_service` 表：`service_type`（`leave`/`exam_query`/`other`）、`leave_type`（`sick`/`personal`/`emergency`）、`start_time`/`end_time`（DATETIME）、`attachment_url`（文件路径）

**成功响应：**

```json
{
  "code": 0,
  "message": "请假申请已提交",
  "data": {
    "id": 1,
    "student_id": 10,
    "service_type": "leave",
    "leave_type": "personal",
    "start_time": "2026-07-10T08:00:00",
    "end_time": "2026-07-12T18:00:00",
    "status": "pending",
    "create_time": "2026-07-09T14:30:00"
  }
}
```

**业务规则：**
1. ⭐ 插入前校验 `student_id` 对应的 `sys_user` 存在且 `user_type='student'`
2. ⭐ 再校验 `student_info` 表中 `user_id = student_id` 的记录存在且 `status='active'`
3. `end_time` >= `start_time`
4. 新建状态 `pending`
5. ⭐ 数据写入 `student_admin_service` 表

**应用层校验（⭐ V1.1 新增 - 双重逻辑外键校验）：**

```python
def create_leave_request(db: Session, data: LeaveCreate):
    # 1. 校验学生用户存在
    student_user = db.query(SysUser).filter(
        SysUser.id == data.student_id,
        SysUser.user_type == 'student',
        SysUser.status == 'normal'
    ).first()
    if not student_user:
        raise ReferenceNotFoundError("学生用户", data.student_id)

    # 2. 校验学生扩展信息存在
    student_info = db.query(StudentInfo).filter(
        StudentInfo.user_id == data.student_id,
        StudentInfo.status == 'active'
    ).first()
    if not student_info:
        raise ReferenceNotFoundError("学生档案", data.student_id)

    # 3. 创建请假记录
    leave = StudentAdminService(
        student_id=data.student_id,
        service_type='leave',
        **data.model_dump(exclude={'student_id'})
    )
    db.add(leave)
    db.commit()
    return leave
```

### 7.3 PUT `/api/v1/student/leave-requests/{request_id}/approve` — 审批请假

**请求体：**

```json
{
  "action": "approve",
  "approval_comment": "已确认情况，批准请假"
}
```

或驳回：

```json
{
  "action": "reject",
  "approval_comment": "理由不充分，请补充说明"
}
```

**成功响应：**

```json
{
  "code": 0,
  "message": "审批完成",
  "data": {
    "id": 1,
    "status": "approved",
    "approver_id": 5,
    "approval_comment": "已确认情况，批准请假",
    "approval_time": "2026-07-09T15:00:00"
  }
}
```

> ⭐ 字段对齐 `student_admin_service` 表：`approver_id`、`approval_comment`、`approval_time`

**业务规则：**
1. 请假申请状态必须为 `pending`
2. 审批人必须是班主任（`team_leader`）或管理员（`admin`）
3. `action` 仅允许 `approve` 或 `reject`
4. ⭐ 审批后状态变为 `approved`/`rejected`（终态，不可回退）
5. ⭐ 使用条件更新防并发：`WHERE id=? AND status='pending'`

### 7.4 POST `/api/v1/student/feedback-tickets` — 提交投诉/建议

> ⭐ 数据来源：`student_feedback_ticket` 表

**请求体：**

```json
{
  "student_id": 10,
  "ticket_type": "complaint",
  "category": "教学质量",
  "title": "课程进度过快",
  "content": "雅思写作课程进度太快，跟不上...",
  "detail": "详细描述..."
}
```

> ⭐ 字段对齐 `student_feedback_ticket` 表：`ticket_type`（`complaint`/`suggestion`/`consult`）、`category`（分类）、`content`（摘要）、`detail`（详细内容）

**成功响应：**

```json
{
  "code": 0,
  "message": "工单已创建",
  "data": {
    "id": 1,
    "ticket_type": "complaint",
    "category": "教学质量",
    "status": "pending",
    "priority": "medium",
    "create_time": "2026-07-09T14:30:00"
  }
}
```

**业务规则：**
1. ⭐ `student_id` 必须对应 `sys_user` 中 `user_type='student'` 的用户
2. 新建状态 `pending`，默认优先级 `medium`
3. ⭐ 匿名投诉场景 `student_id` 可为 NULL（应用层不校验用户存在）

### 7.5 PUT `/api/v1/student/feedback-tickets/{ticket_id}` — 处理投诉

**请求体：**

```json
{
  "status": "resolved",
  "solution": "已安排补课，调整课程进度",
  "assignee_id": 5
}
```

**成功响应：**

```json
{
  "code": 0,
  "message": "工单已处理",
  "data": {
    "id": 1,
    "status": "resolved",
    "solution": "已安排补课，调整课程进度",
    "assignee_id": 5,
    "update_time": "2026-07-09T16:00:00"
  }
}
```

> ⭐ 字段对齐 `student_feedback_ticket` 表：`assignee_id`（指派处理人）、`solution`（解决方案）

**工单状态流转（⭐ 对齐数据库文档 8. 状态枚举字典）：**

```
pending → processing → resolved → closed（终态）
```

**业务规则：**
1. ⭐ 超过 3 天未处理（`status=pending`），`priority` 自动提升（`medium → high → urgent`）
2. ⭐ `closed` 为终态，关闭后不可回退
3. 处理完成记录 `solution` 和处理人 `assignee_id`
4. 学生可查看本人投诉进度
5. ⭐ 如果 `assignee_id` 不为空，校验 `sys_user` 中存在

### 7.6 POST `/api/v1/student/psych/record` — 记录心理交互（Dify 调用）

> ⭐ 数据来源：`student_psych_record` 表，触发写入 `student_psych_profile` 和 `student_psych_alert`

**请求体：**

```json
{
  "student_id": 10,
  "emotion_tag": "焦虑",
  "emotion_score": 35,
  "interaction_content": "学生在对话中表达了对即将到来的雅思考试的焦虑...",
  "trigger_keywords": ["考试", "压力", "睡不着"],
  "record_date": "2026-07-09"
}
```

> ⭐ 字段对齐 `student_psych_record` 表：`emotion_tag`、`emotion_score`（0-100）、`interaction_content`、`trigger_keywords`（JSON）、`record_date`（DATE）

**成功响应：**

```json
{
  "code": 0,
  "message": "心理记录已保存",
  "data": {
    "id": 1,
    "student_id": 10,
    "risk_level": "medium",
    "alert_created": true,
    "alert_id": 3
  }
}
```

**业务规则（心理预警触发 ⭐ 对齐数据库文档 6.6.6 节）：**

| 风险等级 | 触发条件 | 处理动作 |
|----------|----------|----------|
| `low` | `emotion_score` 40-60，无高危关键词 | 仅记录，建议关怀 |
| `medium` | `emotion_score` 20-40，出现压力关键词 | 创建预警（`student_psych_alert`），班主任跟进 |
| `high` | `emotion_score` < 20，出现高危关键词 | 立即预警，强制人工介入 |

**实现流程（⭐ V1.1 新增 - 心理数据写入事务）：**

```python
def record_psych_interaction(db: Session, data: PsychRecordCreate):
    # 1. 校验学生存在
    student = db.query(SysUser).filter(
        SysUser.id == data.student_id,
        SysUser.user_type == 'student'
    ).first()
    if not student:
        raise ReferenceNotFoundError("学生", data.student_id)

    with db.begin():
        # 2. 写入心理记录
        record = StudentPsychRecord(**data.model_dump())
        db.add(record)

        # 3. 更新/创建心理画像
        profile = db.query(StudentPsychProfile).filter(
            StudentPsychProfile.student_id == data.student_id
        ).first()
        if profile:
            profile.latest_emotion_tag = data.emotion_tag
            profile.emotion_score = data.emotion_score
            profile.last_interaction_time = func.now()
        else:
            profile = StudentPsychProfile(
                student_id=data.student_id,
                latest_emotion_tag=data.emotion_tag,
                emotion_score=data.emotion_score,
                last_interaction_time=func.now(),
                risk_level='low'
            )
            db.add(profile)

        # 4. 判断是否需要创建预警
        alert = None
        if data.emotion_score < 40:
            risk_level = 'high' if data.emotion_score < 20 else 'medium'
            alert = StudentPsychAlert(
                student_id=data.student_id,
                trigger_reason=f"情绪分值{data.emotion_score}，关键词：{data.trigger_keywords}",
                risk_level=risk_level,
                status='pending'
            )
            db.add(alert)
            profile.risk_level = risk_level

        db.flush()  # 获取 alert.id

    return {
        "id": record.id,
        "student_id": data.student_id,
        "risk_level": profile.risk_level,
        "alert_created": alert is not None,
        "alert_id": alert.id if alert else None
    }
```

**重要约束：**
1. AI 只做风险识别，不做医学诊断
2. `high` 预警必须进入人工处理流程
3. 心理数据仅授权角色可见（`teacher_id` + `admin`）
4. ⭐ 日志中不记录完整 `interaction_content`（心理原文不入日志）

### 7.7 GET `/api/v1/student/psych/alerts` — 查询心理预警

> ⭐ 数据来源：`student_psych_alert` 表

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `risk_level` | string | 否 | `low`/`medium`/`high` |
| `status` | string | 否 | `pending`/`following`/`resolved`/`dismissed` |
| `teacher_id` | int | 否 | 负责老师 ID |
| `page` | int | 否 | 页码 |
| `page_size` | int | 否 | 每页条数 |

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 3,
        "student_id": 10,
        "trigger_reason": "情绪分值35，关键词：考试、压力、睡不着",
        "risk_level": "medium",
        "status": "pending",
        "teacher_id": null,
        "create_time": "2026-07-09T14:30:00"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 20
  }
}
```

> ⭐ 字段对齐 `student_psych_alert` 表：`trigger_reason`、`teacher_id`、`follow_record`、`resolved_time`

**权限规则：**
- **学生**：只能看到自己的预警（脱敏展示）
- **班主任**：看到负责学生的预警（`student_info.class_teacher_id == current_user.id`）
- **管理员**：看到全部

### 7.8 PUT `/api/v1/student/psych/alerts/{alert_id}` — 处理心理预警

**请求体：**

```json
{
  "status": "following",
  "teacher_id": 5,
  "follow_record": "已联系学生，安排心理辅导..."
}
```

**业务规则：**
1. 仅班主任（`team_leader`）和管理员（`admin`）可处理
2. ⭐ 状态流转：`pending → following → resolved` 或 `pending → dismissed`
3. 重度预警升级后通过 `notification_log` 通知领导

---

## 8. 智能报告模块接口

### 8.1 接口清单

| 方法 | 路径 | 说明 | MVP | Dify白名单 |
|------|------|------|-----|-----------|
| POST | `/api/v1/reports/generate` | 触发报告生成 | P0 | - |
| GET | `/api/v1/reports` | 查询报告列表 | P1 | - |
| GET | `/api/v1/reports/{report_id}` | 获取报告详情 | P0 | - |

### 8.2 POST `/api/v1/reports/generate` — 触发报告生成

> ⭐ 数据来源：写入 `report_generation` 表，异步聚合各业务表数据

**请求体：**

```json
{
  "report_type": "daily_summary",
  "report_title": "2026年7月第1周日报汇总",
  "period_start": "2026-07-01",
  "period_end": "2026-07-07"
}
```

> ⭐ 字段对齐 `report_generation` 表：`report_type`（`customer_ops`/`daily_summary`/`weekly_summary`/`psych_weekly`/`complaint_weekly`）、`report_title`、`period_start`/`period_end`（DATE）

**报告类型枚举（⭐ 对齐数据库文档 6.7.1 节）：**

| 类型 | 说明 | 数据来源表 |
|------|------|----------|
| `customer_ops` | 全域客户经营分析 | `crm_lead`, `crm_follow_up` |
| `daily_summary` | 员工日报汇总 | `employee_daily_report` |
| `psych_weekly` | 学生心理周报 | `student_psych_record`, `student_psych_alert` |
| `complaint_weekly` | 投诉处理周报 | `student_feedback_ticket` |
| `weekly_summary` | 综合周报 | 多表聚合 |

**成功响应：**

```json
{
  "code": 0,
  "message": "报告生成任务已创建",
  "data": {
    "report_id": 1,
    "report_type": "daily_summary",
    "report_title": "2026年7月第1周日报汇总",
    "status": "generating",
    "create_time": "2026-07-09T14:30:00"
  }
}
```

**异步流程（⭐ 对齐数据库文档 14.4 节事务边界规范）：**

```text
1. 接收请求，创建 report_generation 记录（status=generating）→ 立即返回 report_id
2. BackgroundTasks 后台执行（不在请求事务中）：
   a. 独立事务 1：聚合业务表数据
   b. 调用 Dify 生成报告文本（事务外调用外部 API）
   c. 独立事务 2：保存 report_content（JSON）+ report_html（MEDIUMTEXT）
   d. 更新 status=completed / failed + error_message
3. 前端轮询 GET /api/v1/reports/{report_id} 获取结果
```

**⭐ 关键约束**：BackgroundTasks 中的数据库操作必须使用独立 Session，不在请求事务中执行。

```python
@router.post("/generate")
def trigger_report_generation(
    request: ReportGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # 1. 在请求事务中创建任务记录
    report = ReportGeneration(
        report_type=request.report_type,
        report_title=request.report_title,
        period_start=request.period_start,
        period_end=request.period_end,
        generated_by=current_user.id,
        status='generating'
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 2. 异步执行（使用独立 Session）
    background_tasks.add_task(generate_report_async, report.id)

    return success_response(data={
        "report_id": report.id,
        "status": "generating",
        "create_time": report.create_time.isoformat()
    })


# ⭐ 独立 Session 的异步任务
def generate_report_async(report_id: int):
    db = SessionLocal()  # 独立数据库会话
    try:
        # 1. 聚合数据（在事务中）
        report = db.query(ReportGeneration).filter_by(id=report_id).first()
        raw_data = aggregate_report_data(db, report)

        # 2. 调用 Dify（事务外）
        ai_result = call_dify_workflow(report.report_type, raw_data)

        # 3. 保存结果（独立事务）
        with db.begin():
            report.report_content = ai_result.content
            report.report_html = ai_result.html
            report.status = 'completed'
    except Exception as e:
        with db.begin():
            report.status = 'failed'
            report.error_message = str(e)[:500]
    finally:
        db.close()
```

### 8.3 GET `/api/v1/reports/{report_id}` — 获取报告详情

**成功响应（生成中）：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "report_type": "daily_summary",
    "report_title": "2026年7月第1周日报汇总",
    "status": "generating",
    "report_content": null,
    "report_html": null,
    "create_time": "2026-07-09T14:30:00"
  }
}
```

**成功响应（已完成）：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "report_type": "daily_summary",
    "report_title": "2026年7月第1周日报汇总",
    "period_start": "2026-07-01",
    "period_end": "2026-07-07",
    "status": "completed",
    "report_content": {
      "summary": "本周整体工作进展顺利...",
      "key_findings": ["客户咨询量环比增长15%", "签约转化率8.5%"],
      "risks": ["张三客户流失风险较高"],
      "suggestions": ["加强高意向客户跟进频率"]
    },
    "report_html": "<div>...</div>",
    "create_time": "2026-07-09T14:30:00"
  }
}
```

**成功响应（失败）：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "status": "failed",
    "error_message": "Dify 调用超时",
    "create_time": "2026-07-09T14:30:00"
  }
}
```

> ⭐ 字段对齐 `report_generation` 表：`report_content`（JSON）、`report_html`（MEDIUMTEXT）、`error_message`（TEXT）

---

## 9. 客户研判模块接口

### 9.1 接口清单

| 方法 | 路径 | 说明 | MVP | Dify白名单 |
|------|------|------|-----|-----------|
| POST | `/api/v1/profile/upload` | 上传客户资料 | P1 | - |
| GET | `/api/v1/profile/{source_id}` | 查询研判结果 | P1 | - |
| POST | `/api/v1/profile/{source_id}/analyze` | 触发 AI 研判 | P1 | - |
| GET | `/api/v1/profile/rules` | 查询画像规则 | P1 | - |

### 9.2 POST `/api/v1/profile/upload` — 上传客户资料

> ⭐ 数据来源：写入 `customer_source` 表，文件存本地 `uploads/` 目录

**Content-Type**：`multipart/form-data`

**表单参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | file | 否 | PDF/Excel 文件（最大 10MB） |
| `content_text` | string | 否 | 文本资料（对应 `raw_content` 字段） |
| `source_type` | string | 是 | `text`/`pdf_resume`/`excel`/`import`/`manual` |

> ⭐ `source_type` 枚举对齐 `customer_source` 表

**成功响应：**

```json
{
  "code": 0,
  "message": "资料已上传",
  "data": {
    "source_id": 1,
    "source_type": "pdf_resume",
    "file_name": "张三简历.pdf",
    "file_url": "/uploads/profiles/2026/07/abc123.pdf",
    "parse_status": "pending",
    "create_time": "2026-07-09T14:30:00"
  }
}
```

**业务规则：**
1. `file` 和 `content_text` 至少提供一个
2. 上传成功创建 `customer_source` 记录，`parse_status='pending'`
3. ⭐ 文件保存到本地 `uploads/profiles/` 目录，数据库只存 `file_url` 路径
4. 支持文件类型：pdf, xlsx, xls, txt, docx
5. ⭐ `operator_id` 记录操作人

### 9.3 POST `/api/v1/profile/{source_id}/analyze` — 触发 AI 研判

**成功响应：**

```json
{
  "code": 0,
  "message": "研判任务已启动",
  "data": {
    "source_id": 1,
    "parse_status": "pending"
  }
}
```

**异步流程（⭐ 对齐数据库文档无外键场景）：**

```text
1. 更新 customer_source.parse_status = 'pending'
2. BackgroundTasks 后台执行（独立 Session）：
   a. 解析上传文件/文本
   b. 读取 profile_rule 画像规则（按 product_line + priority 排序）
   c. 调用 Dify Workflow 进行 AI 研判（事务外）
   d. 写入 customer_profile（逻辑关联 customer_source.id）
   e. 更新 customer_source.parse_status = 'success' / 'failed'
```

### 9.4 GET `/api/v1/profile/{source_id}` — 查询研判结果

> ⭐ 数据来源：关联查询 `customer_source` + `customer_profile`（通过 `source_id` 逻辑关联）

**成功响应（研判成功）：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "source_id": 1,
    "source_type": "pdf_resume",
    "file_url": "/uploads/profiles/2026/07/abc123.pdf",
    "parse_status": "success",
    "customer_name": "张三",
    "contact_info": "138****0001",
    "background_info": {
      "education": "本科",
      "target_country": ["英国", "澳大利亚"],
      "target_major": "计算机"
    },
    "match_result": "matched",
    "matched_product": "留学申请",
    "match_score": 85.50,
    "match_reason": "学历背景、目标国家和专业方向符合产品要求",
    "recommended_programs": [
      {"program_name": "英国硕士直通车", "score": 90}
    ],
    "create_time": "2026-07-09T14:30:00"
  }
}
```

> ⭐ 字段对齐 `customer_profile` 表：`match_result`（`matched`/`partial`/`not_matched`）、`match_score`（DECIMAL(5,2)）、`recommended_programs`（JSON）

---

## 10. Dify 工具 API（白名单）

### 10.1 白名单机制说明

Dify 通过 HTTP 请求节点调用 FastAPI 时，使用独立的 `DIFY_SERVICE_TOKEN` 进行鉴权。白名单内的接口不校验用户 JWT，而是校验服务 Token。

**鉴权方式：**

```text
Authorization: Bearer {DIFY_SERVICE_TOKEN}
```

### 10.2 白名单接口汇总

| 方法 | 路径 | 场景 | MVP | 数据库表 |
|------|------|------|-----|----------|
| GET | `/api/v1/courses` | 课程查询 | P0 | `course_project` |
| GET | `/api/v1/events` | 活动查询 | P0 | `event_lecture` |
| POST | `/api/v1/events/{event_id}/register` | 活动报名 | P0 | `event_registration` |
| GET | `/api/v1/crm/leads` | 客户查询 | P1 | `crm_lead` |
| POST | `/api/v1/chat/session` | 创建会话 | P1 | `chat_session` |
| POST | `/api/v1/student/psych/record` | 心理记录 | P1 | `student_psych_record` |
| GET | `/api/v1/student/applications` | 申请进度查询 | P1 | `application_progress` |

### 10.3 白名单接口约束

1. Dify 调用的接口返回格式必须稳定，不能随意变更字段名
2. 接口响应时间控制在 15 秒以内（Dify HTTP 节点超时配置）
3. 返回数据量不宜过大，建议单次返回不超过 50 条
4. ⭐ 白名单接口的参数校验可以比用户接口宽松（Dify 传参由工作流控制）
5. 禁止在白名单中添加删除类接口
6. ⭐ 白名单接口的 `operator_id` 默认为系统账号（Dify 调用无法关联具体用户）

### 10.4 Dify Service Token 校验实现

```python
# utils/security.py
from fastapi import Header, HTTPException, Depends
from config import settings


def verify_dify_service_token(authorization: str = Header(...)) -> None:
    """校验 Dify 服务 Token，与用户 JWT 分离"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "message": "无效的服务令牌", "data": None}
        )

    token = authorization.replace("Bearer ", "").strip()
    if token != settings.DIFY_SERVICE_TOKEN:
        raise HTTPException(
            status_code=403,
            detail={"code": 40301, "message": "服务令牌校验失败", "data": None}
        )


# 在 Dify 白名单路由中使用
# router.get("/courses", dependencies=[Depends(verify_dify_service_token)])
```

---

## 11. 异步任务接口规范

### 11.1 异步任务模式

对于耗时 AI 操作，统一采用 **"提交任务 → 查询结果"** 的异步模式。

```text
提交任务                   查询结果
┌──────────┐              ┌──────────┐
│ POST /xx │              │ GET /xx  │
│          │──→ source_id─→│          │
│ 立即返回  │              │ 轮询状态  │
│ status:  │              │ 获取结果  │
│ pending  │              │          │
└──────────┘              └──────────┘
     │                         ↑
     │    BackgroundTasks      │
     └─────────────────────────┘
        异步执行 → 更新状态
        ⭐ 使用独立 Session
        ⭐ 事务外调用外部 API
```

### 11.2 异步接口列表

| 接口 | 提交 | 查询 | 状态字段 | 数据库表 |
|------|------|------|----------|----------|
| 客户研判 | `POST /api/v1/profile/upload` | `GET /api/v1/profile/{source_id}` | `customer_source.parse_status` | `customer_source` |
| 报告生成 | `POST /api/v1/reports/generate` | `GET /api/v1/reports/{report_id}` | `report_generation.status` | `report_generation` |

### 11.3 异步任务通用状态

| 状态 | 含义 | 后续操作 |
|------|------|----------|
| `pending` | 已提交，等待处理 | 继续轮询 |
| `processing` / `generating` | 正在执行 | 继续轮询 |
| `success` / `completed` | 执行成功 | 获取结果 |
| `failed` | 执行失败 | 查看 `error_message`，可重试 |

### 11.4 前端轮询建议

```javascript
async function pollTaskStatus(taskId, queryUrl, interval = 2000, maxAttempts = 60) {
  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch(queryUrl);
    const data = await response.json();
    const status = data.data.status || data.data.parse_status;
    if (status === 'success' || status === 'completed') {
      return data.data;
    }
    if (status === 'failed') {
      throw new Error(data.data.error_message);
    }
    await new Promise(resolve => setTimeout(resolve, interval));
  }
  throw new Error('任务超时');
}
```

### 11.5 ⭐ 异步任务事务边界规范（V1.1 新增）

```python
# ⭐ 核心原则：
# 1. 请求处理中只做"创建任务记录 + 提交后台任务"
# 2. 后台任务使用独立 Session
# 3. 外部 API 调用在事务外执行

# ============================================
# 正确示例：报告生成
# ============================================
@router.post("/generate")
def trigger_report(request: ReportGenerateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # ✅ 请求事务：创建任务记录
    report = ReportGeneration(status='generating', **request.model_dump())
    db.add(report)
    db.commit()       # ← 提交后释放连接
    report_id = report.id

    # ✅ 异步任务使用独立 Session
    background_tasks.add_task(generate_report_async, report_id)
    return success_response(data={"report_id": report_id, "status": "generating"})


def generate_report_async(report_id: int):
    db = SessionLocal()     # ← 独立 Session
    try:
        report = db.query(ReportGeneration).filter_by(id=report_id).first()
        raw_data = aggregate_data(db, report)   # 聚合数据

        ai_result = call_dify(raw_data)         # ← 事务外调用 Dify

        with db.begin():                        # ← 独立事务保存结果
            report.report_content = ai_result
            report.status = 'completed'
    except Exception as e:
        with db.begin():
            report.status = 'failed'
            report.error_message = str(e)[:500]
    finally:
        db.close()
```

---

## 12. 分页、排序、筛选规范

### 12.1 分页参数标准化

所有列表查询接口统一使用以下分页参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `page` | int | 否 | 1 | 页码，从 1 开始 |
| `page_size` | int | 否 | 20 | 每页条数，最大 100 |

**分页响应格式：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

### 12.2 ⭐ 游标分页（深分页场景）

> ⭐ 对齐数据库文档 V2.1 12.2 节：大数据量场景使用游标分页替代 OFFSET

**适用场景**：`chat_message`、`crm_follow_up`、`notification_log` 等数据量增长快的表。

```text
GET /api/v1/chat/session/{session_id}/messages?cursor=100&limit=20
```

**响应格式：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [],
    "next_cursor": 120,
    "has_more": true
  }
}
```

**实现原理**（⭐ 对齐数据库文档游标分页 SQL）：

```python
def query_messages_cursor(db: Session, session_id: str, cursor: int = None, limit: int = 20):
    query = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.id.desc())

    if cursor:
        query = query.filter(ChatMessage.id < cursor)  # 游标分页

    messages = query.limit(limit + 1).all()  # 多取 1 条判断 has_more
    has_more = len(messages) > limit
    items = messages[:limit]

    next_cursor = items[-1].id if items else None
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}
```

### 12.3 排序参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `sort_by` | string | 否 | `create_time` | 排序字段 |
| `sort_order` | string | 否 | `desc` | 排序方向：asc/desc |

**排序白名单校验（防 SQL 注入 ⭐ 对齐数据库索引字段）：**

```python
# ⭐ 白名单字段必须与数据库实际索引字段对齐
ALLOWED_SORT_FIELDS = {
    "courses":      ["id", "project_name", "price", "create_time", "category"],
    "events":       ["id", "event_name", "start_time", "create_time", "status"],
    "leads":        ["id", "customer_name", "status", "create_time", "update_time", "last_contact_time"],
    "follow_ups":   ["id", "lead_id", "create_time"],
    "daily_reports": ["id", "report_date", "create_time"],
    "leave":        ["id", "student_id", "start_time", "create_time", "status"],
    "tickets":      ["id", "student_id", "status", "priority", "create_time"],
    "psych_alerts": ["id", "student_id", "risk_level", "status", "create_time"],
    "reports":      ["id", "report_type", "create_time"],
    "applications": ["id", "student_id", "next_deadline", "create_time"],
    "deadlines":    ["id", "deadline_date", "create_time"],
}

def validate_sort_params(resource: str, sort_by: str, sort_order: str):
    allowed = ALLOWED_SORT_FIELDS.get(resource, ["create_time"])
    if sort_by not in allowed:
        sort_by = "create_time"  # 默认安全字段
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    return sort_by, sort_order
```

### 12.4 通用查询过滤器（Pydantic Schema）

```python
# schemas/common.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


class PaginationParams(BaseModel):
    """通用分页参数"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return min(self.page_size, 100)


class CursorPaginationParams(BaseModel):
    """⭐ 游标分页参数（深分页场景）"""
    cursor: Optional[int] = Field(default=None, description="游标 ID")
    limit: int = Field(default=20, ge=1, le=100, description="每页条数")


class DateRangeParams(BaseModel):
    """日期范围查询"""
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class SortParams(BaseModel):
    """排序参数"""
    sort_by: str = Field(default="create_time", description="排序字段")
    sort_order: str = Field(default="desc", description="排序方向 asc/desc")
```

### 12.5 ⭐ 索引覆盖优化建议（V1.1 新增）

API 查询设计时应尽量利用数据库已有的覆盖索引，避免回表：

```python
# 示例：查询客户列表时，只返回索引覆盖的字段
# 数据库索引：KEY `idx_cover_status_time` (`status`, `create_time`, `id`)
# API 返回字段限制在 status, create_time, id 内，可完全走覆盖索引

# 如果需要返回其他字段（如 customer_name），则必须回表
# 高频查询应尽量精简返回字段
```

---

## 13. 安全与鉴权规范

### 13.1 双 Token 机制

| Token 类型 | 用途 | 格式 | 有效期 |
|-----------|------|------|--------|
| 用户 JWT | 前端/用户请求 | `Authorization: Bearer {jwt}` | 24 小时 |
| Dify Service Token | Dify HTTP 节点请求 | `Authorization: Bearer {service_token}` | 配置固定 |

### 13.2 JWT Token 设计

```python
# JWT Payload
{
  "sub": 1,              # user_id
  "username": "admin",
  "user_type": "admin",   # ⭐ 对齐 sys_user.user_type
  "role_id": 1,           # ⭐ 对齐 sys_user.role_id
  "exp": 1750000000,
  "iat": 1749913600
}
```

### 13.3 权限校验层级

```text
接口级权限：路由层 → Depends(require_role("admin", "manager"))
数据级权限：Service 层 → 按 owner_employee_id / student_id 过滤
字段级权限：Schema 层 → 按角色控制返回字段（心理原文仅授权角色可见）
```

**权限依赖注入示例：**

```python
# utils/security.py
from fastapi import Depends, HTTPException
from typing import List


def require_auth():
    """要求用户已登录"""
    pass


def require_role(allowed_roles: List[str]):
    """要求用户属于指定角色"""
    def role_checker(current_user = Depends(require_auth)):
        if current_user.user_type not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail={"code": 40301, "message": "无权限访问", "data": None}
            )
        return current_user
    return role_checker


def require_owner_or_admin(resource_owner_field: str = "owner_employee_id"):
    """要求用户是资源所有者或管理员"""
    pass
```

### 13.4 ⭐ 数据越权防护（对齐数据库文档 V2.1 第 9 章）

Service 层查询时自动添加数据权限过滤：

```python
# services/crm_service.py
def query_leads(db: Session, current_user, filters: dict):
    query = db.query(CRMLead)

    # ⭐ 数据权限：按数据库文档 9.1 节数据隔离策略
    if current_user.user_type == 'employee':
        # CRM 客户数据：负责人
        query = query.filter(CRMLead.owner_employee_id == current_user.id)
    elif current_user.user_type == 'manager':
        # 经理看本部门（通过 sys_user.department 过滤）
        department_users = db.query(SysUser.id).filter(
            SysUser.department == current_user.department
        ).subquery()
        query = query.filter(CRMLead.owner_employee_id.in_(department_users))

    # 应用业务过滤条件
    if filters.get("status"):
        query = query.filter(CRMLead.status == filters["status"])

    return query
```

### 13.5 ⭐ 数据隔离矩阵（对齐数据库文档 V2.1 第 9 章）

| 数据类型 | 隔离字段 | 授权可见范围 | API 实现 |
|---------|---------|-------------|---------|
| 学生扩展信息 | `student_info.class_teacher_id` | 学生本人 + 班主任 + 管理员 | Service 层过滤 |
| 学生请假记录 | `student_admin_service.student_id` | 学生本人 + 班主任 + 管理员 | Service 层过滤 |
| 学生心理画像 | `student_psych_profile.student_id` | 学生本人 + 授权老师 + 管理员 | Service 层过滤 |
| 学生心理记录 | `student_psych_record.student_id` | 仅授权老师 + 管理员 | Service 层过滤 |
| 学生心理预警 | `student_psych_alert.student_id` | 仅授权老师 + 管理员 | Service 层过滤 |
| 学生投诉工单 | `student_feedback_ticket.student_id` | 学生本人 + 处理人 + 管理员 | Service 层过滤 |
| CRM 客户数据 | `crm_lead.owner_employee_id` | 负责人 + 管理员 | Service 层过滤 |
| 员工日报 | `employee_daily_report.employee_id` | 员工本人 + 直属上级 + 管理员 | Service 层过滤 |

### 13.6 安全约束清单

| # | 约束 | 说明 |
|---|------|------|
| 1 | 密码 bcrypt 存储 | cost=12，不允许明文 |
| 2 | Token 不暴露在 URL | 仅通过 Header 传递 |
| 3 | API Key 存 .env | `DIFY_API_KEY`, `DIFY_SERVICE_TOKEN`, `SECRET_KEY` 不入库 |
| 4 | 日志脱敏 | 不记录密码、Token、心理原文 |
| 5 | SQL 参数化查询 | SQLAlchemy ORM 防注入 |
| 6 | 文件上传限制 | 类型白名单 + 大小限制（10MB） |
| 7 | 心理数据隔离 | 仅授权角色可见，`interaction_content` 不入日志 |
| 8 | 投诉匿名保护 | 匿名投诉不关联真实身份（`student_id=NULL`） |
| 9 | ⭐ 逻辑外键校验 | 所有 `xxx_id` 字段在应用层校验对应记录存在 |

---

## 14. ⭐ 应用层数据一致性保障（无外键场景）

> **本章为 V1.1 新增，V1.2 复核**，对齐《数据库设计规范文档 V2.1》第 5 章和第 14 章。

### 14.1 核心原则

由于数据库全面禁用物理外键，所有表间关系通过 `{entity}_id` 字段 + 索引 + **应用层逻辑**维护。API 接口层是应用层数据一致性的第一道防线。

### 14.2 逻辑外键存在性校验规范

**所有创建/更新接口中涉及 `xxx_id` 字段时，必须校验对应实体存在。**

```python
# utils/validators.py（⭐ 对齐数据库文档 14.1 节）
from functools import wraps
from sqlalchemy.orm import Session

def validate_entity_exists(entity_model, field_name: str, error_entity_name: str):
    """校验逻辑外键指向的实体是否存在"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            entity_id = kwargs.get(field_name)
            if entity_id is not None:
                session: Session = kwargs.get('db')
                exists = session.query(
                    session.query(entity_model)
                    .filter_by(id=entity_id)
                    .exists()
                ).scalar()
                if not exists:
                    raise ReferenceNotFoundError(error_entity_name, entity_id)
            return func(*args, **kwargs)
        return wrapper
    return decorator


# 使用示例
@validate_entity_exists(SysUser, 'student_id', '学生')
def create_leave_application(db: Session, student_id: int, **data):
    ...
```

### 14.3 ⭐ 接口级逻辑外键校验清单

| 接口 | 校验的 `xxx_id` | 校验目标表 | 校验条件 |
|------|----------------|-----------|---------|
| `POST /events/{id}/register` | `event_id` | `event_lecture` | 存在 + `status='upcoming'` |
| `POST /events/{id}/register` | `user_id` | `sys_user` | 存在（如果非 NULL） |
| `POST /crm/leads` | `owner_employee_id` | `sys_user` | 存在 + `user_type='employee'` + `status='normal'` |
| `POST /crm/leads/{id}/follow-ups` | `lead_id` | `crm_lead` | 存在 |
| `POST /student/leave-requests` | `student_id` | `sys_user` + `student_info` | 存在 + `user_type='student'` + `status='active'` |
| `PUT /student/leave-requests/{id}/approve` | `approver_id` | `sys_user` | 存在 |
| `POST /student/feedback-tickets` | `student_id` | `sys_user` | 存在 + `user_type='student'`（非匿名时） |
| `PUT /student/feedback-tickets/{id}` | `assignee_id` | `sys_user` | 存在（如果非 NULL） |
| `POST /student/psych/record` | `student_id` | `sys_user` | 存在 + `user_type='student'` |
| `POST /employee/daily-reports` | `employee_id` | `sys_user` | 存在 + `user_type='employee'` |
| `POST /reports/generate` | `generated_by` | `sys_user` | 存在 |

### 14.4 ⭐ 级联操作规范（对齐数据库文档 14.2 节）

```python
# services/cascade_service.py
# ⭐ 无物理外键场景下的级联操作

def cancel_event(db: Session, event_id: int):
    """取消活动，批量取消报名（⭐ 对齐数据库文档 14.2 节）"""
    with db.begin():
        # 1. 锁定活动行
        event = db.query(EventLecture).filter_by(
            id=event_id, status='upcoming'
        ).with_for_update().first()
        if not event:
            raise NotFoundError("活动不存在或已结束")

        # 2. 批量取消报名（应用层级联）
        db.query(EventRegistration).filter_by(
            event_id=event_id, status='registered'
        ).update({"status": "cancelled"}, synchronize_session=False)

        # 3. 更新活动状态
        event.status = 'cancelled'
    # 事务自动提交


def soft_delete_lead(db: Session, lead_id: int):
    """软删除意向客户，同步处理关联数据（⭐ 对齐数据库文档 14.2 节）"""
    with db.begin():
        # 1. 标记关联跟进记录为无效
        db.query(CRMFollowUp).filter_by(lead_id=lead_id).update(
            {"is_deleted": 1}, synchronize_session=False
        )
        # 2. 软删除客户
        result = db.query(CRMLead).filter_by(id=lead_id).update(
            {"status": "lost", "lost_reason": "数据清理", "is_deleted": 1}
        )
        if result == 0:
            raise NotFoundError("客户不存在")
    return {"lead_id": lead_id, "status": "deleted"}
```

### 14.5 ⭐ 事务边界规范（对齐数据库文档 14.4 节）

```text
⭐ 事务原则:
  [ ] 一个业务操作 = 一个事务（原子性）
  [ ] 事务尽量短小（< 1 秒）
  [ ] 不在事务中调用外部 API（Dify、邮件、短信）
  [ ] 不在事务中进行文件 IO（文件上传在事务前完成）
  [ ] 使用 with db.begin() 确保事务正确提交/回滚
  [ ] 高并发场景使用 SELECT ... FOR UPDATE（悲观锁）
  [ ] 低并发场景可使用乐观锁（version 字段或条件 UPDATE）
  [ ] 异步任务使用独立 Session（不在请求 Session 中执行）
```

**错误示例 vs 正确示例：**

```python
# ❌ 错误：事务中调用 Dify
with db.begin():
    lead = create_lead(db, data)
    ai_result = call_dify(lead)  # ← 事务中调用外部 API！
    lead.ai_tags = ai_result

# ✅ 正确：先提交事务，再调用外部 API
with db.begin():
    lead = create_lead(db, data)
# 事务已提交
ai_result = call_dify(lead)  # ← 事务外调用
with db.begin():
    lead.ai_tags = ai_result
```

### 14.6 ⭐ 数据一致性检查接口（P2 预留）

建议提供管理后台接口触发一致性检查：

```python
# GET /api/v1/admin/consistency-check（仅管理员）
# 返回各检查项的结果

CHECKS = [
    {
        "name": "孤立报名记录",
        "description": "event_registration 中存在 event_id 对应的 event_lecture 已删除的记录",
        "sql": """
            SELECT er.id, er.event_id
            FROM event_registration er
            LEFT JOIN event_lecture el ON er.event_id = el.id
            WHERE el.id IS NULL AND er.status != 'cancelled'
        """
    },
    {
        "name": "孤立跟进记录",
        "description": "crm_follow_up 中存在 lead_id 对应的 crm_lead 已删除的记录",
        "sql": """
            SELECT cf.id, cf.lead_id
            FROM crm_follow_up cf
            LEFT JOIN crm_lead cl ON cf.lead_id = cl.id
            WHERE cl.id IS NULL
        """
    },
    {
        "name": "学生信息与用户表不一致",
        "description": "student_info 中 user_id 对应的 sys_user 不存在或 user_type 不是 student",
        "sql": """
            SELECT si.id, si.user_id
            FROM student_info si
            LEFT JOIN sys_user su ON si.user_id = su.id
            WHERE su.id IS NULL OR su.user_type != 'student'
        """
    },
]
```

---

## 15. Swagger 文档配置

### 15.1 FastAPI 配置

```python
# main.py
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="教育服务系统 API",
    description="""
## 教育服务系统（留学服务智能平台）API 文档

基于 FastAPI + Dify + MySQL 的 AI 驱动教育服务系统。

⭐ 数据库无物理外键，所有关联关系通过应用层维护。

### 模块
- **认证**：用户登录与鉴权
- **客服 Agent**：课程查询、活动报名、会话管理
- **企业助手**：CRM 客户管理、日报提交与汇总
- **学生助手**：请假审批、投诉处理、心理预警
- **智能报告**：报告生成与查询
- **客户研判**：资料上传与 AI 画像研判
    """,
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
)

# 添加 Dify Service Token 认证方式到 Swagger
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "用户 JWT Token"
        },
        "DifyServiceToken": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Service Token",
            "description": "Dify HTTP 节点调用 FastAPI 的服务令牌"
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

### 15.2 路由标签分组

```python
# routers/__init__.py 汇总
routers = [
    (health_router,             ["基础设施"]),
    (auth_router,               ["认证"]),
    (course_router,             ["客服 Agent - 课程"]),
    (event_router,              ["客服 Agent - 活动"]),
    (chat_router,               ["客服 Agent - 会话"]),
    (crm_router,                ["企业助手 - CRM"]),
    (daily_report_router,       ["企业助手 - 日报"]),
    (student_leave_router,      ["学生助手 - 请假"]),
    (student_feedback_router,   ["学生助手 - 投诉"]),
    (student_psych_router,      ["学生助手 - 心理"]),
    (student_app_router,        ["学生助手 - 申请进度"]),
    (report_router,             ["智能报告"]),
    (profile_router,            ["客户研判"]),
    (admin_router,              ["⭐ 管理后台 - 一致性检查"]),  # V1.1 新增
]
```

### 15.3 接口描述规范

每个接口必须包含：
- `summary`：简短描述
- `description`：详细说明（含业务规则、⭐ 逻辑外键校验说明）
- `response_description`：响应说明
- `responses`：各状态码响应示例

```python
@router.post(
    "/events/{event_id}/register",
    summary="活动报名",
    description="""
    用户报名参加指定活动。

    **业务规则：**
    - 活动必须存在且状态为 upcoming
    - 报名人数不得超过最大人数
    - 同一用户不允许重复报名（uk_event_user 唯一索引兜底）
    - 并发报名使用 SELECT ... FOR UPDATE 行锁
    - ⭐ 无物理外键：应用层校验 event_id 和 user_id 对应记录存在

    **数据来源：**
    - event_lecture（活动）
    - event_registration（报名记录）
    """,
    response_description="报名成功返回报名信息",
    responses={
        200: {"description": "报名成功"},
        404: {"description": "活动不存在或用户不存在"},
        409: {"description": "重复报名或状态冲突"},
        422: {"description": "名额已满"},
    }
)
```

---

## 16. 接口测试与验收清单

### 16.1 P0 接口测试清单

```text
[ ] GET  /api/v1/health                         → 返回 healthy
[ ] POST /api/v1/auth/login                     → 返回 Token
[ ] GET  /api/v1/auth/me                        → 返回用户信息
[ ] GET  /api/v1/courses                        → 返回课程列表（status=1）
[ ] GET  /api/v1/courses?category=语言培训        → 筛选正确
[ ] GET  /api/v1/events                         → 返回活动列表（status=upcoming）
[ ] GET  /api/v1/events?status=upcoming         → 仅 upcoming
[ ] POST /api/v1/events/1/register              → 报名成功
[ ] POST /api/v1/events/1/register（重复）        → 返回 409（uk_event_user 约束）
[ ] POST /api/v1/events/1/register（名额满）       → 返回 422
[ ] POST /api/v1/crm/leads                      → 创建客户
[ ] GET  /api/v1/crm/leads                      → 客户列表（权限过滤）
[ ] PUT  /api/v1/crm/leads/1/status             → 状态变更
[ ] POST /api/v1/crm/leads/1/follow-ups         → 跟进记录
[ ] POST /api/v1/student/leave-requests         → 提交请假
[ ] PUT  /api/v1/student/leave-requests/1/approve → 审批请假
[ ] POST /api/v1/student/feedback-tickets       → 提交投诉
[ ] PUT  /api/v1/student/feedback-tickets/1     → 处理投诉
[ ] POST /api/v1/reports/generate               → 触发报告（status=generating）
[ ] GET  /api/v1/reports/1                      → 报告详情（轮询）
```

### 16.2 ⭐ 逻辑外键校验测试（V1.1 新增）

```text
[ ] POST /events/999/register                   → 返回 40402（活动不存在）
[ ] POST /events/1/register (user_id=999)       → 返回 40402（用户不存在）
[ ] POST /crm/leads (owner_employee_id=999)     → 返回 40402（员工不存在）
[ ] POST /crm/leads/1/follow-ups (lead_id=999)  → 返回 40402（客户不存在）
[ ] POST /student/leave-requests (student_id=999) → 返回 40402（学生不存在）
[ ] POST /student/psych/record (student_id=999) → 返回 40402（学生不存在）
```

### 16.3 Dify 联调测试

```text
[ ] Dify HTTP 节点 GET /api/v1/courses           → 返回课程 JSON
[ ] Dify HTTP 节点 GET /api/v1/events            → 返回活动 JSON
[ ] Dify HTTP 节点 POST /api/v1/events/1/register → 报名成功
[ ] Dify Service Token 校验                      → 错误 Token 返回 403
[ ] Dify 调用非白名单接口                         → 返回 403
```

### 16.4 权限测试

```text
[ ] 未登录访问受保护接口                         → 返回 401
[ ] 员工访问其他员工的客户（owner_employee_id 不匹配） → 返回空列表
[ ] 学生访问其他学生的心理记录                    → 返回空列表/403
[ ] 普通员工访问管理接口                          → 返回 403
```

### 16.5 异常场景测试

```text
[ ] 不存在的活动报名                             → 返回 40401
[ ] 不存在的客户更新状态                          → 返回 40401
[ ] 已审批的请假重复审批                          → 返回 40902
[ ] 终态客户回退到 new（signed→new）              → 返回 40902
[ ] 提交缺少必填字段的请求                        → 返回 40001
[ ] Dify 服务不可用时生成报告                     → 返回 50201
[ ] ⭐ 并发报名最后名额（FOR UPDATE 锁测试）       → 仅 1 人成功
```

### 16.6 ⭐ 数据一致性测试（V1.1 新增）

```text
[ ] 取消活动后报名记录状态更新                     → event_registration.status → cancelled
[ ] 删除客户后跟进记录同步处理                     → crm_follow_up 同步软删除
[ ] 事务中异常自动回滚                            → 数据无残留
```

---

## 17. 附录

### 附录 A：P0 接口完整清单（MVP 必做）

| # | 方法 | 路径 | 模块 | 数据库表 |
|---|------|------|------|----------|
| 1 | GET | `/api/v1/health` | 基础 | - |
| 2 | POST | `/api/v1/auth/login` | 认证 | `sys_user` |
| 3 | GET | `/api/v1/auth/me` | 认证 | `sys_user` |
| 4 | GET | `/api/v1/courses` | 客服 Agent | `course_project` |
| 5 | GET | `/api/v1/events` | 客服 Agent | `event_lecture` |
| 6 | POST | `/api/v1/events/{event_id}/register` | 客服 Agent | `event_registration` |
| 7 | GET | `/api/v1/crm/leads` | 企业助手 | `crm_lead` |
| 8 | POST | `/api/v1/crm/leads` | 企业助手 | `crm_lead` |
| 9 | PUT | `/api/v1/crm/leads/{lead_id}/status` | 企业助手 | `crm_lead` |
| 10 | POST | `/api/v1/crm/leads/{lead_id}/follow-ups` | 企业助手 | `crm_follow_up` |
| 11 | POST | `/api/v1/student/leave-requests` | 学生助手 | `student_admin_service` |
| 12 | PUT | `/api/v1/student/leave-requests/{request_id}/approve` | 学生助手 | `student_admin_service` |
| 13 | POST | `/api/v1/student/feedback-tickets` | 学生助手 | `student_feedback_ticket` |
| 14 | PUT | `/api/v1/student/feedback-tickets/{ticket_id}` | 学生助手 | `student_feedback_ticket` |
| 15 | POST | `/api/v1/reports/generate` | 智能报告 | `report_generation` |
| 16 | GET | `/api/v1/reports/{report_id}` | 智能报告 | `report_generation` |

**P0 共计 16 个接口**，覆盖 4 条答辩演示主线。

### 附录 B：P1 接口清单（建议完成）

| # | 方法 | 路径 | 模块 | 数据库表 |
|---|------|------|------|----------|
| 1 | GET | `/api/v1/courses/{course_id}` | 课程详情 | `course_project` |
| 2 | GET | `/api/v1/events/{event_id}` | 活动详情 | `event_lecture` |
| 3 | DELETE | `/api/v1/events/{event_id}/register` | 取消报名 | `event_registration` |
| 4 | POST | `/api/v1/chat/session` | 创建会话 | `chat_session` |
| 5 | GET | `/api/v1/crm/leads/{lead_id}` | 客户详情 | `crm_lead` |
| 6 | PUT | `/api/v1/crm/leads/{lead_id}` | 更新客户 | `crm_lead` |
| 7 | GET | `/api/v1/crm/leads/{lead_id}/follow-ups` | 跟进历史 | `crm_follow_up` |
| 8 | POST | `/api/v1/employee/daily-reports` | 提交日报 | `employee_daily_report` |
| 9 | GET | `/api/v1/employee/daily-reports` | 查询日报 | `employee_daily_report` |
| 10 | GET | `/api/v1/employee/daily-reports/summary` | 日报汇总 | `employee_daily_report` |
| 11 | GET | `/api/v1/student/leave-requests` | 查询请假 | `student_admin_service` |
| 12 | GET | `/api/v1/student/feedback-tickets` | 投诉列表 | `student_feedback_ticket` |
| 13 | POST | `/api/v1/student/psych/record` | 心理记录 | `student_psych_record` |
| 14 | GET | `/api/v1/student/psych/alerts` | 心理预警列表 | `student_psych_alert` |
| 15 | PUT | `/api/v1/student/psych/alerts/{alert_id}` | 处理预警 | `student_psych_alert` |
| 16 | GET | `/api/v1/student/applications` | 申请进度 | `application_progress` |
| 17 | GET | `/api/v1/student/deadlines` | 查询 DDL | `academic_deadline` |
| 18 | GET | `/api/v1/reports` | 报告列表 | `report_generation` |
| 19 | POST | `/api/v1/profile/upload` | 上传资料 | `customer_source` |
| 20 | GET | `/api/v1/profile/{source_id}` | 研判结果 | `customer_source` + `customer_profile` |

### 附录 C：Dify HTTP 节点配置参考

| 配置项 | 值 |
|--------|-----|
| 请求方式 | POST / GET |
| URL 模板 | `http://host.docker.internal:8000/api/v1/{path}` |
| 请求头 Authorization | `Bearer {{DIFY_SERVICE_TOKEN}}` |
| Content-Type | `application/json` |
| 超时时间 | 15 秒 |
| 重试次数 | 0（不自动重试，由 Dify 工作流控制） |
| 返回处理 | 解析 `data` 字段传递给 LLM 节点 |

### 附录 D：接口与需求对照表

| 需求编号 | 需求描述 | 对应接口 | 数据库表 |
|----------|----------|----------|----------|
| CS-003 | 查询课程列表 | `GET /api/v1/courses` | `course_project` |
| CS-004 | 查询活动列表 | `GET /api/v1/events` | `event_lecture` |
| CS-005 | 活动报名 | `POST /api/v1/events/{id}/register` | `event_registration` |
| EA-001 | 新增意向客户 | `POST /api/v1/crm/leads` | `crm_lead` |
| EA-002 | 查询意向客户 | `GET /api/v1/crm/leads` | `crm_lead` |
| EA-003 | 更新客户状态 | `PUT /api/v1/crm/leads/{id}/status` | `crm_lead` |
| EA-004 | 新增跟进记录 | `POST /api/v1/crm/leads/{id}/follow-ups` | `crm_follow_up` |
| EA-006 | 提交日报 | `POST /api/v1/employee/daily-reports` | `employee_daily_report` |
| EA-008 | 日报汇总 | `GET /api/v1/employee/daily-reports/summary` | `employee_daily_report` |
| SA-001 | 提交请假 | `POST /api/v1/student/leave-requests` | `student_admin_service` |
| SA-002 | 审批请假 | `PUT /api/v1/student/leave-requests/{id}/approve` | `student_admin_service` |
| SA-008 | 提交投诉 | `POST /api/v1/student/feedback-tickets` | `student_feedback_ticket` |
| SA-009 | 处理投诉 | `PUT /api/v1/student/feedback-tickets/{id}` | `student_feedback_ticket` |
| SA-004 | 记录情绪交互 | `POST /api/v1/student/psych/record` | `student_psych_record` |
| SA-006 | 查询心理预警 | `GET /api/v1/student/psych/alerts` | `student_psych_alert` |
| SA-007 | 处理心理预警 | `PUT /api/v1/student/psych/alerts/{id}` | `student_psych_alert` |
| RP-001 | 触发报告生成 | `POST /api/v1/reports/generate` | `report_generation` |
| RP-004 | 查看报告详情 | `GET /api/v1/reports/{id}` | `report_generation` |
| CR-001 | 上传客户资料 | `POST /api/v1/profile/upload` | `customer_source` |
| CR-006 | 查询研判状态 | `GET /api/v1/profile/{source_id}` | `customer_profile` |

### 附录 E：V1.1 相对于 V1.0 的主要变更（⭐ 新增）

| 变更项 | V1.0 | V1.1 |
|--------|------|------|
| 接口字段名 | 部分使用简称（`name`, `title`, `created_at`） | ⭐ 严格对齐数据库表字段（`project_name`, `event_name`, `create_time`） |
| 响应字段映射 | 不明确 | ⭐ 新增 2.6 节字段命名与数据库对齐规范 |
| 表→接口映射 | 无 | ⭐ 新增 1.4 节数据库表→接口模块映射 |
| 逻辑外键校验 | 未涉及 | ⭐ 新增 14 章：应用层数据一致性保障（完整伪代码） |
| 错误码 | 20 个 | ⭐ 新增 `40402`（关联实体不存在）、`42204`（终态不可回退）、`42205`（逻辑外键引用不存在） |
| 事务边界 | 未涉及 | ⭐ 新增 14.5 节：事务边界规范 + 错误/正确示例 |
| 级联操作 | 未涉及 | ⭐ 新增 14.4 节：取消活动批量取消报名、删除客户同步跟进记录 |
| 异步任务事务 | 简单描述 | ⭐ 明确独立 Session + 事务外调用 Dify |
| 游标分页 | 仅提及 | ⭐ 补充游标分页实现伪代码（12.2 节） |
| 数据隔离矩阵 | 未涉及 | ⭐ 新增 13.5 节：对齐数据库文档 9.1 节 |
| 覆盖索引优化 | 未涉及 | ⭐ 新增 12.5 节索引覆盖优化建议 |
| 心理预警实现 | 流程描述 | ⭐ 补充完整事务伪代码（7.6 节） |
| 状态机校验 | 流程描述 | ⭐ 补充条件更新防并发伪代码（6.4 节） |
| 附录 | 5 个 | ⭐ 附录 A/B 新增数据库表映射列 |

### 附录 E-2：V1.2 相对于 V1.1 的定稿变更

| 变更项 | V1.1 | V1.2 |
|---|---|---|
| 文档状态 | 已确认 | 全链路评审定稿版 |
| 架构引用 | 架构 V1.1 | 架构 V1.2 定稿版 |
| 数据库引用 | 数据库 V2.0 | 数据库 V2.1 定稿版 |
| Dify 引用 | 未在文档头显式列出 | 显式对齐 Dify V1.1 |
| P0/P1 口径 | 接口清单完整，但与前端实现优先级容易混淆 | 明确 P0 接口冻结，Vue 页面不作为 P0 主链路阻塞项 |
| 客户研判 | P1 接口 | 明确为业务核心模块，但 3 天 MVP 可作为 P1 验证链路 |
| 评审结论 | 分散在附录 | 新增 1.5 节全链路评审定稿结论 |
| 章节数 | 16 章 | ⭐ 17 章（新增第 14 章应用层数据一致性保障） |

### 附录 F：与架构文档一致性确认

| 架构文档要求 | API 文档落实 |
|-------------|-------------|
| `/api/v1` 统一前缀 | ✅ 所有接口使用 `/api/v1` |
| `{code, message, data}` 统一响应 | ✅ 所有接口统一格式 |
| Dify 白名单隔离 | ✅ 第10章定义白名单 + Service Token |
| 异步任务模式 | ✅ 第11章定义异步接口规范 + ⭐ 独立Session |
| 活动报名并发控制 | ✅ 5.4 节详细说明并发策略 + FOR UPDATE |
| 统一错误码 | ✅ 第3章定义完整错误码体系 + ⭐ 新增3个 |
| Swagger 测试 | ✅ 第15章 Swagger 配置 |
| Dify HTTP 节点约定 | ✅ 附录C 配置参考 |
| 同步 SQLAlchemy + PyMySQL | ✅ 接口实现层面保持一致 |
| ⭐ 无物理外键 | ✅ 第14章完整的应用层一致性保障 |
| ⭐ 逻辑关联 + 索引 | ✅ 所有接口响应字段对应索引字段 |

### 附录 G：FastAPI 启动验证

```bash
# 启动 FastAPI
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 验证健康检查
curl http://localhost:8000/api/v1/health

# 验证 Swagger 文档
# 浏览器打开：http://localhost:8000/docs

# 验证登录
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456"}'

# 验证课程查询（带 Token）
curl http://localhost:8000/api/v1/courses \
  -H "Authorization: Bearer {access_token}"

# ⭐ 验证逻辑外键校验
curl -X POST http://localhost:8000/api/v1/events/999/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {access_token}" \
  -d '{"user_id":10, "customer_name":"测试"}'
# 预期返回: {"code":40401,"message":"活动不存在","data":null}
```

---

> **文档结束**  
> 教育服务系统 — API 接口设计规范文档 V1.2  
> **核心变更**：严格对齐《数据库设计规范文档 V2.1》，新增全链路评审定稿结论，明确 P0 接口冻结、Dify 白名单边界和 Vue 前端 P1 实现策略。

> **后续工作建议：**
> 1. 基于本文档生成 `routers/` 和 `schemas/` 的 Python 代码骨架
> 2. 实现 `utils/validators.py`（逻辑外键校验装饰器）和 `utils/errors.py`（统一异常类）
> 3. 实现 `services/cascade_service.py`（级联操作服务）
> 4. 在 Dify 中配置 HTTP 节点，填写正确的 URL 和 Service Token
> 5. 编写逻辑外键校验的集成测试用例
