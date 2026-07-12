-- Iteration 3 周期比较验收 Seed
-- 使用保留 ID 930001-930099 和 ITER3_TEST_ 标记前缀，生成两个相邻周期的合成数据。
-- INSERT IGNORE 保证幂等：已存在同主键记录时跳过，不会覆盖正常数据。
-- 配套 cleanup: migrations/seeds/20260712_iteration3_comparison.cleanup.sql

-- ── 周期一（上一周期）：2026-07-01 ~ 2026-07-07 ──

-- application_risk 上一周期报告
INSERT IGNORE INTO report_generation (id, report_type, status, trigger_source,
    period_start, period_end, title, report_content, data_quality,
    generated_by, create_time, update_time)
VALUES (930001, 'application_risk', 'completed', 'manual',
    '2026-07-01', '2026-07-07',
    'ITER3_TEST_上一周期申请风险报告',
    JSON_OBJECT('summary', 'ITER3_TEST 上一周期', 'metrics',
        JSON_OBJECT('total_applications', 50, 'high_risk_count', 3,
            'medium_risk_count', 10, 'low_risk_count', 37,
            'overdue_count', 5, 'missing_material_count', 2)),
    JSON_OBJECT('level', 'ok', 'warnings', JSON_ARRAY()),
    1, '2026-07-07 12:00:00', '2026-07-07 12:00:00');

-- application_risk 当前周期报告（上升趋势：高风险从3→8）
INSERT IGNORE INTO report_generation (id, report_type, status, trigger_source,
    period_start, period_end, title, report_content, data_quality,
    generated_by, create_time, update_time)
VALUES (930002, 'application_risk', 'completed', 'manual',
    '2026-07-08', '2026-07-14',
    'ITER3_TEST_当前周期申请风险报告',
    JSON_OBJECT('summary', 'ITER3_TEST 当前周期', 'metrics',
        JSON_OBJECT('total_applications', 60, 'high_risk_count', 8,
            'medium_risk_count', 15, 'low_risk_count', 37,
            'overdue_count', 4, 'missing_material_count', 1)),
    JSON_OBJECT('level', 'ok', 'warnings', JSON_ARRAY()),
    1, '2026-07-14 12:00:00', '2026-07-14 12:00:00');

-- channel_roi 上一周期报告（三个渠道，含零成本渠道）
INSERT IGNORE INTO report_generation (id, report_type, status, trigger_source,
    period_start, period_end, title, report_content, data_quality,
    generated_by, create_time, update_time)
VALUES (930003, 'channel_roi', 'completed', 'manual',
    '2026-07-01', '2026-07-07',
    'ITER3_TEST_上一周期渠道ROI报告',
    JSON_OBJECT('summary', 'ITER3_TEST 上一周期渠道ROI', 'channel_metrics', JSON_ARRAY(
        JSON_OBJECT('channel', 'search', 'leads', 100, 'signed_count', 10,
            'cost', 5000, 'paid_amount', 50000, 'roi', 9.0),
        JSON_OBJECT('channel', 'social', 'leads', 80, 'signed_count', 5,
            'cost', 3000, 'paid_amount', 20000, 'roi', 5.67),
        JSON_OBJECT('channel', 'referral', 'leads', 50, 'signed_count', 8,
            'cost', 0, 'paid_amount', 40000, 'roi', null)
    )),
    JSON_OBJECT('level', 'ok', 'warnings', JSON_ARRAY()),
    1, '2026-07-07 12:00:00', '2026-07-07 12:00:00');

-- channel_roi 当前周期报告（search渠道ROI下降）
INSERT IGNORE INTO report_generation (id, report_type, status, trigger_source,
    period_start, period_end, title, report_content, data_quality,
    generated_by, create_time, update_time)
VALUES (930004, 'channel_roi', 'completed', 'manual',
    '2026-07-08', '2026-07-14',
    'ITER3_TEST_当前周期渠道ROI报告',
    JSON_OBJECT('summary', 'ITER3_TEST 当前周期渠道ROI', 'channel_metrics', JSON_ARRAY(
        JSON_OBJECT('channel', 'search', 'leads', 120, 'signed_count', 8,
            'cost', 8000, 'paid_amount', 45000, 'roi', 4.63),
        JSON_OBJECT('channel', 'social', 'leads', 90, 'signed_count', 6,
            'cost', 3500, 'paid_amount', 25000, 'roi', 6.14),
        JSON_OBJECT('channel', 'referral', 'leads', 60, 'signed_count', 9,
            'cost', 0, 'paid_amount', 50000, 'roi', null)
    )),
    JSON_OBJECT('level', 'ok', 'warnings', JSON_ARRAY()),
    1, '2026-07-14 12:00:00', '2026-07-14 12:00:00');

-- service_sla 上一周期报告
INSERT IGNORE INTO report_generation (id, report_type, status, trigger_source,
    period_start, period_end, title, report_content, data_quality,
    generated_by, create_time, update_time)
VALUES (930005, 'service_sla', 'completed', 'manual',
    '2026-07-01', '2026-07-07',
    'ITER3_TEST_上一周期SLA报告',
    JSON_OBJECT('summary', 'ITER3_TEST 上一周期', 'sla_overview',
        JSON_OBJECT('total_complaints', 20, 'complaint_response_overdue_count', 3,
            'complaint_resolve_overdue_count', 2, 'avg_first_response_hours', 4.5)),
    JSON_OBJECT('level', 'ok', 'warnings', JSON_ARRAY()),
    1, '2026-07-07 12:00:00', '2026-07-07 12:00:00');

-- service_sla 当前周期报告（投诉上升：20→32，超时3→8）
INSERT IGNORE INTO report_generation (id, report_type, status, trigger_source,
    period_start, period_end, title, report_content, data_quality,
    generated_by, create_time, update_time)
VALUES (930006, 'service_sla', 'completed', 'manual',
    '2026-07-08', '2026-07-14',
    'ITER3_TEST_当前周期SLA报告',
    JSON_OBJECT('summary', 'ITER3_TEST 当前周期', 'sla_overview',
        JSON_OBJECT('total_complaints', 32, 'complaint_response_overdue_count', 8,
            'complaint_resolve_overdue_count', 5, 'avg_first_response_hours', 6.2)),
    JSON_OBJECT('level', 'ok', 'warnings', JSON_ARRAY()),
    1, '2026-07-14 12:00:00', '2026-07-14 12:00:00');
