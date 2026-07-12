-- Iteration 2B.2 回滚：撤销有限枚举约束，回到迁移前兼容的宽松字符串字段。
--
-- 仓库无法证明手工 ALTER 之前的完整 ENUM 定义，因此 downgrade 以数据安全为先：
-- 保留所有当前合法值，不把报告类型或状态静默截断为更窄的历史集合。

ALTER TABLE report_generation
    MODIFY COLUMN report_type VARCHAR(64) NOT NULL COMMENT '报告类型编码',
    MODIFY COLUMN status VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT '任务状态',
    MODIFY COLUMN trigger_source VARCHAR(16) NOT NULL DEFAULT 'manual' COMMENT '触发来源';

