-- Iteration 3 周期比较验收 Seed 清理
-- 双重保护：同时使用保留 ID 范围和 ITER3_TEST_ 标题前缀，
-- 确保只删除验收种子行，不影响正常业务数据。

DELETE FROM report_generation
WHERE id BETWEEN 930001 AND 930099
   OR title LIKE 'ITER3_TEST_%';

-- 验证清理结果：应为 0 行（可选，取消注释以启用）
-- SELECT COUNT(*) AS remaining_iter3_seed_rows
-- FROM report_generation
-- WHERE id BETWEEN 930001 AND 930099
--    OR title LIKE 'ITER3_TEST_%';
