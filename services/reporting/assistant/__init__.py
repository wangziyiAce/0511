"""智能报告助手 — 智能交互与决策层。

本包在现有 Registry → Aggregator → Rules → Schema → Orchestrator → Renderer
链路之上增加自然语言交互能力。管理者无需知道报告编码即可用自然语言生成、
查询和追问报告。

本层只负责：
- 自然语言意图识别
- 参数规范化（时间、筛选条件）
- 置信度与澄清判断
- 调用受控报告工具
- 基于工具结果组装回答

本层不负责：
- 直接访问数据库（通过已有 Aggregator 和 Orchestrator 间接使用）
- 计算业务指标（复用 rules.py）
- 生成 HTML（复用 renderer.py）
- 写入 report_action（Iteration 4 实现）

架构位置：
    用户自然语言输入
    → POST /api/v1/reports/assistant/messages
    → Assistant Service（本包）
    → 受控 Python Tools
    → 现有事实链路（Registry → Aggregator → Rules → Orchestrator）

面试表达：
"智能报告助手是在不推翻十类报告和规则引擎的前提下，增加了一层自然语言交互。
LLM 只做意图识别和参数填充，所有业务数字仍由 SQL 和规则引擎计算，
所有写操作必须经过权限校验和用户确认。"
"""
