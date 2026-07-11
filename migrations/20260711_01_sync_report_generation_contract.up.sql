-- Iteration 2B.2：同步 report_generation 数据库契约（MySQL 8）
-- contract:report_type=customer_ops,daily_summary,weekly_summary,psych_weekly,complaint_weekly,application_risk,sales_funnel,channel_roi,service_sla,action_closure
-- contract:status=pending,generating,completed,failed
-- contract:trigger_source=manual,schedule,retry,system
--
-- 执行前提：连接时已经选择目标数据库。脚本先检查旧数据，再修改字段，避免
-- MySQL 在收紧 ENUM 时把非法值静默转换为空字符串。

DELIMITER $$

DROP PROCEDURE IF EXISTS validate_report_generation_contract$$

CREATE PROCEDURE validate_report_generation_contract()
BEGIN
    DECLARE invalid_report_type_length BIGINT DEFAULT 0;
    DECLARE invalid_status_count BIGINT DEFAULT 0;
    DECLARE invalid_trigger_source_count BIGINT DEFAULT 0;

    SELECT COUNT(*)
      INTO invalid_report_type_length
      FROM report_generation
     WHERE CHAR_LENGTH(report_type) > 64;

    IF invalid_report_type_length > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'report_generation.report_type 存在超过 64 字符的旧值，迁移已停止';
    END IF;

    SELECT COUNT(*)
      INTO invalid_status_count
      FROM report_generation
     WHERE status NOT IN ('pending', 'generating', 'completed', 'failed');

    IF invalid_status_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'report_generation.status 存在未知旧值，迁移已停止';
    END IF;

    SELECT COUNT(*)
      INTO invalid_trigger_source_count
      FROM report_generation
     WHERE trigger_source NOT IN ('manual', 'schedule', 'retry', 'system');

    IF invalid_trigger_source_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'report_generation.trigger_source 存在未知旧值，迁移已停止';
    END IF;
END$$

CALL validate_report_generation_contract()$$
DROP PROCEDURE validate_report_generation_contract$$

DELIMITER ;

ALTER TABLE report_generation
    MODIFY COLUMN report_type VARCHAR(64) NOT NULL COMMENT '报告类型编码，Registry 驱动，数据库保留扩展能力',
    MODIFY COLUMN status ENUM('pending', 'generating', 'completed', 'failed') NOT NULL DEFAULT 'pending' COMMENT '任务状态',
    MODIFY COLUMN trigger_source ENUM('manual', 'schedule', 'retry', 'system') NOT NULL DEFAULT 'manual' COMMENT '触发来源';

