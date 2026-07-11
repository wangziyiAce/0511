-- Iteration 2B.2 申请风险验收数据（仅限非生产测试环境）
-- A1024：高风险；A1058：中风险；A1091：低风险。
-- application_id 是 BIGINT，因此数据库保存 1024/1058/1091，A 前缀只用于验收展示。
-- 重复执行时先清理同一组合 ID，不影响其他申请数据。

START TRANSACTION;

DELETE FROM application_material_item
 WHERE application_id IN (1024, 1058, 1091);

-- A1024：逾期 + 两项必填材料缺失 + 超过 7 天未更新 + 无下一步动作。
-- 预期由确定性规则计算为最高风险，并排在 position 1。
INSERT INTO application_material_item (
    application_id, student_id, owner_id, material_name, required,
    deadline, submitted_time, status, update_time, create_time
) VALUES
    (1024, 990024, 990001, 'ITER2B2_TEST_TRANSCRIPT', 1,
     DATE_SUB(CURDATE(), INTERVAL 2 DAY), NULL, 'pending',
     DATE_SUB(NOW(), INTERVAL 10 DAY), DATE_SUB(NOW(), INTERVAL 10 DAY)),
    (1024, 990024, 990001, 'ITER2B2_TEST_RECOMMENDATION', 1,
     DATE_SUB(CURDATE(), INTERVAL 2 DAY), NULL, 'pending',
     DATE_SUB(NOW(), INTERVAL 10 DAY), DATE_SUB(NOW(), INTERVAL 10 DAY));

-- A1058：7 天内截止 + 一项必填材料缺失 + 无下一步动作。
-- 预期进入 risk_items，但风险分低于 A1024。
INSERT INTO application_material_item (
    application_id, student_id, owner_id, material_name, required,
    deadline, submitted_time, status, update_time, create_time
) VALUES
    (1058, 990058, 990001, 'ITER2B2_TEST_PERSONAL_STATEMENT', 1,
     DATE_ADD(CURDATE(), INTERVAL 5 DAY), NULL, 'pending',
     NOW(), NOW());

-- A1091：材料已提交、30 天内截止且近期更新，用于验证低风险不会进入 risk_items。
INSERT INTO application_material_item (
    application_id, student_id, owner_id, material_name, required,
    deadline, submitted_time, status, update_time, create_time
) VALUES
    (1091, 990091, 990001, 'ITER2B2_TEST_PASSPORT', 1,
     DATE_ADD(CURDATE(), INTERVAL 20 DAY), NOW(), 'submitted',
     NOW(), NOW());

COMMIT;

