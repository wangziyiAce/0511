# 教育服务系统 — Dify 工作流设计规范文档 V1.1

> **文档版本**：V1.1  
> **编制日期**：2026-07-09  
> **文档状态**：全链路评审定稿版  
> **适用阶段**：MVP 开发 → 答辩演示  
> **对应架构文档**：《教育服务系统_总体架构设计文档_定稿版V1.2》  
> **对应 API 文档**：《教育服务系统_API接口设计规范文档_V1.2.md》  
> **对应数据库文档**：《教育服务系统_数据库设计规范文档_V2.1.md》  
> **对应前端文档**：《教育服务系统_前端架构设计规范文档_V1.1.md》  
> **定稿基线**：架构 V1.2 + 数据库 V2.1 + API V1.2 + Dify V1.1 + 前端 V1.1  
> **核心原则**：Dify 做大脑（意图识别 + 对话生成 + 工作流编排），FastAPI 做手脚（业务接口 + 数据读写 + 权限校验）

---

## 目录

1. [设计总则](#1-设计总则)
2. [Dify 工作流架构设计](#2-dify-工作流架构设计)
3. [Chatflow 设计规范](#3-chatflow-设计规范)
4. [Workflow 设计规范（后台 AI 任务）](#4-workflow-设计规范后台-ai-任务)
5. [HTTP 请求节点规范](#5-http-请求节点规范)
6. [知识库与 RAG 设计](#6-知识库与-rag-设计)
7. [意图识别与路由设计](#7-意图识别与路由设计)
8. [LLM 节点设计规范](#8-llm-节点设计规范)
9. [变量管理与数据流转](#9-变量管理与数据流转)
10. [各业务场景 Chatflow 设计](#10-各业务场景-chatflow-设计)
11. [后台 AI 任务 Workflow 设计](#11-后台-ai-任务-workflow-设计)
12. [Dify WebApp 配置](#12-dify-webapp-配置)
13. [测试与验收清单](#13-测试与验收清单)
14. [附录](#14-附录)

---

## 1. 设计总则

### 1.1 Dify 在系统架构中的定位

```text
┌─────────────────────────────────────────────────────────────┐
│  接入层：Vue 3 前端 / Dify WebApp / Swagger                   │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
    ┌───────────▼───────────┐     ┌───────────▼───────────────┐
    │  Dify AI 编排层（大脑） │     │  FastAPI 业务服务层（手脚） │
    │                       │     │                           │
    │  Chatflow / Workflow  │ ←→ │  routers / services        │
    │  - 意图识别            │HTTP │  - 业务接口 CRUD           │
    │  - 对话生成            │     │  - 数据校验（逻辑外键）     │
    │  - RAG 知识库问答       │     │  - 权限校验               │
    │  - HTTP 节点调 API     │     │  - 并发控制               │
    │                       │     │  - Dify API 调用封装       │
    └───────────┬───────────┘     └───────────┬───────────────┘
                │                             │
                └──────────────┬──────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  MySQL 8.0（记忆）    │
                    │  ⭐ 无物理外键        │
                    └─────────────────────┘
```

### 1.2 Dify 与 FastAPI 职责边界

| 能力 | Dify 负责 | FastAPI 负责 |
|------|----------|-------------|
| 意图识别 | ✅ 是 | ❌ 否 |
| 自然语言回复 | ✅ 是 | ❌ 否 |
| RAG 知识库问答 | ✅ 是 | ❌ 否 |
| 业务数据查询 | ❌ 否 | ✅ 是 |
| 数据新增/修改/删除 | ❌ 否 | ✅ 是 |
| 活动报名并发控制 | ❌ 否 | ✅ 是 |
| 权限校验 | 辅助（传 user_id） | ✅ 是 |
| 状态流转 | ❌ 否 | ✅ 是 |
| 报告文本生成 | ✅ 是 | 可辅助（数据聚合） |
| 报告数据聚合 | ❌ 否 | ✅ 是 |
| 业务日志 | ❌ 否 | ✅ 是 |
| 数据库访问 | ❌ 否 | ✅ 是 |

### 1.3 必须遵守的边界

1. **Dify 不直接操作数据库。** 所有数据查询/写入必须通过 FastAPI HTTP 节点。
2. **Dify 不保存业务主数据。** 对话历史可以存在 Dify 内置存储，但业务数据（课程、客户、活动等）不存入 Dify。
3. **AI 不编造业务数据。** 课程名称、价格、时间、活动详情等信息必须来自 FastAPI 返回的真实数据。
4. **所有写入动作必须经过 FastAPI。** 活动报名、请假申请、投诉提交等。
5. **业务规则校验在 FastAPI 完成。** Dify 只负责理解用户意图和生成自然语言。

### 1.4 Dify 可调用接口白名单（对齐 API 文档第 10 章）

| 方法 | 路径 | 场景 | MVP | 数据库表 |
|------|------|------|-----|----------|
| GET | `/api/v1/courses` | 课程查询 | P0 | `course_project` |
| GET | `/api/v1/events` | 活动查询 | P0 | `event_lecture` |
| POST | `/api/v1/events/{event_id}/register` | 活动报名 | P0 | `event_registration` |
| GET | `/api/v1/crm/leads` | 客户查询 | P1 | `crm_lead` |
| POST | `/api/v1/chat/session` | 创建会话 | P1 | `chat_session` |
| POST | `/api/v1/student/psych/record` | 心理记录写入 | P1 | `student_psych_record` |
| GET | `/api/v1/student/applications` | 申请进度查询 | P1 | `application_progress` |

**禁止 Dify 直接调用的接口：**
- 用户管理接口（`/api/v1/auth/*` 除 login）
- 系统配置接口
- 删除类接口
- 管理员接口
- 未列入白名单的写入接口

### 1.5 Dify Service Token 设计

Dify 调用 FastAPI 时使用独立服务令牌，与用户 JWT 分离：

```text
Authorization: Bearer {DIFY_SERVICE_TOKEN}
```

**环境变量配置：**
```bash
# .env
DIFY_API_BASE_URL=http://localhost:8080/v1
DIFY_API_KEY=app-xxxxxxxxxxxxxxxx
DIFY_SERVICE_TOKEN=service-xxxxxxxxxxxx
```

**FastAPI 侧校验（对齐 API 文档 10.4 节）：**
```python
# utils/security.py
from fastapi import Header, HTTPException
from config import settings

def verify_dify_service_token(authorization: str = Header(...)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail={"code": 40301, "message": "无效的服务令牌"})
    token = authorization.replace("Bearer ", "").strip()
    if token != settings.DIFY_SERVICE_TOKEN:
        raise HTTPException(status_code=403, detail={"code": 40301, "message": "服务令牌校验失败"})
```

### 1.6 全链路评审定稿结论（V1.1）

Dify V1.1 在 V1.0 基础上做定稿确认，不扩大 Dify 对业务数据的权限。经全链路评审，最终口径如下：

| 评审项 | 定稿结论 |
|---|---|
| 职责边界 | Dify 只做意图识别、RAG、对话生成和工作流编排，不直接读写 MySQL |
| P0 演示链路 | 客服 Agent Chatflow 跑通课程查询、活动查询、活动报名、知识库问答 |
| Dify 白名单 | 仅调用 API V1.2 第 10 章白名单接口，统一携带 `DIFY_SERVICE_TOKEN` |
| 客户研判 | 属于业务核心模块，MVP 阶段作为 P1 Workflow 验证链路；文本资料优先，PDF / Excel 后续增强 |
| 报告生成 | 保持 P0 Workflow，由 FastAPI 后台任务触发 Dify blocking 模式并写回 `report_generation` |
| 安全边界 | 心理、投诉、客户等敏感业务数据由 FastAPI 做权限过滤，Dify 不保存业务主数据 |

---

## 2. Dify 工作流架构设计

### 2.1 工作流类型划分

| 类型 | 用途 | 触发方式 | 响应模式 | MVP 优先级 |
|------|------|---------|---------|-----------|
| **Chatflow** | 对话型 AI（客服 Agent） | 用户在 Dify WebApp 提问 | streaming / blocking | P0 |
| **Workflow** | 后台 AI 任务（报告生成、客户研判） | FastAPI 通过 API 触发 | blocking | 报告生成 P0，客户研判 P1 |
| **Agent** | 复杂多步推理（P2 预留） | - | - | P2 |

### 2.2 MVP 工作流全景图

```text
┌──────────────────────────────────────────────────────────────┐
│                     Dify 工作流全景（MVP）                      │
│                                                              │
│  Chatflow 1: 客服 Agent（主入口）          P0                  │
│  ├── 意图识别 → 路由分发                                      │
│  ├── 课程查询 → HTTP GET /api/v1/courses                      │
│  ├── 活动查询 → HTTP GET /api/v1/events                       │
│  ├── 活动报名 → HTTP POST /api/v1/events/{id}/register         │
│  ├── 知识库问答 → RAG 检索                                    │
│  └── 闲聊兜底 → LLM 自由回复                                  │
│                                                              │
│  Chatflow 2: 企业助手              P1                         │
│  ├── 客户查询 → HTTP GET /api/v1/crm/leads                    │
│  └── 客户信息问答                                             │
│                                                              │
│  Chatflow 3: 学生助手              P1                         │
│  ├── 心理关怀对话（记录情绪）                                   │
│  ├── HTTP POST /api/v1/student/psych/record                   │
│  └── 申请进度查询 → HTTP GET /api/v1/student/applications      │
│                                                              │
│  Workflow 1: 客户研判             P1（业务核心，MVP 验证链路）   │
│  ├── FastAPI 触发 → Dify Chat API                             │
│  ├── 规则匹配 → LLM 研判                                      │
│  └── 返回结构化 JSON                                          │
│                                                              │
│  Workflow 2: 智能报告生成         P0                          │
│  ├── FastAPI 触发 → Dify Chat API                             │
│  ├── 数据注入 → LLM 生成报告                                   │
│  └── 返回 Markdown/HTML                                       │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 MVP 主链路数据流

```text
用户在 Dify WebApp 提问
        ↓
Dify Chatflow 启动
        ↓
意图识别节点（LLM 分类）
        ↓
┌───────────────────────────────────────┐
│ 路由分发（条件分支）                    │
│                                       │
│ course_query → HTTP GET /api/v1/courses│
│ event_query  → HTTP GET /api/v1/events │
│ event_register → HTTP POST ...register │
│ knowledge    → RAG 知识库检索          │
│ chat         → LLM 自由回复            │
└───────────────────────────────────────┘
        ↓
FastAPI 查询 MySQL
        ↓
FastAPI 返回业务 JSON
        ↓
Dify 基于接口结果 + LLM 组织自然语言回复
        ↓
用户看到结果
```

---

## 3. Chatflow 设计规范

### 3.1 Chatflow 结构模板

每个 Chatflow 必须包含以下节点结构：

```text
┌──────────┐
│  Start   │ ← 用户输入（sys.query）
└────┬─────┘
     ↓
┌──────────────┐
│ 意图识别 LLM  │ ← 分类用户意图（course_query / event_query / event_register / knowledge / chat）
└──────┬───────┘
       ↓
┌──────────────┐
│  条件分支     │ ← 根据意图路由到不同处理节点
└──────┬───────┘
       │
   ┌───┼───┬───┬───┐
   ↓   ↓   ↓   ↓   ↓
┌────┐┌────┐┌────┐┌────┐┌────┐
│HTTP││HTTP││HTTP││RAG ││LLM │
│课程││活动││报名││检索││回复│
└──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘
   │     │     │     │     │
   └─────┴─────┴─────┴─────┘
              ↓
     ┌──────────────┐
     │ 回复生成 LLM  │ ← 基于接口结果 + 上下文生成自然语言
     └──────┬───────┘
            ↓
     ┌──────────┐
     │  Answer  │ ← 返回给用户
     └──────────┘
```

### 3.2 节点命名规范

| 节点类型 | 命名格式 | 示例 |
|----------|---------|------|
| 意图识别 LLM | `intent_classifier` | - |
| HTTP 请求节点 | `http_{action}_{resource}` | `http_query_courses`, `http_register_event` |
| 知识检索 | `knowledge_{domain}` | `knowledge_overseas`, `knowledge_policy` |
| LLM 生成节点 | `llm_{purpose}` | `llm_course_reply`, `llm_event_reply` |
| 条件分支 | `route_{condition}` | `route_intent` |
| 变量赋值 | `set_{variable}` | `set_course_list` |
| 代码节点 | `code_{purpose}` | `code_parse_json`, `code_format_price` |
| 模板转换 | `template_{purpose}` | `template_course_card` |

### 3.3 系统提示词规范

**意图识别节点系统提示词：**

```text
你是一个教育服务系统的智能客服，负责识别用户意图。

请根据用户输入，判断意图类型并返回 JSON：

{
  "intent": "course_query | event_query | event_register | knowledge | chat",
  "confidence": 0.0-1.0,
  "entities": {
    "category": "课程分类（如有）",
    "keyword": "搜索关键词（如有）",
    "event_name": "活动名称（如有）"
  }
}

意图说明：
- course_query: 用户询问课程、培训、项目相关信息
- event_query: 用户询问活动、讲座、宣讲会相关信息
- event_register: 用户想要报名参加某个活动
- knowledge: 用户询问留学政策、海外生活等知识类问题
- chat: 普通闲聊、问候、非业务对话

注意：只能返回上述意图之一，不要编造其他意图类型。
```

**回复生成节点系统提示词：**

```text
你是一个专业、友好的教育服务机构客服。

回复规则：
1. 严格基于接口返回的数据进行回复，不要编造任何课程、活动、价格等信息。
2. 如果接口返回空数据，告知用户"暂无相关信息"。
3. 回复风格亲切专业，使用适当的 emoji 增强可读性。
4. 价格信息保留两位小数，单位为元。
5. 活动报名成功后，确认报名信息并告知注意事项。
6. 不要做出任何承诺或保证（如"保证录取"、"100%通过"等）。
7. 涉及心理、健康问题时，只做倾听和关怀，不做诊断和建议。

当前上下文：
- 用户意图：{{intent}}
- 接口返回数据：{{api_result}}
```

### 3.4 变量命名规范

| 变量名 | 类型 | 来源 | 说明 |
|--------|------|------|------|
| `sys.query` | string | Start 节点 | 用户原始输入 |
| `sys.conversation_id` | string | 系统 | 会话 ID |
| `sys.user_id` | string | 系统 | 用户标识 |
| `intent` | string | 意图识别 LLM | 意图类型 |
| `entities` | object | 意图识别 LLM | 提取的实体 |
| `api_result` | object/string | HTTP 节点 | FastAPI 返回的 body |
| `course_list` | array | 代码节点 | 解析后的课程列表 |
| `event_list` | array | 代码节点 | 解析后的活动列表 |
| `register_result` | object | HTTP 节点 | 报名结果 |
| `knowledge_context` | string | 知识检索 | RAG 检索到的知识片段 |
| `final_reply` | string | 回复 LLM | 最终回复文本 |

---

## 4. Workflow 设计规范（后台 AI 任务）

### 4.1 Workflow 触发方式

后台 AI 任务由 FastAPI 通过 Dify Chat API 触发，而非用户在 WebApp 中触发：

```text
FastAPI BackgroundTasks
        ↓
调用 Dify Chat API（blocking 模式）
POST /v1/chat-messages
{
  "inputs": {
    "task_type": "customer_profiling",  // 或 report_generation
    "raw_data": {...},                   // 业务数据
    "rules": [...]                       // 规则配置
  },
  "query": "请对以下客户资料进行画像研判...",
  "response_mode": "blocking",
  "user": "system-bot"
}
        ↓
Dify Workflow 执行
        ↓
返回结构化结果
        ↓
FastAPI 解析结果 → 写入 MySQL
```

### 4.2 Workflow 与 Chatflow 的区别

| 特性 | Chatflow | Workflow |
|------|----------|----------|
| 触发方 | 用户（WebApp） | FastAPI（API 调用） |
| 响应模式 | streaming（推荐）/ blocking | blocking（必须） |
| 是否有对话上下文 | 是（多轮对话） | 否（单次任务） |
| 输入 | 用户自然语言 | 结构化 inputs + query |
| 输出 | 自然语言回复 | 结构化 JSON |
| 会话管理 | 需要 | 不需要 |
| 典型场景 | 客服对话 | 报告生成、客户研判 |

### 4.3 Workflow 输出格式规范

所有 Workflow 必须返回标准 JSON 格式，便于 FastAPI 解析：

```json
{
  "success": true,
  "task_type": "customer_profiling",
  "result": {
    // 业务结果
  },
  "metadata": {
    "tokens_used": 1500,
    "processing_time_ms": 3200
  }
}
```

**FastAPI 侧解析：**
```python
# services/dify_service.py
def call_dify_workflow(task_type: str, inputs: dict, query: str) -> dict:
    payload = {
        "inputs": inputs,
        "query": query,
        "response_mode": "blocking",
        "user": "system-bot",
    }
    response = httpx.post(
        f"{settings.DIFY_API_BASE_URL}/chat-messages",
        headers={"Authorization": f"Bearer {settings.DIFY_API_KEY}"},
        json=payload,
        timeout=60.0  # Workflow 超时时间比 Chatflow 长
    )
    result = response.json()
    # 解析 answer 中的 JSON
    answer_text = result.get("answer", "{}")
    try:
        return json.loads(answer_text)
    except json.JSONDecodeError:
        raise DifyParseError("Dify 返回格式异常")
```

---

## 5. HTTP 请求节点规范

### 5.1 节点配置模板

每个 HTTP 请求节点统一配置：

| 配置项 | 值 |
|--------|-----|
| 请求方式 | GET / POST（根据接口） |
| URL | `http://host.docker.internal:8000/api/v1/{path}` |
| 请求头 Authorization | `Bearer {{DIFY_SERVICE_TOKEN}}` |
| Content-Type | `application/json` |
| 超时时间 | 15 秒（Chatflow）/ 60 秒（Workflow） |
| 重试次数 | 0（不自动重试，由工作流条件分支处理） |

> **注意**：Dify 运行在 Docker 中，FastAPI 在宿主机，必须使用 `host.docker.internal` 而非 `localhost`。

### 5.2 课程查询 HTTP 节点

```yaml
节点名称: http_query_courses
请求方式: GET
URL: http://host.docker.internal:8000/api/v1/courses
查询参数:
  - category: {{entities.category}}           # 来自意图识别
  - keyword: {{entities.keyword}}             # 来自意图识别
  - page: 1
  - page_size: 10
请求头:
  Authorization: Bearer {{DIFY_SERVICE_TOKEN}}
  Content-Type: application/json
```

**返回处理：**
- 成功（code=0）：提取 `data.items` 传递给 LLM 回复节点
- 失败（code≠0）：使用默认回复"查询课程时出现错误，请稍后再试"

### 5.3 活动查询 HTTP 节点

```yaml
节点名称: http_query_events
请求方式: GET
URL: http://host.docker.internal:8000/api/v1/events
查询参数:
  - status: upcoming
  - page: 1
  - page_size: 10
请求头:
  Authorization: Bearer {{DIFY_SERVICE_TOKEN}}
```

### 5.4 活动报名 HTTP 节点

```yaml
节点名称: http_register_event
请求方式: POST
URL: http://host.docker.internal:8000/api/v1/events/{{event_id}}/register
请求体:
  {
    "user_id": null,
    "customer_name": "{{customer_name}}",
    "contact_info": "{{contact_info}}",
    "remark": ""
  }
请求头:
  Authorization: Bearer {{DIFY_SERVICE_TOKEN}}
  Content-Type: application/json
```

**报名流程设计（Dify 侧）：**

```text
用户表达报名意向
        ↓
意图识别：event_register
        ↓
LLM 提取信息：询问姓名、联系方式（如果用户未提供）
        ↓
条件分支：信息是否完整？
  ├── 是 → HTTP POST 报名
  │        ↓
  │    ┌─────────────────────────────┐
  │    │ 条件分支：报名结果？          │
  │    │ code=0 → "报名成功！..."      │
  │    │ code=40901 → "您已报名过..."  │
  │    │ code=42201 → "名额已满..."    │
  │    │ 其他 → "报名失败，请稍后..."   │
  │    └─────────────────────────────┘
  └── 否 → LLM 追问缺失信息
```

### 5.5 HTTP 节点错误处理

每个 HTTP 节点必须配置失败处理：

| 场景 | HTTP 状态码 | Dify 处理 |
|------|------------|----------|
| 成功 | 200 (code=0) | 正常传递结果给 LLM |
| 业务错误 | 200 (code≠0) | 根据错误码返回不同文案 |
| 参数错误 | 400 | 返回"请求参数有误" |
| 未授权 | 401/403 | 返回"服务暂不可用"（不暴露鉴权细节） |
| 资源不存在 | 404 | 返回"未找到相关信息" |
| 服务器错误 | 500/502 | 返回"服务暂时繁忙，请稍后再试" |
| 超时 | 无响应 | 返回"响应超时，请稍后再试" |

**Dify 条件分支错误码映射：**

```python
# 代码节点：解析 API 响应
def parse_api_response(api_result: str) -> dict:
    """解析 FastAPI 返回结果并映射为 Dify 可用变量"""
    import json
    data = json.loads(api_result) if isinstance(api_result, str) else api_result
    
    return {
        "api_code": data.get("code", -1),
        "api_message": data.get("message", ""),
        "api_data": json.dumps(data.get("data", {}), ensure_ascii=False),
        "is_success": data.get("code") == 0,
        "is_duplicate": data.get("code") == 40901,    # 重复报名
        "is_full": data.get("code") == 42201,          # 名额已满
        "is_not_found": data.get("code") in [40401, 40402],  # 资源不存在
        "items_count": len(data.get("data", {}).get("items", [])),
        "items_json": json.dumps(data.get("data", {}).get("items", []), ensure_ascii=False),
    }
```

---

## 6. 知识库与 RAG 设计

### 6.1 MVP 知识库架构

MVP 阶段使用 Dify 内置知识库（不单独接 Milvus）：

```text
Dify 知识库
├── 留学政策（文档上传）
│   ├── 各国留学签证政策
│   ├── 院校申请指南
│   └── 语言考试要求
├── 海外生活知识（数据库 overseas_life_knowledge）
│   ├── 住宿攻略
│   ├── 生活常识
│   └── 安全指南
├── 公司业务介绍
│   ├── 服务项目说明
│   ├── 课程体系介绍
│   └── 成功案例
└── FAQ
    ├── 常见问题
    ├── 报名流程
    └── 退费政策
```

### 6.2 知识库文档格式规范

上传到 Dify 知识库的文档要求：

| 要求 | 说明 |
|------|------|
| 格式 | Markdown（推荐）或 TXT |
| 编码 | UTF-8 |
| 分段 | 按主题分节，使用 `##` 标题 |
| 长度 | 单段不超过 2000 字符 |
| 更新时间 | 文档末尾标注更新日期 |
| 来源标注 | 注明信息来源 |

**文档模板：**
```markdown
## 英国留学签证政策（2026年）

### 学生签证类型
- Tier 4 (General) Student Visa：适用于 16 岁以上学生
- Short-term Study Visa：适用于 6 个月以内的短期课程

### 申请条件
1. 获得英国院校的无条件录取通知书（CAS）
2. 英语语言能力证明（雅思总分 5.5 以上）
3. 资金证明：至少覆盖第一年学费 + 9 个月生活费

### 申请流程
1. 在线填写签证申请表
2. 支付签证费用和 IHS 医疗附加费
3. 预约签证中心采集生物信息
4. 提交申请材料

---
> 更新时间：2026-07-09
> 信息来源：英国政府官网
```

### 6.3 RAG 检索节点配置

```yaml
节点名称: knowledge_retrieval
知识库: 留学政策 / 海外生活 / 公司业务 / FAQ
检索模式: 混合检索（关键词 + 向量）
Top K: 3
Score 阈值: 0.7
重排序: 启用（Rerank 模型）
```

**RAG 回复模板：**
```text
基于知识库检索结果回答用户问题。

检索到的相关知识：
{{knowledge_context}}

回答规则：
1. 优先使用知识库中的信息
2. 如果知识库中没有相关信息，回复"抱歉，我暂时无法回答这个问题，建议您咨询我们的顾问"
3. 回答末尾标注信息来源（如适用）
4. 涉及政策时效性的内容，提醒用户以官方最新政策为准
```

### 6.4 知识库与数据库的数据同步

| 数据类型 | 存储位置 | 同步方式 |
|---------|---------|---------|
| 留学政策文档 | Dify 知识库 | 手动上传/更新 |
| 海外生活知识 | MySQL `overseas_life_knowledge` + Dify 知识库 | 管理后台同步 |
| 公司业务介绍 | Dify 知识库 | 手动维护 |
| FAQ | Dify 知识库 | 手动维护 |
| 课程/活动数据 | MySQL → FastAPI → Dify HTTP | 实时查询 |
| 客户数据 | MySQL → FastAPI → Dify HTTP | 实时查询 |

---

## 7. 意图识别与路由设计

### 7.1 意图分类体系（对齐数据库 `intent_config` 表）

| 意图编码 | 意图名称 | 适用场景 | 路由目标 |
|----------|---------|---------|---------|
| `course_query` | 课程查询 | 客服 | HTTP → `/api/v1/courses` |
| `event_query` | 活动查询 | 客服 | HTTP → `/api/v1/events` |
| `event_register` | 活动报名 | 客服 | LLM 提取信息 → HTTP → `/api/v1/events/{id}/register` |
| `knowledge_overseas` | 海外生活咨询 | 客服 | RAG 知识库检索 |
| `knowledge_policy` | 留学政策咨询 | 客服 | RAG 知识库检索 |
| `knowledge_company` | 公司业务咨询 | 客服 | RAG 知识库检索 |
| `knowledge_faq` | 常见问题 | 客服 | RAG 知识库检索 |
| `chat_greeting` | 问候 | 客服 | LLM 自由回复 |
| `chat_farewell` | 道别 | 客服 | LLM 自由回复 |
| `chat_other` | 其他闲聊 | 客服 | LLM 自由回复 |
| `lead_query` | 客户查询 | 企业 | HTTP → `/api/v1/crm/leads` |
| `daily_report` | 日报口述 | 企业 | LLM 结构化 → HTTP → FastAPI |
| `leave_request` | 请假意图 | 学生 | 引导至 FastAPI 接口（非 Dify 直接处理） |
| `complaint_submit` | 投诉意图 | 学生 | 引导至 FastAPI 接口（非 Dify 直接处理） |
| `psych_check_in` | 心理关怀 | 学生 | LLM 对话 → HTTP → `/api/v1/student/psych/record` |
| `application_progress` | 申请进度 | 学生 | HTTP → `/api/v1/student/applications` |
| `emotion_express` | 情绪表达 | 学生 | LLM 关怀回复 |
| `study_advice` | 学习建议 | 学生 | RAG + LLM |
| `deadline_query` | DDL 查询 | 学生 | HTTP → `/api/v1/student/deadlines` |
| `score_query` | 成绩查询 | 学生 | HTTP → FastAPI（P1） |

### 7.2 意图识别 Prompt 设计原则

1. **Few-shot 示例**：每种意图提供 2-3 个典型问法示例
2. **优先级排序**：业务意图 > 知识问答 > 闲聊
3. **模糊意图处理**：无法确定时返回 `chat` 并引导用户明确需求
4. **实体提取**：同时提取分类、关键词、姓名、联系方式等
5. **confidence 阈值**：低于 0.6 时触发澄清追问

### 7.3 条件分支路由逻辑

```text
条件分支：route_intent
条件判断（按优先级）：
  1. intent == "course_query"     → http_query_courses
  2. intent == "event_query"      → http_query_events
  3. intent == "event_register"   → llm_extract_register_info
  4. intent == "lead_query"       → http_query_leads
  5. intent == "psych_check_in"   → llm_psych_chat
  6. intent == "application_progress" → http_query_applications
  7. intent.startswith("knowledge_") → knowledge_retrieval
  8. intent.startswith("chat_")   → llm_free_reply
  9. 默认                           → llm_clarify_intent（追问意图）
```

---

## 8. LLM 节点设计规范

### 8.1 模型选择

| 场景 | 推荐模型 | 说明 |
|------|---------|------|
| 意图识别 | GPT-4o-mini / Claude 3 Haiku | 快速分类，低延迟 |
| 对话回复 | GPT-4o / Claude 3.5 Sonnet | 自然语言质量 |
| 报告生成 | GPT-4o / Claude 3.5 Sonnet | 长文本生成 |
| 客户研判 | GPT-4o / Claude 3.5 Sonnet | 结构化推理 |
| 情绪分析 | GPT-4o-mini | 快速分类 |
| RAG 问答 | GPT-4o / Claude 3.5 Sonnet | 知识综合 |

### 8.2 温度参数设置

| 场景 | Temperature | 说明 |
|------|------------|------|
| 意图识别 | 0.1 | 低随机性，分类稳定 |
| 对话回复 | 0.7 | 自然多样性 |
| 报告生成 | 0.5 | 有一定创造性但不偏离 |
| 客户研判 | 0.2 | 推理严谨 |
| 情绪分析 | 0.1 | 分类稳定 |

### 8.3 回复生成 LLM Prompt 模板

**课程查询回复：**
```text
你是一个专业的教育顾问。请根据以下课程信息，为用户提供有帮助的回复。

用户查询意图：{{intent}}
查询关键词：{{entities.keyword}}

可用的课程数据（来自系统数据库，请勿编造）：
{{course_list}}

回复要求：
1. 如果课程列表不为空：
   - 简要介绍匹配的课程（最多3个）
   - 包含课程名称、价格、周期等关键信息
   - 如果课程较多，告知用户总数并提供筛选建议
2. 如果课程列表为空：
   - 告知用户"目前暂无匹配的课程"
   - 建议用户尝试其他关键词或联系顾问
3. 语气亲切专业，使用适当的 emoji
4. 不要编造不存在的课程信息
5. 不要做出"保证通过"、"100%录取"等承诺

回复格式：自然语言，不需要 JSON
```

**活动报名成功回复：**
```text
用户已成功报名活动。请根据报名结果生成确认回复。

报名结果：{{register_result}}

回复要求：
1. 确认报名信息：活动名称、时间、地点
2. 提醒注意事项（如提前5分钟入场、带好笔记本等）
3. 提供咨询方式（如有问题可联系顾问）
4. 语气热情积极
```

### 8.4 多轮对话上下文管理

```yaml
对话设置:
  最大轮次: 20 轮
  上下文窗口: 最近 10 轮对话
  变量持久化:
    - customer_name: 用户姓名（提取后保存）
    - contact_info: 联系方式（提取后保存）
    - last_intent: 上一轮意图
    - selected_course_id: 用户选中的课程 ID
    - selected_event_id: 用户选中的活动 ID
```

---

## 9. 变量管理与数据流转

### 9.1 全局变量定义

| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `customer_name` | string | "" | 用户在对话中提供的姓名 |
| `contact_info` | string | "" | 用户在对话中提供的联系方式 |
| `last_intent` | string | "" | 上一轮识别的意图 |
| `selected_event_id` | number | null | 用户选择报名的活动 ID |
| `collected_info_complete` | boolean | false | 报名信息是否收集完整 |

### 9.2 数据流转图

```text
Start (sys.query)
    │
    ▼
intent_classifier (LLM)
    │ 输出: intent, entities, confidence
    ▼
route_intent (条件分支)
    │
    ├── course_query → http_query_courses
    │   │ 输入: entities.category, entities.keyword
    │   │ 输出: api_result (body)
    │   ▼
    │   code_parse_response → 输出: course_list, items_count
    │   ▼
    │   llm_course_reply
    │   │ 输入: intent, course_list, items_count
    │   │ 输出: text (最终回复)
    │
    ├── event_query → http_query_events → llm_event_reply → Answer
    │
    ├── event_register → llm_extract_info
    │   │ 输入: sys.query, customer_name, contact_info
    │   │ 输出: info_complete, missing_field
    │   ▼
    │   route_registration (条件分支)
    │   │
    │   ├── info_complete = true → http_register_event → llm_register_success
    │   └── info_complete = false → llm_ask_missing_info
    │
    ├── knowledge_* → knowledge_retrieval → llm_knowledge_reply
    │
    └── chat_* → llm_free_reply
```

### 9.3 代码节点示例

**解析课程 API 响应：**
```python
def main(api_result: str) -> dict:
    """解析课程查询 API 响应，提取课程列表"""
    import json
    
    try:
        data = json.loads(api_result) if isinstance(api_result, str) else api_result
        items = data.get("data", {}).get("items", [])
        total = data.get("data", {}).get("total", 0)
        
        # 格式化课程信息供 LLM 使用
        course_list = []
        for item in items:
            course_list.append({
                "id": item.get("id"),
                "name": item.get("project_name", ""),          # ⭐ 对齐数据库字段 project_name
                "category": item.get("category", ""),
                "description": item.get("description", ""),
                "price": item.get("price", 0),
                "duration": item.get("duration", ""),
                "target_audience": item.get("target_audience", ""),  # ⭐ 对齐数据库字段
                "tags": item.get("tags", []),
            })
        
        return {
            "course_list_json": json.dumps(course_list, ensure_ascii=False),
            "items_count": len(items),
            "total": total,
            "has_courses": len(items) > 0,
            "first_course_name": items[0].get("project_name", "") if items else "",
        }
    except Exception as e:
        return {
            "course_list_json": "[]",
            "items_count": 0,
            "total": 0,
            "has_courses": False,
            "first_course_name": "",
            "parse_error": str(e),
        }
```

**提取报名信息：**
```python
def main(query: str, customer_name: str, contact_info: str) -> dict:
    """从对话中提取和累积报名所需信息"""
    
    # 检查已有信息
    has_name = bool(customer_name and customer_name.strip())
    has_contact = bool(contact_info and contact_info.strip())
    
    # 简单的信息提取（实际应在 LLM 节点中完成）
    # 此处作为代码节点兜底逻辑
    
    missing_fields = []
    if not has_name:
        missing_fields.append("姓名")
    if not has_contact:
        missing_fields.append("联系方式")
    
    return {
        "info_complete": len(missing_fields) == 0,
        "missing_fields": "、".join(missing_fields) if missing_fields else "",
        "missing_count": len(missing_fields),
        "has_name": has_name,
        "has_contact": has_contact,
    }
```

---

## 10. 各业务场景 Chatflow 设计

### 10.1 客服 Agent Chatflow（主入口 - P0）

**适用场景**：用户在 Dify WebApp 中进行客服咨询

**节点流程：**

```text
┌─────────────────────────────────────────────────────────────┐
│                    客服 Agent Chatflow                        │
│                                                             │
│  Start                                                      │
│    ↓                                                        │
│  intent_classifier (LLM) ─── 意图识别                        │
│    ↓                                                        │
│  route_intent (条件分支)                                     │
│    │                                                        │
│    ├── course_query                                         │
│    │   ├── http_query_courses (HTTP GET)                    │
│    │   ├── code_parse_courses (代码)                         │
│    │   └── llm_course_reply (LLM)                           │
│    │                                                        │
│    ├── event_query                                          │
│    │   ├── http_query_events (HTTP GET)                     │
│    │   ├── code_parse_events (代码)                          │
│    │   └── llm_event_reply (LLM)                            │
│    │                                                        │
│    ├── event_register                                       │
│    │   ├── llm_extract_info (LLM) ─── 提取姓名+联系方式       │
│    │   ├── route_info_complete (条件分支)                    │
│    │   │   ├── 完整 → http_register_event (HTTP POST)       │
│    │   │   │         └── llm_register_result (LLM)           │
│    │   │   └── 不完整 → llm_ask_info (LLM) ─── 追问          │
│    │                                                        │
│    ├── knowledge_*                                          │
│    │   ├── knowledge_retrieval (知识检索)                    │
│    │   └── llm_knowledge_reply (LLM)                        │
│    │                                                        │
│    └── chat_* / 默认                                        │
│        └── llm_free_reply (LLM)                             │
│                                                             │
│  Answer                                                     │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 企业助手 Chatflow（P1）

**适用场景**：员工查询自己负责的客户信息

**节点流程：**
```text
Start → intent_classifier → route_intent
  ├── lead_query → http_query_leads → code_parse → llm_lead_reply
  └── chat → llm_free_reply
```

**HTTP 节点参数**：
```yaml
URL: http://host.docker.internal:8000/api/v1/crm/leads
参数:
  - keyword: {{entities.keyword}}
  - status: {{entities.status}}
  - page: 1
  - page_size: 5
```

> **注意**：客户数据查询结果受 FastAPI 侧数据权限控制（`owner_employee_id` 过滤）。Dify 传的 `user_id` 仅作为对话标识，不用于数据权限。

### 10.3 学生助手 Chatflow（P1）

**适用场景**：学生心理关怀对话 + 申请进度查询

**节点流程：**
```text
Start → intent_classifier → route_intent
  ├── psych_check_in
  │   ├── llm_psych_dialogue (LLM) ─── 关怀对话
  │   ├── code_extract_emotion (代码) ─── 提取情绪标签
  │   └── http_record_psych (HTTP POST)
  │       URL: /api/v1/student/psych/record
  │       请求体:
  │       {
  │         "student_id": {{sys.user_id}},
  │         "emotion_tag": {{emotion_tag}},
  │         "emotion_score": {{emotion_score}},
  │         "interaction_content": {{dialogue_summary}},
  │         "trigger_keywords": {{trigger_keywords}},
  │         "record_date": "{{today}}"
  │       }
  │
  ├── application_progress
  │   └── http_query_applications → llm_progress_reply
  │
  └── emotion_express
      └── llm_empathy_reply (LLM) ─── 共情回复
```

**心理关怀对话规范：**
1. 倾听优先，不急于给建议
2. 不做出医学诊断
3. 识别高危信号（自伤/自杀倾向）→ 在回复中引导求助 + 后台创建预警
4. 对话摘要写入 `student_psych_record` 表（通过 HTTP 节点）
5. 情绪标签使用中文（焦虑/低落/愤怒/平静/积极等）
6. 情绪分值 0-100（越高越积极）

---

## 11. 后台 AI 任务 Workflow 设计

### 11.1 客户画像研判 Workflow（P1）

**触发方式**：FastAPI `POST /api/v1/profile/{source_id}/analyze` → BackgroundTasks → Dify Chat API

**Workflow 节点流程：**
```text
Start (inputs.raw_data + inputs.rules)
    ↓
code_preprocess (代码) ─── 数据预处理
  - 解析客户资料文本
  - 提取关键信息（学历、年龄、意向国家、语言成绩等）
    ↓
llm_match_rules (LLM) ─── 规则匹配
  - 输入：客户信息 + 画像规则（来自 profile_rule 表）
  - 输出：匹配的产品线 + 匹配度评分
    ↓
code_extract_match (代码) ─── 提取匹配结果
  - 解析 LLM 输出的 JSON
  - 标准化 match_result / match_score / matched_product
    ↓
llm_generate_recommendation (LLM) ─── 生成推荐
  - 输入：匹配结果 + 课程列表（来自 inputs.available_courses）
  - 输出：推荐项目列表 + 推荐理由
    ↓
Answer (返回结构化 JSON)
{
  "success": true,
  "task_type": "customer_profiling",
  "result": {
    "customer_name": "张三",
    "match_result": "matched",
    "matched_product": "英国硕士直通车",
    "match_score": 85.5,
    "match_reason": "学历背景（本科）、目标国家（英国）、专业方向（计算机）匹配",
    "recommended_programs": [
      {"program_name": "UCL 计算机硕士申请", "score": 90},
      {"program_name": "帝国理工 AI 硕士", "score": 85}
    ],
    "background_info": {
      "education": "本科",
      "target_country": ["英国"],
      "target_major": "计算机",
      "gpa": "3.5",
      "language_score": "雅思 6.5"
    }
  }
}
```

**FastAPI 侧调用流程（对齐 API 文档 9.3 节）：**
```python
def execute_profiling_async(source_id: int):
    db = SessionLocal()
    try:
        source = db.query(CustomerSource).filter_by(id=source_id).first()
        
        # 1. 读取画像规则
        rules = db.query(ProfileRule).filter_by(status=1).order_by(ProfileRule.priority.desc()).all()
        
        # 2. 调用 Dify Workflow（事务外）
        inputs = {
            "task_type": "customer_profiling",
            "raw_data": {
                "source_type": source.source_type,
                "content": source.raw_content or "",
                "file_url": source.file_url,
            },
            "rules": [{"product_line": r.product_line, "rule_content": r.rule_content} for r in rules],
        }
        result = dify_service.call_workflow(
            task_type="customer_profiling",
            inputs=inputs,
            query=f"请对以下客户资料进行画像研判：{source.raw_content[:500]}"
        )
        
        # 3. 保存研判结果（独立事务）
        if result.get("success"):
            with db.begin():
                profile = CustomerProfile(
                    customer_name=result["result"].get("customer_name"),
                    source_id=source_id,
                    background_info=result["result"].get("background_info"),
                    match_result=result["result"].get("match_result"),
                    matched_product=result["result"].get("matched_product"),
                    match_score=result["result"].get("match_score"),
                    match_reason=result["result"].get("match_reason"),
                    recommended_programs=result["result"].get("recommended_programs"),
                )
                db.add(profile)
                source.parse_status = 'success'
    except Exception as e:
        with db.begin():
            source.parse_status = 'failed'
            source.parse_error = str(e)[:500]
    finally:
        db.close()
```

### 11.2 智能报告生成 Workflow（P0）

**触发方式**：FastAPI `POST /api/v1/reports/generate` → BackgroundTasks → Dify Chat API

**报告类型与数据来源（对齐 API 文档 8.2 节）：**

| 报告类型 | 数据来源表 | 聚合方式 |
|----------|----------|---------|
| `daily_summary` | `employee_daily_report` | 按日期范围聚合 |
| `weekly_summary` | `employee_daily_report` + `crm_lead` + `student_feedback_ticket` | 多表聚合 |
| `customer_ops` | `crm_lead` + `crm_follow_up` | 按状态/负责人聚合 |
| `psych_weekly` | `student_psych_record` + `student_psych_alert` | 按风险等级聚合 |
| `complaint_weekly` | `student_feedback_ticket` | 按状态/分类聚合 |

**Workflow 节点流程：**
```text
Start (inputs.aggregated_data + inputs.report_type)
    ↓
llm_generate_report (LLM)
  - 输入：聚合后的业务数据（结构化 JSON）
  - 输出：报告内容（Markdown 格式）
    ↓
code_format_report (代码) ─── 格式化为 HTML（可选）
    ↓
Answer (返回结构化 JSON)
{
  "success": true,
  "task_type": "report_generation",
  "result": {
    "report_type": "daily_summary",
    "content": {
      "summary": "本周整体工作进展顺利...",
      "key_findings": ["客户咨询量环比增长15%", "签约转化率8.5%"],
      "risks": ["张三客户流失风险较高"],
      "suggestions": ["加强高意向客户跟进频率"]
    },
    "html": "<div>...</div>"
  }
}
```

**LLM 报告生成 Prompt：**
```text
你是一个专业的数据分析报告生成助手。请根据提供的业务数据，生成一份结构化的分析报告。

报告类型：{{report_type}}
数据周期：{{period_start}} 至 {{period_end}}

聚合数据：
{{aggregated_data}}

报告结构要求：
1. **概述**：200字以内的数据总结
2. **关键发现**：3-5条最重要的数据洞察
3. **风险提示**：识别潜在风险
4. **改进建议**：可操作的建议

输出格式：返回 JSON
{
  "summary": "概述文本",
  "key_findings": ["发现1", "发现2"],
  "risks": ["风险1", "风险2"],
  "suggestions": ["建议1", "建议2"]
}

注意：
- 所有数据必须基于提供的聚合数据，不得编造
- 数值保留原始精度
- 风险和建议要具体、可操作
```

---

## 12. Dify WebApp 配置

### 12.1 WebApp 设置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 应用名称 | 教育服务智能助手 | WebApp 页面标题 |
| 应用描述 | AI 驱动的留学教育服务智能助手 | 副标题 |
| 开场白 | 您好！我是教育服务智能助手，可以帮您查询课程、活动，解答留学相关问题。请问有什么可以帮您的？ | 首次进入显示 |
| 推荐问题 | ["有什么语言培训课程？", "近期有哪些留学讲座？", "英国留学需要什么条件？", "如何报名参加活动？"] | 快捷入口 |
| 对话模式 | Chatflow | - |
| 文件上传 | 关闭（MVP 阶段） | - |
| 语音输入 | 关闭（MVP 阶段） | - |
| 对话记录 | 开启 | 方便回顾 |
| 反馈功能 | 开启 | 收集用户评价 |

### 12.2 WebApp 与 Vue 前端的职责分工

| 功能 | Dify WebApp | Vue 3 后台 |
|------|-----------|-----------|
| AI 对话 | ✅ 核心功能 | ❌ 不实现 |
| 课程/活动查询 | ✅ 通过对话 | ✅ 列表 + 筛选 |
| 活动报名 | ✅ 通过对话 | ✅ 表单 |
| CRM 客户管理 | ❌ | ✅ 完整 CRUD |
| 请假审批 | ❌ | ✅ 审批流程 |
| 投诉处理 | ❌ | ✅ 工单管理 |
| 报告查看 | ❌ | ✅ 报告中心 |
| 数据看板 | ❌ | ✅ ECharts |

### 12.3 演示准备清单

```text
答辩演示前准备：
[ ] Dify WebApp 可正常访问
[ ] 客服 Agent Chatflow 已发布
[ ] HTTP 节点 URL 配置正确（host.docker.internal:8000）
[ ] DIFY_SERVICE_TOKEN 已配置
[ ] FastAPI 服务已启动（端口 8000）
[ ] MySQL 种子数据已插入
[ ] 知识库文档已上传
[ ] WebApp 开场白和推荐问题已设置
[ ] 测试对话流程：课程查询 → 活动查询 → 活动报名
[ ] 准备演示用对话脚本
[ ] 准备截图/录屏作为备用方案
```

---

## 13. 测试与验收清单

### 13.1 客服 Agent Chatflow 测试

```text
[ ] 用户输入"有什么课程？" → 意图识别为 course_query → 返回课程列表
[ ] 用户输入"最近有什么活动？" → 意图识别为 event_query → 返回活动列表
[ ] 用户输入"我想报名英国留学讲座" → 意图识别为 event_register → 引导填写信息
[ ] 用户输入"英国留学需要什么条件？" → 意图识别为 knowledge_policy → RAG 检索 → 返回政策信息
[ ] 用户输入"你好" → 意图识别为 chat_greeting → 友好回复
[ ] 课程列表为空时 → 返回"暂无相关课程，请尝试其他关键词"
[ ] 活动名额已满时 → 返回"抱歉，该活动名额已满"
[ ] HTTP 节点超时 → 返回"服务暂时繁忙"
[ ] 多轮对话 → 上下文保持（姓名、联系方式等）
```

### 13.2 学生助手 Chatflow 测试

```text
[ ] 学生表达焦虑 → 关怀回复 + 记录情绪到 psych_record
[ ] 学生查询申请进度 → HTTP 调用 application_progress → 返回进度
[ ] 学生表达自伤倾向 → 关怀回复 + 创建高危预警（alert）
[ ] 心理记录写入失败 → 不中断对话，后台记录错误
```

### 13.3 后台 Workflow 测试

```text
[ ] 客户研判：上传简历 → 触发研判 → 返回匹配结果（matched/partial/not_matched）
[ ] 报告生成：触发日报汇总 → 返回结构化报告 JSON
[ ] 研判失败（Dify 超时） → parse_status = failed + error_message
[ ] 报告生成失败 → status = failed + error_message
```

### 13.4 Dify ↔ FastAPI 联调测试

```text
[ ] Dify HTTP GET /api/v1/courses → 200 + 课程 JSON
[ ] Dify HTTP GET /api/v1/events → 200 + 活动 JSON
[ ] Dify HTTP POST /api/v1/events/1/register → 200 + 报名成功
[ ] Dify 调用未授权接口 → 403
[ ] 错误 Service Token → 403
[ ] Dify 调用不存在活动 → 40401
[ ] Dify 重复报名 → 40901
```

### 13.5 数据一致性测试（⭐ 对齐数据库文档第 14 章）

```text
[ ] 活动取消后 → Dify 查询活动时返回 status=cancelled
[ ] 课程下架后 → Dify 查询课程时不返回该课程（status=0 过滤）
[ ] 报名记录取消后 → 不显示在用户报名列表中
```

---

## 14. 附录

### 附录 A：Dify 环境配置参考

```bash
# Docker 运行 Dify
docker-compose up -d

# Dify 访问地址
# Web:     http://localhost:8080
# API:     http://localhost:8080/v1
# Console: http://localhost:8080/console

# 创建应用 → 选择 Chatflow / Workflow
# 发布应用 → 获取 API Key
```

### 附录 B：Dify API 调用参考（FastAPI 侧）

```python
# services/dify_service.py
import httpx
import json
from config import settings

class DifyService:
    def __init__(self):
        self.base_url = settings.DIFY_API_BASE_URL
        self.api_key = settings.DIFY_API_KEY

    def chat_blocking(self, query: str, user: str, inputs: dict = None) -> dict:
        """Chatflow 阻塞模式调用"""
        payload = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "blocking",
            "user": user,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.base_url}/chat-messages",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def call_workflow(self, task_type: str, inputs: dict, query: str) -> dict:
        """Workflow 阻塞模式调用（后台 AI 任务）"""
        result = self.chat_blocking(
            query=query,
            user="system-bot",
            inputs={**inputs, "task_type": task_type}
        )
        # 从 answer 中提取 JSON 结果
        answer_text = result.get("answer", "{}")
        # 尝试提取 JSON 块
        if "```json" in answer_text:
            answer_text = answer_text.split("```json")[1].split("```")[0]
        elif "```" in answer_text:
            answer_text = answer_text.split("```")[1].split("```")[0]
        try:
            return json.loads(answer_text.strip())
        except json.JSONDecodeError:
            return {"success": False, "error": "Dify 返回格式异常", "raw": answer_text}
```

### 附录 C：HTTP 节点 URL 参考（Dify 侧配置）

| 接口 | URL |
|------|-----|
| 健康检查 | `http://host.docker.internal:8000/api/v1/health` |
| 课程查询 | `http://host.docker.internal:8000/api/v1/courses?category={{category}}&keyword={{keyword}}&page=1&page_size=10` |
| 活动查询 | `http://host.docker.internal:8000/api/v1/events?status=upcoming&page=1&page_size=10` |
| 活动报名 | `http://host.docker.internal:8000/api/v1/events/{{event_id}}/register` |
| 客户查询 | `http://host.docker.internal:8000/api/v1/crm/leads?keyword={{keyword}}&page=1&page_size=5` |
| 创建会话 | `http://host.docker.internal:8000/api/v1/chat/session` |
| 心理记录 | `http://host.docker.internal:8000/api/v1/student/psych/record` |
| 申请进度 | `http://host.docker.internal:8000/api/v1/student/applications?student_id={{student_id}}` |

### 附录 D：意图识别种子数据（对齐 `intent_config` 表）

| intent_code | intent_name | scene | 典型问法示例 |
|------------|------------|-------|------------|
| `course_query` | 课程查询 | customer_service | "有什么课程"、"语言培训有哪些"、"雅思班多少钱" |
| `event_query` | 活动查询 | customer_service | "最近有什么讲座"、"有没有留学活动" |
| `event_register` | 活动报名 | customer_service | "我想报名"、"帮我报个名"、"参加活动" |
| `knowledge_policy` | 留学政策 | customer_service | "英国留学条件"、"签证怎么办"、"需要什么材料" |
| `knowledge_overseas` | 海外生活 | customer_service | "英国住宿"、"国外生活注意什么" |
| `knowledge_company` | 公司业务 | customer_service | "你们提供什么服务"、"怎么收费" |
| `chat_greeting` | 问候 | customer_service | "你好"、"在吗"、"hi" |
| `lead_query` | 客户查询 | enterprise | "我的客户"、"查一下张三"、"意向客户" |
| `daily_report` | 日报 | enterprise | "今天日报"、"汇报工作" |
| `leave_request` | 请假 | student | "我要请假"、"请假几天" |
| `psych_check_in` | 心理关怀 | student | "最近压力大"、"心情不好"、"焦虑" |
| `application_progress` | 申请进度 | student | "我的申请怎么样了"、"offer来了吗" |
| `emotion_express` | 情绪表达 | student | "好累"、"开心"、"想家了" |

### 附录 E：与三份核心文档的一致性确认

| 核心文档要求 | Dify 工作流文档落实 |
|-------------|-------------------|
| 架构文档 4.1：Dify 与 FastAPI 职责边界 | ✅ 1.2 节完整对齐 |
| 架构文档 4.2：必须遵守的边界（6条） | ✅ 1.3 节逐条落实 |
| 架构文档 4.3：Dify 白名单接口（7个） | ✅ 1.4 节 + 附录 C |
| 架构文档 4.4：Dify Service Token | ✅ 1.5 节 + 5.1 节 |
| 架构文档 5.2：客服课程查询链路 | ✅ 10.1 节完整 Chatflow |
| 架构文档 5.3：活动报名链路 | ✅ 5.4 节 + 10.1 节 |
| 架构文档 5.4：客户研判异步链路 | ✅ 11.1 节 Workflow |
| 架构文档 5.5：报告生成链路 | ✅ 11.2 节 Workflow |
| API 文档第 10 章：Dify 工具 API | ✅ 5.2-5.5 节 HTTP 节点 |
| API 文档第 11 章：异步任务规范 | ✅ 4.1 节 + 第 11 章 |
| 数据库文档 6.8.1：intent_config 表 | ✅ 附录 D 意图种子数据 |
| 数据库文档 6.5：chat_session/chat_message | ✅ 对话上下文管理 |
| 数据库文档 8：状态枚举字典 | ✅ HTTP 节点错误码映射 |

### 附录 F：版本历史

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|---------|------|
| V1.0 | 2026-07-09 | 初始版本，基于架构文档 V1.1、API 文档 V1.1、数据库文档 V2.0 编制 | 全栈组 |
| V1.1 | 2026-07-09 | 全链路评审定稿，对齐架构 V1.2、API V1.2、数据库 V2.1、前端 V1.1，明确 P0 Chatflow、P0 报告 Workflow 和 P1 客户研判 Workflow 边界 | 全栈组 |

---

> **文档结束**  
> 教育服务系统 — Dify 工作流设计规范文档 V1.1  
> **核心原则**：Dify 做大脑（意图识别 + 对话生成 + 工作流编排），FastAPI 做手脚（业务接口 + 数据读写 + 权限校验），MySQL 做记忆（唯一真实数据源）。
