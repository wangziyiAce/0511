# Iteration 3 完成报告

## 1. 结论

Iteration 3（周期对比与受控跨报告分析）已完成全部 10 个任务。后端 359 passed，前端 54 passed，生产构建通过。

## 2. 实施任务总结

| Task | 描述 | Commit | 测试 |
|------|------|--------|------|
| 1 | 比较响应契约 | `0be49e4` | Task 1-5 基础 |
| 2 | 受控 Metric Catalog | `aaa18e1` | direct/derived/dimensional 三模式 |
| 3 | 比较周期解析 | `d17586d`~`be67b05` | 5 种周期模式 |
| 4 | Decimal 计算与 DataQuality 门禁 | `859b480`~`cd1aefc` | zero/None/负ROI/质量阻断 |
| 5 | 只读指标比较工具与 Evidence | `4e83008`~`2420326` | 29 tests |
| 6 | 跨报告 Catalog、权限和工具预算 | `dd82360`~`b9abd9d` | 25 tests |
| 7 | 因果语言保护与四段回答 | `7065daf` | 13 tests |
| 8 | 意图识别与 Service 编排 | `f52255d` | 系统集成 |
| 9 | 前端比较与关系展示 | `d661689` | 前端 54 tests |
| 10 | MySQL Seed 与完成报告 | 本次 commit | 两轮验证 |

## 3. 支持能力

### 同类报告周期比较

- 本周/上周、本月/上月、最近7天/前7天、最近30天/前30天、指定月份对比
- Python Decimal 计算 delta/change_rate/direction
- None 不转 0；previous=0 时 change_rate=None
- 双周期 DataQuality 独立保存，质量门禁控制趋势输出
- 每指标/维度生成 current/previous/delta/change_rate 四个 Evidence

### 受控跨报告分析

- 四组静态白名单（当前仅 `channel_roi+sales_funnel` 可执行）
- 三组因单侧无注册指标被安全阻断（需 Task 2 修订解除）
- 逐报告权限预检 — fail-closed，无部分数据泄露
- 工具预算上限 + 空工具拒绝 + unsupported_gaps 阻断
- 因果断言防护：五词禁止 + Python 强制 cannot_confirm 区块

### 前端展示

- 比较表格：指标、维度、上期/当期值、差值、变化率、方向箭头
- 关系分析：四区（确认事实/相关信号/可能解释/无法确认），彩色分区卡片
- permission_denied 时自动隐藏比较和分析区块

## 4. 不受支持的能力（明确排除）

- Redis 缓存、会话持久化、NL2SQL
- 任意报告组合、自定义指标、多 Agent
- RAG、自动异常检测、智能告警
- 修改原 Aggregator 指标公式

## 5. 安全约束保持

- 禁止 eval、动态 import、任意表达式、LLM 指定路径/resolver/组合/工具
- 所有报告类型、指标、角色、工具预算由 Python 静态控制
- 无部分数据泄露：权限失败 = 无工具调用
- 错误消息不暴露报告存在性或数据量

## 6. 最终验证结果

### 后端（两轮一致）

```
359 passed, 2 deselected, 0 failed
```

### 前端

```
4 files / 54 tests passed
生产构建通过
92 个 OpenAPI operation 校验通过
```

### 修改文件审查

全部修改在允许范围内：
- `services/reporting/assistant/**`（schemas, metric_catalog, metric_resolvers, comparison_period, comparison, tools, guardrails, cross_report_catalog, answer_composer, intent_parser, service）
- `tests/test_report_assistant_*.py`
- `frontend/src/types/report-assistant.ts`
- `frontend/src/components/report-assistant/ReportAssistantComparison.tsx`
- `frontend/src/components/report-assistant/ReportAssistantRelationship.tsx`
- `frontend/src/components/report-assistant/ReportAssistantMessage.tsx`
- `migrations/seeds/20260712_iteration3_comparison.*.sql`

未修改禁止文件：main.py, config.py, routers/__init__.py, models/report.py, services/reporting/rules.py, services/reporting/aggregators.py

## 7. 已知限制

- `complaint_weekly`、`customer_ops`、`action_closure` 虽可通过 direct_path 提取指标，但尚未注册到 Metric Catalog，导致三组跨报告组合被安全阻断
- 密钥轮换未完成（用户已接受的例外）
- 真实验收 Seed 未经 MySQL 实测（无数据库连接）
- 真实 LLM Smoke Test 未执行（无 LLM 连接）

## 8. 密钥安全

- `.env` 被 `.gitignore` 忽略
- 本报告不含真实密钥
- 推送前必须完成密钥轮换

## 9. 建议后续

1. 批准 Task 2 修订方案 → 解除三组跨报告阻断
2. 连接真实 MySQL 运行验收 Seed
3. 连接真实 LLM 运行 Smoke Test
4. 轮换所有历史密钥
5. 评审是否进入 Iteration 4
