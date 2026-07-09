-- ============================================================
-- 智能报告模块 — 种子数据
-- ============================================================
-- 用途: 为报告模块提供测试数据，方便联调和演示
-- 使用: mysql -u root -p education_service < seed/seed_report.sql
-- 数据: 3 条已完成报告 + 1 条失败报告（覆盖 3 种报告类型）
-- ============================================================

-- 1. 员工日报汇总（已完成）
INSERT INTO `report_generation` (`report_type`, `report_title`, `report_content`, `report_html`, `period_start`, `period_end`, `generated_by`, `status`, `create_time`)
VALUES (
    'daily_summary',
    '2026年7月第1周日报汇总',
    JSON_OBJECT(
        'summary', '本周团队整体工作进展顺利，共提交日报 35 份，覆盖率达 87.5%。咨询部签约 2 单，市场部收集有效线索 45 条。',
        'key_findings', JSON_ARRAY(
            '客户咨询量环比增长 15%，英国留学咨询占比最高（40%）',
            '签约转化率 8.5%，较上周提升 1.2 个百分点',
            '张三客户进入签约阶段，预计下周完成合同',
            '市场部新增合作渠道 2 个'
        ),
        'risks', JSON_ARRAY(
            '李四客户出现流失信号，连续 2 周未回复跟进消息',
            '澳洲签证政策变动可能影响 3 位在办学生'
        ),
        'suggestions', JSON_ARRAY(
            '加强高意向客户跟进频率，建议每日至少 1 次触达',
            '针对澳洲签证政策变动，提前准备应对方案并通知相关学生',
            '本周五组织签约经验分享会'
        )
    ),
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>2026年7月第1周日报汇总</title><style>body{font-family:"Microsoft YaHei",sans-serif;max-width:800px;margin:0 auto;padding:20px}h1{color:#1a1a2e;border-bottom:2px solid #16213e;padding-bottom:10px}h2{color:#0f3460;margin-top:24px}.summary{background:#f0f4ff;padding:16px;border-radius:8px;margin:12px 0}ul{line-height:1.8}.footer{margin-top:32px;color:#999;font-size:12px;border-top:1px solid #eee;padding-top:12px}</style></head><body><h1>2026年7月第1周日报汇总</h1><div class="summary"><p>本周团队整体工作进展顺利，共提交日报 35 份，覆盖率达 87.5%。咨询部签约 2 单，市场部收集有效线索 45 条。</p></div><h2>📊 关键发现</h2><ul><li>客户咨询量环比增长 15%，英国留学咨询占比最高（40%）</li><li>签约转化率 8.5%，较上周提升 1.2 个百分点</li><li>张三客户进入签约阶段，预计下周完成合同</li><li>市场部新增合作渠道 2 个</li></ul><h2>⚠️ 风险预警</h2><ul><li>李四客户出现流失信号，连续 2 周未回复跟进消息</li><li>澳洲签证政策变动可能影响 3 位在办学生</li></ul><h2>💡 改进建议</h2><ul><li>加强高意向客户跟进频率，建议每日至少 1 次触达</li><li>针对澳洲签证政策变动，提前准备应对方案并通知相关学生</li><li>本周五组织签约经验分享会</li></ul><div class="footer">本报告由教育服务系统自动生成 | AI 驱动 · 数据驱动决策</div></body></html>',
    '2026-07-01',
    '2026-07-07',
    1,
    'completed',
    '2026-07-07 18:00:00'
);

-- 2. 全域客户经营分析（已完成）
INSERT INTO `report_generation` (`report_type`, `report_title`, `report_content`, `report_html`, `period_start`, `period_end`, `generated_by`, `status`, `create_time`)
VALUES (
    'customer_ops',
    '2026年7月第1周客户经营分析',
    JSON_OBJECT(
        'summary', '本周新增客户线索 52 条，签约转化 4 单，转化率 7.7%。客户主要来源为线上咨询（60%）和老客户推荐（25%）。',
        'key_findings', JSON_ARRAY(
            '线上咨询渠道贡献最多线索（31 条，占 60%）',
            '英国留学仍为最热门方向（意向占比 45%）',
            '本周流失客户 3 人，主要原因为价格因素和竞品对比',
            '高意向客户池（qualified）扩大至 28 人'
        ),
        'risks', JSON_ARRAY(
            '竞品"XX留学"近期加大广告投放，可能分流线上线索',
            '澳洲签证政策变动导致 2 位意向客户观望'
        ),
        'suggestions', JSON_ARRAY(
            '加大英国 G5 院校的产品包装和推广',
            '针对价格敏感客户推出分期付款方案',
            '强化老客户推荐激励机制，提升转介绍率'
        )
    ),
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>客户经营分析</title><style>body{font-family:"Microsoft YaHei",sans-serif;max-width:800px;margin:0 auto;padding:20px}h1{color:#1a1a2e;border-bottom:2px solid #16213e;padding-bottom:10px}h2{color:#0f3460;margin-top:24px}.summary{background:#f0f4ff;padding:16px;border-radius:8px}ul{line-height:1.8}</style></head><body><h1>2026年7月第1周客户经营分析</h1><div class="summary"><p>本周新增客户线索 52 条，签约转化 4 单，转化率 7.7%。</p></div><h2>📊 关键发现</h2><ul><li>线上咨询渠道贡献最多线索（31 条，占 60%）</li><li>英国留学仍为最热门方向</li></ul><h2>⚠️ 风险预警</h2><ul><li>竞品加大广告投放</li></ul><h2>💡 改进建议</h2><ul><li>加大英国 G5 院校产品包装</li></ul></body></html>',
    '2026-07-01',
    '2026-07-07',
    1,
    'completed',
    '2026-07-07 18:30:00'
);

-- 3. 投诉处理周报（已完成）
INSERT INTO `report_generation` (`report_type`, `report_title`, `report_content`, `period_start`, `period_end`, `generated_by`, `status`, `create_time`)
VALUES (
    'complaint_weekly',
    '2026年7月第1周投诉处理周报',
    JSON_OBJECT(
        'summary', '本周共收到投诉工单 8 件，已解决 6 件，处理中 2 件。平均处理时长 1.5 天，较上周缩短 0.3 天。',
        'key_findings', JSON_ARRAY(
            '教学质量类投诉最多（4 件，占 50%），集中在课程进度和师资匹配',
            '服务态度类投诉 2 件，已全部处理并回访确认满意',
            '匿名投诉 1 件，涉及费用透明度问题，已启动核查'
        ),
        'risks', JSON_ARRAY(
            '教学质量投诉呈上升趋势，需关注师资匹配流程',
            '费用透明度投诉虽少但影响品牌信誉'
        ),
        'suggestions', JSON_ARRAY(
            '优化师资匹配流程，试听课后收集学生反馈',
            '在官网和合同中清晰公示所有费用明细',
            '建立投诉处理SOP，确保 24 小时内首次响应'
        )
    ),
    '2026-07-01',
    '2026-07-07',
    1,
    'completed',
    '2026-07-07 19:00:00'
);

-- 4. 员工日报汇总（失败 — 用于测试重试功能）
INSERT INTO `report_generation` (`report_type`, `report_title`, `period_start`, `period_end`, `generated_by`, `status`, `error_message`, `create_time`)
VALUES (
    'daily_summary',
    '2026年6月第4周日报汇总（失败测试）',
    '2026-06-24',
    '2026-06-30',
    1,
    'failed',
    'Dify 调用超时（120秒）：Workflow 执行超时，请检查 Dify 服务状态或增加超时时间',
    '2026-07-01 10:00:00'
);

-- 5. 报告定时任务（示例配置，P1 表）
INSERT INTO `report_schedule` (`report_type`, `cron_expression`, `recipients`, `status`, `create_time`)
VALUES
    ('daily_summary', '0 9 * * 1', JSON_ARRAY(JSON_OBJECT('user_id', 1, 'channel', 'system')), 1, NOW()),
    ('customer_ops', '0 8 1 * *', JSON_ARRAY(JSON_OBJECT('user_id', 1, 'channel', 'system'), JSON_OBJECT('user_id', 2, 'channel', 'email')), 1, NOW()),
    ('psych_weekly', '0 10 * * 5', JSON_ARRAY(JSON_OBJECT('user_id', 3, 'channel', 'system')), 1, NOW());
