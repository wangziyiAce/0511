"""智能报告 V2 服务包。

本包将报告模块拆分为独立子模块，各司其职：

1. ``rules``：确定性计算 — 风险分、ROI、SLA 是否超时。
   这些数字必须由代码和 SQL 生成，不能交给大模型自由发挥。
2. ``schemas``：每种报告独立的 Pydantic 内容契约，前端和 LLM 按此对齐。
3. ``registry``：报告类型注册表，登记聚合器、模板、权限、默认周期。
4. ``aggregators``：面向数据库取数，把业务事实聚合成可解释的指标快照。
5. ``orchestrator``：任务状态编排、幂等、重试、LLM 调用与 HTML 渲染。
6. ``ai_generator``：纯 Python LLM 解释层 — Prompt 构建 → 模型调用 →
   JSON 解析 → Schema 校验 → 修复重试。
7. ``llm_config``：LLM 连接参数管理，从环境变量读取，不与公共 config 耦合。
8. ``llm_client``：ReportLLMClient — 封装 OpenAI SDK，统一重试、日志、脱敏。
9. ``prompt_builder``：System/User Prompt 模板 + Python 层面数据脱敏。
10. ``renderer``：后端 HTML 模板渲染。

面试表达：
"我把智能报告模块从单文件 MVP 重构成注册表驱动的报告编排系统，
AI 解释从 Dify Chatflow 迁移为纯 Python LLM 调用，保证数字可追溯、
报告类型可扩展、LLM 只做解释不编造指标。"
"""
