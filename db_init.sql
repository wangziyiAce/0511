-- ============================================================
-- 教育服务系统 - 数据库初始化脚本
-- 数据库: MySQL 8.0
-- 字符集: utf8mb4
-- 引擎: InnoDB
-- 基于《客户需求表.xlsx》+ 现有 sql设计草稿.txt 整理
-- 生成时间: 2026-07-07
-- ============================================================

SET NAMES utf8mb4;

-- ============================================================
-- 1. 基础系统表
-- ============================================================

-- 系统角色字典表
DROP TABLE IF EXISTS `sys_role`;
CREATE TABLE `sys_role` (
    `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `role_code`     VARCHAR(32)     NOT NULL                COMMENT '角色编码（如 ADMIN/EMPLOYEE/STUDENT）',
    `role_name`     VARCHAR(64)     NOT NULL                COMMENT '角色名称',
    `description`   VARCHAR(255)    DEFAULT NULL            COMMENT '角色描述',
    `status`        TINYINT         NOT NULL DEFAULT 1      COMMENT '状态 1=启用 0=禁用',
    `create_time`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_role_code` (`role_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统角色字典表';

-- 统一用户表
DROP TABLE IF EXISTS `sys_user`;
CREATE TABLE `sys_user` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `username`          VARCHAR(64)     NOT NULL                COMMENT '登录账号',
    `password_hash`     VARCHAR(255)    NOT NULL                COMMENT '密码哈希',
    `real_name`         VARCHAR(64)     NOT NULL                COMMENT '真实姓名',
    `user_type`         ENUM('student','employee','admin') NOT NULL COMMENT '用户类型',
    `role_id`           BIGINT UNSIGNED DEFAULT NULL            COMMENT '关联角色ID',
    `department`        VARCHAR(128)    DEFAULT NULL            COMMENT '所属部门/院系',
    `contact_info`      VARCHAR(128)    DEFAULT NULL            COMMENT '联系方式（手机号/邮箱）',
    `avatar_url`        VARCHAR(512)    DEFAULT NULL            COMMENT '头像URL',
    `status`            ENUM('normal','disabled') NOT NULL DEFAULT 'normal' COMMENT '账号状态',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_user_type` (`user_type`),
    KEY `idx_role_id` (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='统一用户表（学生/员工/管理员）';

-- 组织架构表
DROP TABLE IF EXISTS `sys_organization`;
CREATE TABLE `sys_organization` (
    `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `org_name`      VARCHAR(128)    NOT NULL                COMMENT '组织/部门名称',
    `parent_id`     BIGINT UNSIGNED DEFAULT NULL            COMMENT '上级组织ID',
    `org_level`     TINYINT         NOT NULL DEFAULT 1      COMMENT '层级 1=公司 2=部门 3=小组',
    `manager_id`    BIGINT UNSIGNED DEFAULT NULL            COMMENT '负责人ID',
    `sort_order`    INT             NOT NULL DEFAULT 0      COMMENT '排序权重',
    `status`        TINYINT         NOT NULL DEFAULT 1      COMMENT '状态 1=启用 0=停用',
    `create_time`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_parent_id` (`parent_id`),
    KEY `idx_manager_id` (`manager_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='组织架构表';

-- ============================================================
-- 2. 客户研判模块（需求1）
-- ============================================================

-- 用户画像研判规则表
DROP TABLE IF EXISTS `profile_rule`;
CREATE TABLE `profile_rule` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `product_line`      VARCHAR(64)     NOT NULL                COMMENT '产品线（如：留学申请/背景提升/硕博连读）',
    `rule_name`         VARCHAR(128)    NOT NULL                COMMENT '规则名称',
    `rule_content`      JSON            NOT NULL                COMMENT '研判规则配置（JSON格式，含学历/语言/年龄等条件）',
    `match_prompt`      TEXT            DEFAULT NULL            COMMENT 'AI研判使用的系统提示词',
    `priority`          TINYINT         NOT NULL DEFAULT 0      COMMENT '优先级 数值越大越优先',
    `status`            TINYINT         NOT NULL DEFAULT 1      COMMENT '状态 1=启用 0=禁用',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_product_line` (`product_line`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户画像研判规则表';

-- 客户信息来源记录表（文本/PDF简历/Excel等上传来源）
DROP TABLE IF EXISTS `customer_source`;
CREATE TABLE `customer_source` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `source_type`       ENUM('text','pdf_resume','excel','import','manual') NOT NULL COMMENT '信息来源类型',
    `raw_content`       TEXT            DEFAULT NULL            COMMENT '原始文本内容',
    `file_url`          VARCHAR(512)    DEFAULT NULL            COMMENT '上传文件URL（PDF/Excel）',
    `file_name`         VARCHAR(255)    DEFAULT NULL            COMMENT '原始文件名',
    `parse_status`      ENUM('pending','success','failed') NOT NULL DEFAULT 'pending' COMMENT '解析状态',
    `parse_result`      JSON            DEFAULT NULL            COMMENT 'AI解析后的结构化结果',
    `parse_error`       TEXT            DEFAULT NULL            COMMENT '解析失败原因',
    `operator_id`       BIGINT UNSIGNED DEFAULT NULL            COMMENT '操作人ID',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_source_type` (`source_type`),
    KEY `idx_parse_status` (`parse_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户信息来源记录表';

-- 客户画像研判结果表
DROP TABLE IF EXISTS `customer_profile`;
CREATE TABLE `customer_profile` (
    `id`                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `customer_name`         VARCHAR(64)     DEFAULT NULL            COMMENT '客户姓名',
    `contact_info`          VARCHAR(128)    DEFAULT NULL            COMMENT '联系方式',
    `source_id`             BIGINT UNSIGNED DEFAULT NULL            COMMENT '关联客户信息来源ID',
    `background_info`       JSON            DEFAULT NULL            COMMENT '客户背景信息结构化数据（学历/年龄/意向国家等）',
    `match_result`          ENUM('matched','partial','not_matched') DEFAULT NULL COMMENT '匹配结果',
    `matched_product`       VARCHAR(128)    DEFAULT NULL            COMMENT '匹配的产品线',
    `match_score`           DECIMAL(5,2)    DEFAULT NULL            COMMENT '匹配度评分（0-100）',
    `match_reason`          TEXT            DEFAULT NULL            COMMENT 'AI研判原因说明',
    `recommended_programs`  JSON            DEFAULT NULL            COMMENT '推荐的专业/项目列表',
    `evaluator_id`          BIGINT UNSIGNED DEFAULT NULL            COMMENT '研判人/操作人ID',
    `create_time`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_source_id` (`source_id`),
    KEY `idx_match_result` (`match_result`),
    KEY `idx_matched_product` (`matched_product`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户画像研判结果表';

-- ============================================================
-- 3. CRM 意向客户管理（需求3 - 企业智能助手）
-- ============================================================

-- 意向客户表（CRM Lead）
DROP TABLE IF EXISTS `crm_lead`;
CREATE TABLE `crm_lead` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `customer_name`     VARCHAR(64)     NOT NULL                COMMENT '客户姓名',
    `contact_info`      VARCHAR(128)    DEFAULT NULL            COMMENT '联系方式（手机/邮箱）',
    `gender`            ENUM('M','F','U') DEFAULT 'U'           COMMENT '性别',
    `age`               INT             DEFAULT NULL            COMMENT '年龄',
    `education_level`   VARCHAR(64)     DEFAULT NULL            COMMENT '学历层次',
    `intended_country`  VARCHAR(128)    DEFAULT NULL            COMMENT '意向国家（多值逗号分隔）',
    `intended_major`    VARCHAR(128)    DEFAULT NULL            COMMENT '意向专业',
    `background_info`   TEXT            DEFAULT NULL            COMMENT '客户背景与档案',
    `customer_profile_id` BIGINT UNSIGNED DEFAULT NULL          COMMENT '关联客户画像ID',
    `source_channel`    VARCHAR(64)     DEFAULT NULL            COMMENT '来源渠道（线上/线下/转介绍等）',
    `status`            ENUM('new','contacting','qualified','signed','lost') NOT NULL DEFAULT 'new' COMMENT '流转状态',
    `owner_employee_id` BIGINT UNSIGNED NOT NULL                COMMENT '负责员工ID',
    `last_contact_time` DATETIME        DEFAULT NULL            COMMENT '最后联系时间',
    `lost_reason`       VARCHAR(255)    DEFAULT NULL            COMMENT '流失原因',
    `remark`            TEXT            DEFAULT NULL            COMMENT '备注',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_status` (`status`),
    KEY `idx_owner` (`owner_employee_id`),
    KEY `idx_customer_profile` (`customer_profile_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='意向客户表';

-- 客户跟进记录表
DROP TABLE IF EXISTS `crm_follow_up`;
CREATE TABLE `crm_follow_up` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `lead_id`           BIGINT UNSIGNED NOT NULL                COMMENT '关联意向客户ID',
    `employee_id`       BIGINT UNSIGNED NOT NULL                COMMENT '跟进人ID',
    `follow_type`       ENUM('phone','wechat','meeting','email','other') DEFAULT NULL COMMENT '跟进方式',
    `content`           TEXT            NOT NULL                COMMENT '跟进记录内容',
    `next_plan`         VARCHAR(255)    DEFAULT NULL            COMMENT '下次跟进计划',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_lead_id` (`lead_id`),
    KEY `idx_employee_id` (`employee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户跟进记录表';

-- ============================================================
-- 4. 客服 Agent 模块（需求2）
-- ============================================================

-- 知识库文档表
DROP TABLE IF EXISTS `knowledge_base`;
CREATE TABLE `knowledge_base` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `category`          ENUM('company_info','business','policy','faq','overseas_life') NOT NULL COMMENT '知识分类',
    `title`             VARCHAR(255)    NOT NULL                COMMENT '文档标题',
    `content`           TEXT            NOT NULL                COMMENT '文档内容',
    `source_file`       VARCHAR(512)    DEFAULT NULL            COMMENT '来源文件路径/URL',
    `chunk_index`       INT             NOT NULL DEFAULT 0      COMMENT '切片序号',
    `embedding_vector`  BLOB            DEFAULT NULL            COMMENT '向量化存储（用于RAG检索）',
    `status`            TINYINT         NOT NULL DEFAULT 1      COMMENT '状态 1=启用 0=禁用',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_category` (`category`),
    FULLTEXT KEY `ft_content` (`title`,`content`) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库文档表';

-- 客服会话表
DROP TABLE IF EXISTS `chat_session`;
CREATE TABLE `chat_session` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `session_id`        VARCHAR(64)     NOT NULL                COMMENT '会话唯一标识',
    `user_id`           BIGINT UNSIGNED DEFAULT NULL            COMMENT '关联用户ID（已注册用户）',
    `visitor_name`      VARCHAR(64)     DEFAULT NULL            COMMENT '访客昵称',
    `visitor_contact`   VARCHAR(128)    DEFAULT NULL            COMMENT '访客联系方式（用于线索收集）',
    `status`            ENUM('active','closed','timeout') NOT NULL DEFAULT 'active' COMMENT '会话状态',
    `last_message_time` DATETIME        DEFAULT NULL            COMMENT '最后一条消息时间',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `close_time`        DATETIME        DEFAULT NULL            COMMENT '会话关闭时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_session_id` (`session_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`),
    KEY `idx_last_message` (`last_message_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服会话表';

-- 客服消息记录表
DROP TABLE IF EXISTS `chat_message`;
CREATE TABLE `chat_message` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `session_id`        VARCHAR(64)     NOT NULL                COMMENT '关联会话ID',
    `role`              ENUM('user','assistant','system') NOT NULL COMMENT '消息角色',
    `content`           TEXT            NOT NULL                COMMENT '消息内容',
    `intent`            VARCHAR(64)     DEFAULT NULL            COMMENT 'AI识别的意图（业务查询/政策咨询/闲聊等）',
    `tokens_used`       INT             DEFAULT NULL            COMMENT '本次消耗Token数',
    `response_time_ms`  INT             DEFAULT NULL            COMMENT '响应耗时（毫秒）',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_session_id` (`session_id`),
    KEY `idx_intent` (`intent`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服消息记录表';

-- 课程与项目表
DROP TABLE IF EXISTS `course_project`;
CREATE TABLE `course_project` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `project_name`      VARCHAR(255)    NOT NULL                COMMENT '项目/课程名称',
    `category`          VARCHAR(64)     DEFAULT NULL            COMMENT '类别（语言培训/背景提升/硕博连读等）',
    `description`       TEXT            DEFAULT NULL            COMMENT '项目详情介绍',
    `target_audience`   VARCHAR(255)    DEFAULT NULL            COMMENT '适合人群/学历要求',
    `price`             DECIMAL(10,2)   DEFAULT NULL            COMMENT '价格',
    `duration`          VARCHAR(64)     DEFAULT NULL            COMMENT '课程周期',
    `tags`              JSON            DEFAULT NULL            COMMENT '标签（用于匹配推荐）',
    `status`            TINYINT         NOT NULL DEFAULT 1      COMMENT '状态 1=上架 0=下架',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_category` (`category`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='课程与项目表';

-- 活动与讲座表
DROP TABLE IF EXISTS `event_lecture`;
CREATE TABLE `event_lecture` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `event_name`        VARCHAR(255)    NOT NULL                COMMENT '活动/讲座名称',
    `event_type`        ENUM('online','offline','hybrid') NOT NULL COMMENT '类型',
    `description`       TEXT            DEFAULT NULL            COMMENT '活动详情',
    `start_time`        DATETIME        NOT NULL                COMMENT '开始时间',
    `end_time`          DATETIME        DEFAULT NULL            COMMENT '结束时间',
    `location`          VARCHAR(255)    DEFAULT NULL            COMMENT '地点或线上链接',
    `max_participants`  INT             DEFAULT NULL            COMMENT '最大报名人数',
    `current_participants` INT          NOT NULL DEFAULT 0      COMMENT '当前报名人数',
    `organizer_id`      BIGINT UNSIGNED DEFAULT NULL            COMMENT '组织者ID',
    `status`            ENUM('upcoming','ongoing','ended','cancelled') NOT NULL DEFAULT 'upcoming' COMMENT '活动状态',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_event_type` (`event_type`),
    KEY `idx_status` (`status`),
    KEY `idx_start_time` (`start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='活动与讲座表';

-- 活动报名表
DROP TABLE IF EXISTS `event_registration`;
CREATE TABLE `event_registration` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `event_id`          BIGINT UNSIGNED NOT NULL                COMMENT '关联活动ID',
    `user_id`           BIGINT UNSIGNED DEFAULT NULL            COMMENT '报名用户ID（注册用户）',
    `customer_name`     VARCHAR(64)     DEFAULT NULL            COMMENT '报名客户姓名（未注册用户）',
    `contact_info`      VARCHAR(128)    DEFAULT NULL            COMMENT '联系方式',
    `status`            ENUM('registered','attended','cancelled','no_show') NOT NULL DEFAULT 'registered' COMMENT '报名状态',
    `remark`            VARCHAR(255)    DEFAULT NULL            COMMENT '备注',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_event_user` (`event_id`,`user_id`),
    KEY `idx_event_id` (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='活动报名表';

-- ============================================================
-- 5. 学生业务模块（需求3+4 - 企业智能助手 + 学生智能助手）
-- ============================================================

-- 学生信息扩展表
DROP TABLE IF EXISTS `student_info`;
CREATE TABLE `student_info` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `user_id`           BIGINT UNSIGNED NOT NULL                COMMENT '关联用户ID',
    `student_no`        VARCHAR(32)     DEFAULT NULL            COMMENT '学号',
    `school`            VARCHAR(128)    DEFAULT NULL            COMMENT '所在院校',
    `major`             VARCHAR(128)    DEFAULT NULL            COMMENT '专业',
    `grade`             VARCHAR(32)     DEFAULT NULL            COMMENT '年级',
    `abroad_country`    VARCHAR(64)     DEFAULT NULL            COMMENT '留学国家',
    `class_teacher_id`  BIGINT UNSIGNED DEFAULT NULL            COMMENT '班主任ID',
    `enroll_date`       DATE            DEFAULT NULL            COMMENT '入学日期',
    `status`            ENUM('active','graduated','suspended','withdrawn') NOT NULL DEFAULT 'active' COMMENT '学生状态',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_id` (`user_id`),
    KEY `idx_class_teacher` (`class_teacher_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生信息扩展表';

-- 学生成绩表
DROP TABLE IF EXISTS `student_score`;
CREATE TABLE `student_score` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`        BIGINT UNSIGNED NOT NULL                COMMENT '学生ID（关联sys_user）',
    `course_name`       VARCHAR(128)    NOT NULL                COMMENT '课程名称',
    `score`             DECIMAL(5,2)    NOT NULL                COMMENT '成绩',
    `semester`          VARCHAR(32)     DEFAULT NULL            COMMENT '学期（如 2025-2026-1）',
    `credit`            DECIMAL(3,1)    DEFAULT NULL            COMMENT '学分',
    `recorded_by`       BIGINT UNSIGNED DEFAULT NULL            COMMENT '录入人ID',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_student_id` (`student_id`),
    KEY `idx_semester` (`semester`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生成绩表';

-- 学生行政服务表（请假/考务申请等）
DROP TABLE IF EXISTS `student_admin_service`;
CREATE TABLE `student_admin_service` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`        BIGINT UNSIGNED NOT NULL                COMMENT '学生ID',
    `service_type`      ENUM('leave','exam_query','other') NOT NULL COMMENT '服务类型',
    `leave_type`        ENUM('sick','personal','emergency') DEFAULT NULL COMMENT '请假类型（仅请假时有效）',
    `start_time`        DATETIME        DEFAULT NULL            COMMENT '开始时间',
    `end_time`          DATETIME        DEFAULT NULL            COMMENT '结束时间',
    `reason`            TEXT            NOT NULL                COMMENT '申请事由',
    `attachment_url`    VARCHAR(512)    DEFAULT NULL            COMMENT '附件URL（如病假证明）',
    `status`            ENUM('pending','approved','rejected','cancelled') NOT NULL DEFAULT 'pending' COMMENT '审批状态',
    `approver_id`       BIGINT UNSIGNED DEFAULT NULL            COMMENT '审批人/班主任ID',
    `approval_comment`  VARCHAR(512)    DEFAULT NULL            COMMENT '审批意见',
    `approval_time`     DATETIME        DEFAULT NULL            COMMENT '审批时间',
    `related_academic_id` BIGINT UNSIGNED DEFAULT NULL          COMMENT '关联教务数据ID',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_student_id` (`student_id`),
    KEY `idx_status` (`status`),
    KEY `idx_service_type` (`service_type`),
    KEY `idx_approver` (`approver_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生行政服务表（请假/考务等申请）';

-- 心理健康画像表
DROP TABLE IF EXISTS `student_psych_profile`;
CREATE TABLE `student_psych_profile` (
    `id`                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`            BIGINT UNSIGNED NOT NULL                COMMENT '学生ID',
    `latest_emotion_tag`    VARCHAR(64)     DEFAULT NULL            COMMENT '最新情绪标签（焦虑/平稳/低落等）',
    `emotion_score`         INT             DEFAULT NULL            COMMENT '情绪分值（0-100，分值越高越积极）',
    `last_interaction_time` DATETIME        DEFAULT NULL            COMMENT '最近一次交互时间',
    `risk_level`            ENUM('low','medium','high') NOT NULL DEFAULT 'low' COMMENT '风险等级',
    `weekly_summary`        JSON            DEFAULT NULL            COMMENT '本周心理状态摘要',
    `create_time`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_student_id` (`student_id`),
    KEY `idx_risk_level` (`risk_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='心理健康画像表';

-- 心理健康记录表（历史情绪波动明细）
DROP TABLE IF EXISTS `student_psych_record`;
CREATE TABLE `student_psych_record` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`        BIGINT UNSIGNED NOT NULL                COMMENT '学生ID',
    `emotion_tag`       VARCHAR(64)     DEFAULT NULL            COMMENT '情绪标签',
    `emotion_score`     INT             DEFAULT NULL            COMMENT '情绪分值（0-100）',
    `interaction_content` TEXT          DEFAULT NULL            COMMENT '交互内容摘要',
    `trigger_keywords`  JSON            DEFAULT NULL            COMMENT 'AI提取的触发关键词',
    `record_date`       DATE            NOT NULL                COMMENT '记录日期',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_student_date` (`student_id`,`record_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='心理健康记录表';

-- 心理预警表
DROP TABLE IF EXISTS `student_psych_alert`;
CREATE TABLE `student_psych_alert` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`        BIGINT UNSIGNED NOT NULL                COMMENT '学生ID',
    `trigger_reason`    TEXT            NOT NULL                COMMENT '触发原因（AI提取的关键词或原句）',
    `risk_level`        ENUM('low','medium','high') NOT NULL    COMMENT '风险等级',
    `status`            ENUM('pending','following','resolved','dismissed') NOT NULL DEFAULT 'pending' COMMENT '处理状态',
    `teacher_id`        BIGINT UNSIGNED DEFAULT NULL            COMMENT '负责跟进的老师ID',
    `follow_record`     TEXT            DEFAULT NULL            COMMENT '跟进记录',
    `resolved_time`     DATETIME        DEFAULT NULL            COMMENT '解除时间',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_student_id` (`student_id`),
    KEY `idx_risk_level` (`risk_level`),
    KEY `idx_status` (`status`),
    KEY `idx_teacher_id` (`teacher_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='心理预警表';

-- 售后反馈工单表
DROP TABLE IF EXISTS `student_feedback_ticket`;
CREATE TABLE `student_feedback_ticket` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`        BIGINT UNSIGNED NOT NULL                COMMENT '学生ID',
    `ticket_type`       ENUM('complaint','suggestion','consult') NOT NULL DEFAULT 'complaint' COMMENT '工单类型',
    `category`          VARCHAR(64)     DEFAULT NULL            COMMENT '投诉分类（签证办理/院校申请/生活服务/其他）',
    `title`             VARCHAR(255)    DEFAULT NULL            COMMENT '工单标题',
    `content`           TEXT            NOT NULL                COMMENT '投诉/反馈内容摘要',
    `detail`            TEXT            DEFAULT NULL            COMMENT '详细反馈内容',
    `status`            ENUM('pending','processing','resolved','closed') NOT NULL DEFAULT 'pending' COMMENT '处理进度',
    `priority`          ENUM('low','medium','high','urgent') NOT NULL DEFAULT 'medium' COMMENT '优先级',
    `assignee_id`       BIGINT UNSIGNED DEFAULT NULL            COMMENT '指派处理人ID',
    `solution`          TEXT            DEFAULT NULL            COMMENT '最终解决方案',
    `satisfaction`      TINYINT         DEFAULT NULL            COMMENT '满意度评分（1-5星）',
    `is_notified`       TINYINT         NOT NULL DEFAULT 0      COMMENT '是否已通知学生（0否 1是）',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_student_id` (`student_id`),
    KEY `idx_status` (`status`),
    KEY `idx_category` (`category`),
    KEY `idx_assignee` (`assignee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='售后反馈工单表';

-- 留学申请进度追踪表
DROP TABLE IF EXISTS `application_progress`;
CREATE TABLE `application_progress` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`        BIGINT UNSIGNED NOT NULL                COMMENT '学生ID',
    `target_school`     VARCHAR(128)    NOT NULL                COMMENT '目标院校',
    `target_major`      VARCHAR(128)    DEFAULT NULL            COMMENT '目标专业',
    `stage`             ENUM('document_prep','submitted','under_review','offer_received','visa_processing','enrolled') NOT NULL DEFAULT 'document_prep' COMMENT '申请阶段',
    `progress_detail`   TEXT            DEFAULT NULL            COMMENT '进度详情描述',
    `deadline`          DATE            DEFAULT NULL            COMMENT '关键截止日期',
    `next_action`       VARCHAR(255)    DEFAULT NULL            COMMENT '下一步操作',
    `handler_id`        BIGINT UNSIGNED DEFAULT NULL            COMMENT '负责顾问ID',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_student_id` (`student_id`),
    KEY `idx_stage` (`stage`),
    KEY `idx_deadline` (`deadline`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='留学申请进度追踪表';

-- ============================================================
-- 6. 员工业务模块（需求3 - 企业智能助手）
-- ============================================================

-- 员工日报表
DROP TABLE IF EXISTS `employee_daily_report`;
CREATE TABLE `employee_daily_report` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `employee_id`       BIGINT UNSIGNED NOT NULL                COMMENT '员工ID',
    `report_date`       DATE            NOT NULL                COMMENT '日报所属日期',
    `raw_content`       TEXT            DEFAULT NULL            COMMENT '原始口述/输入内容',
    `content`           TEXT            NOT NULL                COMMENT 'AI结构化后的日报文本',
    `key_progress`      JSON            DEFAULT NULL            COMMENT 'AI提取的核心进展',
    `risks`             JSON            DEFAULT NULL            COMMENT 'AI识别的潜在风险',
    `next_plan`         TEXT            DEFAULT NULL            COMMENT '明日计划',
    `status`            ENUM('draft','submitted') NOT NULL DEFAULT 'draft' COMMENT '状态',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_employee_date` (`employee_id`,`report_date`),
    KEY `idx_report_date` (`report_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='员工日报表';

-- 新人入职指引知识库
DROP TABLE IF EXISTS `onboarding_guide`;
CREATE TABLE `onboarding_guide` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `title`             VARCHAR(255)    NOT NULL                COMMENT '指引标题',
    `category`          VARCHAR(64)     NOT NULL                COMMENT '分类（入职指南/规章制度/业务流程等）',
    `content`           TEXT            NOT NULL                COMMENT '指引内容',
    `embedding_vector`  BLOB            DEFAULT NULL            COMMENT '向量化存储（用于RAG检索）',
    `sort_order`        INT             NOT NULL DEFAULT 0      COMMENT '排序权重',
    `status`            TINYINT         NOT NULL DEFAULT 1      COMMENT '状态 1=启用 0=禁用',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='新人入职指引知识库';

-- 待办事项表（主动推送用）
DROP TABLE IF EXISTS `todo_item`;
CREATE TABLE `todo_item` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `assignee_id`       BIGINT UNSIGNED NOT NULL                COMMENT '指派人ID',
    `todo_type`         ENUM('leave_approval','complaint_follow','report_remind','custom') NOT NULL COMMENT '待办类型',
    `title`             VARCHAR(255)    NOT NULL                COMMENT '待办标题',
    `description`       TEXT            DEFAULT NULL            COMMENT '待办描述',
    `related_type`      VARCHAR(64)     DEFAULT NULL            COMMENT '关联业务类型',
    `related_id`        BIGINT UNSIGNED DEFAULT NULL            COMMENT '关联业务ID',
    `priority`          ENUM('low','medium','high','urgent') NOT NULL DEFAULT 'medium' COMMENT '优先级',
    `status`            ENUM('pending','in_progress','done','cancelled') NOT NULL DEFAULT 'pending' COMMENT '状态',
    `due_time`          DATETIME        DEFAULT NULL            COMMENT '截止时间',
    `completed_time`    DATETIME        DEFAULT NULL            COMMENT '完成时间',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_assignee` (`assignee_id`),
    KEY `idx_status` (`status`),
    KEY `idx_todo_type` (`todo_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='待办事项表';

-- ============================================================
-- 7. 智能报告模块（需求5）
-- ============================================================

-- 报告生成记录表
DROP TABLE IF EXISTS `report_generation`;
CREATE TABLE `report_generation` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `report_type`       ENUM('customer_ops','daily_summary','weekly_summary','psych_weekly','complaint_weekly') NOT NULL COMMENT '报告类型',
    `report_title`      VARCHAR(255)    NOT NULL                COMMENT '报告标题',
    `report_content`    JSON            DEFAULT NULL            COMMENT '报告内容（结构化数据）',
    `report_html`       MEDIUMTEXT      DEFAULT NULL            COMMENT '报告HTML渲染内容',
    `period_start`      DATE            DEFAULT NULL            COMMENT '统计周期起始',
    `period_end`        DATE            DEFAULT NULL            COMMENT '统计周期结束',
    `generated_by`      BIGINT UNSIGNED DEFAULT NULL            COMMENT '生成人ID',
    `status`            ENUM('generating','completed','failed') NOT NULL DEFAULT 'generating' COMMENT '生成状态',
    `error_message`     TEXT            DEFAULT NULL            COMMENT '失败原因',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_report_type` (`report_type`),
    KEY `idx_period` (`period_start`,`period_end`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告生成记录表';

-- 报告定时任务配置表
DROP TABLE IF EXISTS `report_schedule`;
CREATE TABLE `report_schedule` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `report_type`       ENUM('customer_ops','daily_summary','weekly_summary','psych_weekly','complaint_weekly') NOT NULL COMMENT '报告类型',
    `schedule_cron`     VARCHAR(64)     NOT NULL                COMMENT 'Cron表达式',
    `recipients`        JSON            NOT NULL                COMMENT '接收人列表（用户ID数组）',
    `enabled`           TINYINT         NOT NULL DEFAULT 1      COMMENT '是否启用 1=启用 0=禁用',
    `last_run_time`     DATETIME        DEFAULT NULL            COMMENT '上次执行时间',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_report_type` (`report_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告定时任务配置表';

-- ============================================================
-- 8. 系统辅助表
-- ============================================================

-- AI意图识别配置表
DROP TABLE IF EXISTS `intent_config`;
CREATE TABLE `intent_config` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `intent_code`       VARCHAR(64)     NOT NULL                COMMENT '意图编码',
    `intent_name`       VARCHAR(128)    NOT NULL                COMMENT '意图名称',
    `scene`             ENUM('customer_service','enterprise','student') NOT NULL COMMENT '适用场景',
    `system_prompt`     TEXT            DEFAULT NULL            COMMENT '该意图对应的系统提示词',
    `routing_rule`      JSON            DEFAULT NULL            COMMENT '路由规则配置',
    `status`            TINYINT         NOT NULL DEFAULT 1      COMMENT '状态 1=启用 0=禁用',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_intent_scene` (`intent_code`,`scene`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI意图识别配置表';

-- 海外生活知识库
DROP TABLE IF EXISTS `overseas_life_knowledge`;
CREATE TABLE `overseas_life_knowledge` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `country`           VARCHAR(64)     NOT NULL                COMMENT '国家',
    `category`          ENUM('medical','transport','emergency','daily_life','other') NOT NULL COMMENT '分类',
    `title`             VARCHAR(255)    NOT NULL                COMMENT '知识标题',
    `content`           TEXT            NOT NULL                COMMENT '知识内容',
    `embedding_vector`  BLOB            DEFAULT NULL            COMMENT '向量化存储',
    `status`            TINYINT         NOT NULL DEFAULT 1      COMMENT '状态 1=启用 0=禁用',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_country` (`country`),
    KEY `idx_category` (`category`),
    FULLTEXT KEY `ft_knowledge` (`title`,`content`) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='海外生活知识库';

-- 学业关键节点/DDL表
DROP TABLE IF EXISTS `academic_deadline`;
CREATE TABLE `academic_deadline` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`        BIGINT UNSIGNED DEFAULT NULL            COMMENT '学生ID（NULL=通用DDL）',
    `deadline_type`     ENUM('paper','exam','application','visa','other') NOT NULL COMMENT 'DDL类型',
    `title`             VARCHAR(255)    NOT NULL                COMMENT '节点名称',
    `description`       TEXT            DEFAULT NULL            COMMENT '描述',
    `deadline`          DATETIME        NOT NULL                COMMENT '截止时间',
    `reminder_enabled`  TINYINT         NOT NULL DEFAULT 1      COMMENT '是否开启提醒',
    `reminder_days`     JSON            DEFAULT NULL            COMMENT '提前提醒天数配置 [7,3,1]',
    `status`            ENUM('pending','reminded','done','missed') NOT NULL DEFAULT 'pending' COMMENT '状态',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_student_id` (`student_id`),
    KEY `idx_deadline` (`deadline`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学业关键节点/DDL表';

-- 提醒通知记录表
DROP TABLE IF EXISTS `notification_log`;
CREATE TABLE `notification_log` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `user_id`           BIGINT UNSIGNED NOT NULL                COMMENT '接收人ID',
    `notification_type` VARCHAR(64)     NOT NULL                COMMENT '通知类型',
    `related_type`      VARCHAR(64)     DEFAULT NULL            COMMENT '关联业务类型',
    `related_id`        BIGINT UNSIGNED DEFAULT NULL            COMMENT '关联业务ID',
    `title`             VARCHAR(255)    NOT NULL                COMMENT '通知标题',
    `content`           TEXT            NOT NULL                COMMENT '通知内容',
    `channel`           ENUM('system','email','sms','wechat') NOT NULL DEFAULT 'system' COMMENT '通知渠道',
    `status`            ENUM('pending','sent','failed') NOT NULL DEFAULT 'pending' COMMENT '发送状态',
    `error_message`     TEXT            DEFAULT NULL            COMMENT '失败原因',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='提醒通知记录表';

-- ============================================================
-- 9. 初始化基础数据
-- ============================================================

-- 初始化角色
INSERT INTO `sys_role` (`role_code`, `role_name`, `description`) VALUES
('admin', '系统管理员', '系统最高权限角色'),
('employee', '员工', '企业内部员工'),
('manager', '部门经理', '部门管理人员'),
('team_leader', '班主任', '学生班主任角色'),
('student', '学生', '在校学生角色');

-- 初始化意图配置（客服Agent 7大场景）
INSERT INTO `intent_config` (`intent_code`, `intent_name`, `scene`, `system_prompt`) VALUES
('company_inquiry', '公司信息咨询', 'customer_service', '你是专业的留学机构客服助手，请基于知识库信息回答关于公司品牌背景、发展历程、校区分布等问题。'),
('business_query', '公司业务查询', 'customer_service', '你是专业的留学机构客服助手，请精准回应客户关于留学申请、背景提升、语言培训等核心业务板块的咨询。'),
('policy_query', '留学政策查询', 'customer_service', '你是专业的留学政策顾问，请基于知识库中的各国签证要求、院校申请门槛、移民就业政策等进行解读。'),
('course_recommend', '课程与项目推荐', 'customer_service', '你是专业的课程推荐顾问，请根据客户的学历背景和留学意向，智能推荐匹配的留学方案、语言课程或背景提升项目。'),
('event_register', '活动报名', 'customer_service', '你是活动咨询专员，请帮助客户查询近期留学分享会、招生官见面会，并协助完成活动预约与报名。'),
('faq', '常见问题', 'customer_service', '你是高效的FAQ客服，请快速回复关于申请流程、服务费用、退费政策等常见问题。'),
('casual_chat', '日常闲聊', 'customer_service', '你是一个亲切友好的AI助手，请用年轻人喜欢的语气和用户聊天，适度使用网络热梗，保持轻松愉快的氛围。');

-- 初始化意图配置（企业智能助手）
INSERT INTO `intent_config` (`intent_code`, `intent_name`, `scene`, `system_prompt`) VALUES
('lead_entry', '意向客户录入', 'enterprise', '请从用户的描述中提取客户的关键信息，包括姓名、联系方式、背景等，以JSON格式输出。'),
('lead_query', '意向客户查询', 'enterprise', '请理解用户想要查询的客户信息，生成对应的SQL查询语句。'),
('lead_update', '客户状态更新', 'enterprise', '请理解用户要更新的客户状态信息，生成对应的更新SQL。'),
('daily_report', '口述日报', 'enterprise', '请根据用户口述的工作内容，生成结构化的日报，包括今日工作、成果、明日计划等。'),
('org_query', '组织架构查询', 'enterprise', '请帮助用户查询组织架构中的部门信息、同事联系方式等。'),
('onboarding', '新人入职指引', 'enterprise', '你是入职导师，请为新老员工提供入职指南、规章制度解答及业务流程指引。');

-- 初始化意图配置（学生智能助手）
INSERT INTO `intent_config` (`intent_code`, `intent_name`, `scene`, `system_prompt`) VALUES
('leave_request', '请假申请', 'student', '请从用户描述中提取请假信息，包括请假类型、开始时间、结束时间、事由等。'),
('emotion_chat', '情绪关怀', 'student', '你是一个温暖的心理辅导助手，请用温柔、理解的语气倾听学生的情绪倾诉，给予安慰和鼓励。如发现高危情绪，请及时标记预警。'),
('feedback_submit', '售后反馈', 'student', '请理解学生的投诉或建议内容，提取关键信息，生成工单摘要和分类。'),
('academic_query', '学业考务查询', 'student', '请帮助学生查询论文DDL、考试时间等关键学业节点信息。'),
('progress_query', '申请进度查询', 'student', '请查询并告知学生当前的文书审核、院校申请、签证办理等留学业务进度。'),
('overseas_life', '海外生活支持', 'student', '你是学生的海外生活助手，请提供当地医疗、交通、紧急求助等生活常识问答。'),
('upselling', '增值转化', 'student', '你是升学顾问，请根据学生的当前阶段和意向，适时推荐机构的学历提升项目。');

