-- ============================================================
-- 教育服务系统 - 数据库初始化脚本
-- 模块：统一用户表 + 客服Agent模块
-- 数据库: education_service
-- 字符集: utf8mb4
-- 引擎: InnoDB
-- 策略: 无物理外键，逻辑关联 + 索引 + 应用层维护
-- ============================================================

CREATE DATABASE IF NOT EXISTS `education_service`
    DEFAULT CHARSET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `education_service`;

SET NAMES utf8mb4;

-- ============================================================
-- 清理旧表
-- 说明：无物理外键，但仍按业务依赖顺序清理
-- ============================================================

DROP TABLE IF EXISTS `chat_message`;
DROP TABLE IF EXISTS `chat_session`;
DROP TABLE IF EXISTS `event_registration`;
DROP TABLE IF EXISTS `event_lecture`;
DROP TABLE IF EXISTS `course_project`;
DROP TABLE IF EXISTS `sys_user`;


-- ============================================================
-- 1. sys_user - 统一用户表
-- ============================================================

CREATE TABLE `sys_user` (
    `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `username`      VARCHAR(64)     NOT NULL COMMENT '用户名',
    `password_hash` VARCHAR(255)    DEFAULT NULL COMMENT '密码哈希',
    `real_name`     VARCHAR(64)     DEFAULT NULL COMMENT '真实姓名',
    `user_type`     ENUM('student','employee','admin','visitor') NOT NULL DEFAULT 'visitor' COMMENT '用户类型',
    `status`        TINYINT         NOT NULL DEFAULT 1 COMMENT '1=正常 0=禁用',
    `create_time`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_user_type` (`user_type`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='统一用户表';


-- ============================================================
-- 2. course_project - 课程与项目表
-- ============================================================

CREATE TABLE `course_project` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `project_name`      VARCHAR(255)    NOT NULL COMMENT '项目/课程名称',
    `category`          VARCHAR(64)     DEFAULT NULL COMMENT '类别（语言培训/背景提升/留学申请）',
    `description`       TEXT            DEFAULT NULL COMMENT '项目详情介绍',
    `target_audience`   VARCHAR(255)    DEFAULT NULL COMMENT '适合人群/学历要求',
    `price`             DECIMAL(10,2)   DEFAULT NULL COMMENT '价格',
    `duration`          VARCHAR(64)     DEFAULT NULL COMMENT '课程周期',
    `tags`              JSON            DEFAULT NULL COMMENT '标签（用于匹配推荐）',
    `status`            TINYINT         NOT NULL DEFAULT 1 COMMENT '1=上架 0=下架',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_category` (`category`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='课程与项目表';


-- ============================================================
-- 3. event_lecture - 活动与讲座表
-- ============================================================

CREATE TABLE `event_lecture` (
    `id`                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `event_name`            VARCHAR(255)    NOT NULL COMMENT '活动/讲座名称',
    `event_type`            ENUM('online','offline','hybrid') NOT NULL COMMENT '类型',
    `description`           TEXT            DEFAULT NULL COMMENT '活动详情',
    `start_time`            DATETIME        NOT NULL COMMENT '开始时间',
    `end_time`              DATETIME        DEFAULT NULL COMMENT '结束时间',
    `location`              VARCHAR(255)    DEFAULT NULL COMMENT '地点或线上链接',
    `max_participants`      INT             DEFAULT NULL COMMENT '最大报名人数',
    `current_participants`  INT             NOT NULL DEFAULT 0 COMMENT '当前报名人数（应用层维护）',
    `organizer_id`          BIGINT UNSIGNED DEFAULT NULL COMMENT '组织者 → sys_user.id（逻辑关联）',
    `status`                ENUM('upcoming','ongoing','ended','cancelled') NOT NULL DEFAULT 'upcoming' COMMENT '活动状态',
    `create_time`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time`           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_event_type` (`event_type`),
    KEY `idx_status` (`status`),
    KEY `idx_start_time` (`start_time`),
    KEY `idx_organizer_id` (`organizer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='活动与讲座表';


-- ============================================================
-- 4. event_registration - 活动报名表
-- ============================================================

CREATE TABLE `event_registration` (
    `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `event_id`      BIGINT UNSIGNED NOT NULL COMMENT '活动ID → event_lecture.id（逻辑关联）',
    `user_id`       BIGINT UNSIGNED DEFAULT NULL COMMENT '报名用户 → sys_user.id（逻辑关联）',
    `customer_name` VARCHAR(64)     DEFAULT NULL COMMENT '报名客户姓名',
    `contact_info`  VARCHAR(128)    DEFAULT NULL COMMENT '联系方式',
    `status`        ENUM('registered','attended','cancelled','no_show') NOT NULL DEFAULT 'registered' COMMENT '报名状态',
    `remark`        VARCHAR(255)    DEFAULT NULL COMMENT '备注',
    `create_time`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_event_user` (`event_id`, `user_id`),
    UNIQUE KEY `uk_event_contact` (`event_id`, `contact_info`),
    KEY `idx_event_id` (`event_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_contact_info` (`contact_info`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='活动报名表';


-- ============================================================
-- 5. chat_session - 客服会话表
-- ============================================================

CREATE TABLE `chat_session` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `session_id`        VARCHAR(64)     NOT NULL COMMENT '会话唯一标识',
    `user_id`           BIGINT UNSIGNED DEFAULT NULL COMMENT '关联用户 → sys_user.id（逻辑关联）',
    `visitor_name`      VARCHAR(64)     DEFAULT NULL COMMENT '访客昵称',
    `visitor_contact`   VARCHAR(128)    DEFAULT NULL COMMENT '访客联系方式',
    `status`            ENUM('active','closed','timeout') NOT NULL DEFAULT 'active' COMMENT '会话状态',
    `last_message_time` DATETIME        DEFAULT NULL COMMENT '最后消息时间',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `close_time`        DATETIME        DEFAULT NULL COMMENT '会话关闭时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_session_id` (`session_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`),
    KEY `idx_last_message_time` (`last_message_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服会话表';


-- ============================================================
-- 6. chat_message - 客服消息记录表
-- ============================================================

CREATE TABLE `chat_message` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `session_id`        VARCHAR(64)     NOT NULL COMMENT '会话ID → chat_session.session_id（逻辑关联）',
    `role`              ENUM('user','assistant','system') NOT NULL COMMENT '消息角色',
    `content`           TEXT            NOT NULL COMMENT '消息内容',
    `intent`            VARCHAR(64)     DEFAULT NULL COMMENT 'AI识别意图',
    `tokens_used`       INT             DEFAULT NULL COMMENT '本次消耗Token数',
    `response_time_ms`  INT             DEFAULT NULL COMMENT '响应耗时，毫秒',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_session_id` (`session_id`),
    KEY `idx_intent` (`intent`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服消息记录表';


-- ============================================================
-- 种子数据：sys_user
-- ============================================================

INSERT INTO `sys_user`
(`id`, `username`, `password_hash`, `real_name`, `user_type`, `status`)
VALUES
(1, 'admin', NULL, '系统管理员', 'admin', 1),
(2, 'super_admin', NULL, '超级管理员', 'admin', 1),

(10, 'consultant01', NULL, '李顾问', 'employee', 1),
(11, 'consultant02', NULL, '王顾问', 'employee', 1),
(12, 'teacher01', NULL, '张老师', 'employee', 1),
(13, 'counselor01', NULL, '陈班主任', 'employee', 1),
(14, 'service01', NULL, '赵客服', 'employee', 1),
(15, 'marketing01', NULL, '孙市场', 'employee', 1),

(100, 'student01', NULL, '测试学生A', 'student', 1),
(101, 'student02', NULL, '测试学生B', 'student', 1),
(102, 'student03', NULL, '测试学生C', 'student', 1),
(103, 'student04', NULL, '测试学生D', 'student', 1),
(104, 'student05', NULL, '测试学生E', 'student', 1),

(200, 'visitor01', NULL, '访客张明', 'visitor', 1),
(201, 'visitor02', NULL, '访客李娜', 'visitor', 1),
(202, 'visitor03', NULL, '访客王强', 'visitor', 1),
(203, 'visitor04', NULL, '访客赵敏', 'visitor', 1),

(900, 'disabled_user', NULL, '禁用测试用户', 'student', 0);


-- ============================================================
-- 种子数据：course_project
-- ============================================================

INSERT INTO `course_project`
(`project_name`, `category`, `description`, `target_audience`, `price`, `duration`, `tags`, `status`)
VALUES
('雅思7分冲刺班', '语言培训', '针对雅思目标7分的学员，涵盖听说读写四项技能强化训练，包含10次全真模考与名师讲评。', '雅思基础5.5分以上', 8800.00, '8周', '["名师授课", "小班教学", "模考+讲评"]', 1),
('托福100分突破班', '语言培训', '系统性托福备考课程，重点突破阅读与听力高分瓶颈，配备独家真题题库。', '托福基础70分以上', 9800.00, '10周', '["真题题库", "一对一辅导", "考前冲刺"]', 1),
('日语N2速成班', '语言培训', '从零基础到N2，采用沉浸式教学法，6个月快速达标。', '零基础或N5水平', 6800.00, '24周', '["沉浸式教学", "日本外教", "考级保过"]', 1),
('GRE/GMAT联报班', '语言培训', 'GRE与GMAT联合备考课程，适合尚未确定目标国家的学生，双线准备。', '大三及以上学生', 12800.00, '16周', '["双线备考", "自适应模考", "高分保障"]', 1),
('海外学术写作提升课', '语言培训', '帮助学生掌握英文论文写作、引用规范、学术表达与查重规范。', '准备海外学习的学生', 5200.00, '6周', '["学术写作", "论文规范", "英文表达"]', 1),

('科研背景提升项目', '背景提升', '与985高校教授合作，参与真实科研课题，产出论文或专利，助力留学申请。', '本科在读学生', 29800.00, '12周', '["名校教授", "科研论文", "推荐信"]', 1),
('名企实习内推计划', '背景提升', '对接世界500强企业，提供远程/实地实习机会，涵盖金融、咨询、互联网等行业。', '大三及以上学生', 15800.00, '8-12周', '["500强企业", "实习证明", "职业规划"]', 1),
('艺术作品集辅导', '背景提升', '针对申请海外艺术院校的学生，提供一对一作品集指导与创作支持。', '艺术/设计专业学生', 25800.00, '16周', '["一对一辅导", "作品集制作", "名校导师"]', 1),
('留学申请面试辅导课', '背景提升', '模拟海外院校面试场景，针对常见问题进行一对一训练和反馈。', '已进入面试阶段的申请者', 6800.00, '4周', '["模拟面试", "一对一反馈", "招生官视角"]', 1),

('英国硕士直通车', '留学申请', '一站式英国TOP30硕士申请服务，包含选校定位、文书润色、面试辅导、签证指导。', '本科毕业生或大四在读', 39800.00, '6-12个月', '["TOP30保录", "文书定制", "面试辅导"]', 1),
('美国名校申请套餐', '留学申请', '针对美国TOP50院校的全套申请服务，包含背景提升规划、选校策略、文书创作、面试培训。', 'GPA 3.0以上', 59800.00, '12-18个月', '["TOP50名校", "全流程服务", "奖学金申请"]', 1),
('澳大利亚移民+留学双规划', '留学申请', '结合澳洲移民政策，提供留学+移民双路径规划，涵盖职业评估、院校申请、签证办理。', '有意向移民澳洲的学生', 35800.00, '8-14个月', '["移民规划", "职业评估", "双路径"]', 1),
('加拿大本科申请规划', '留学申请', '面向高中生的加拿大本科申请服务，覆盖选校、文书、材料递交、签证规划。', '高中在读或毕业生', 32800.00, '8-12个月', '["加拿大本科", "选校规划", "签证指导"]', 1),
('香港硕士申请精英计划', '留学申请', '针对香港八大高校硕士申请，提供背景定位、文书打磨、面试辅导。', '本科在读或毕业生', 29800.00, '4-8个月', '["香港八大", "面试辅导", "高效申请"]', 1),
('新加坡名校申请计划', '留学申请', '面向新加坡国立大学、南洋理工大学等名校申请，提供一站式申请服务。', 'GPA较高、有科研或实习背景学生', 35800.00, '6-10个月', '["NUS", "NTU", "名校申请"]', 1);


-- ============================================================
-- 种子数据：event_lecture
-- ============================================================

INSERT INTO `event_lecture`
(`event_name`, `event_type`, `description`, `start_time`, `end_time`, `location`, `max_participants`, `current_participants`, `organizer_id`, `status`)
VALUES
('英国留学申请攻略讲座', 'online', '详解2026年英国硕士申请流程、选校策略与材料准备要点，由资深留学顾问主讲。', '2026-07-15 14:00:00', '2026-07-15 16:00:00', '线上 - 腾讯会议（会议号：123-456-789）', 100, 0, 10, 'upcoming'),
('美国TOP30名校申请经验分享', 'offline', '邀请已获得哈佛、斯坦福等名校offer的学长学姐现场分享申请经验与心得。', '2026-07-20 10:00:00', '2026-07-20 12:00:00', '北京市朝阳区建国路88号 SOHO现代城A座15层', 50, 0, 11, 'upcoming'),
('雅思口语高分技巧公开课', 'online', '雅思考官亲授口语高分技巧，涵盖Part1-3答题策略与常见误区解析。', '2026-07-18 19:00:00', '2026-07-18 20:30:00', '线上 - Zoom（会议号：987-654-321）', 200, 0, 12, 'upcoming'),
('留学文书写作工作坊', 'hybrid', '由前招生官亲授留学文书写作技巧，现场点评修改真实文书案例。', '2026-07-25 14:00:00', '2026-07-25 17:00:00', '上海市静安区南京西路1515号 + 线上同步直播', 30, 0, 13, 'upcoming'),
('留学生海外生活指南分享会', 'online', '邀请海外在读学长学姐分享海外生活经验，涵盖住宿、医疗、社交等实用话题。', '2026-08-01 15:00:00', '2026-08-01 16:30:00', '线上 - 腾讯会议', 150, 0, 13, 'upcoming'),
('澳洲留学与移民政策解读', 'online', '讲解澳大利亚热门专业、技术移民路径、职业评估和签证政策。', '2026-08-05 19:00:00', '2026-08-05 21:00:00', '线上 - Zoom', 120, 0, 10, 'upcoming'),
('加拿大本科申请规划说明会', 'offline', '面向高中生家庭，解析加拿大本科申请时间线、选校策略与材料准备。', '2026-08-10 14:00:00', '2026-08-10 16:00:00', '广州市天河区体育西路101号维多利广场20层', 60, 0, 15, 'upcoming'),
('香港硕士申请冲刺专场', 'online', '针对香港硕士申请末班车，讲解申请材料、面试准备和递交策略。', '2026-08-12 20:00:00', '2026-08-12 21:30:00', '线上 - 腾讯会议', 80, 0, 11, 'upcoming');


-- ============================================================
-- 种子数据：event_registration
-- ============================================================

INSERT INTO `event_registration`
(`event_id`, `user_id`, `customer_name`, `contact_info`, `status`, `remark`)
VALUES
(1, 200, '张明', '13800000001', 'registered', '通过客服Agent报名，关注英国硕士申请'),
(1, 201, '李娜', '13800000002', 'registered', '希望了解商科申请'),
(1, 202, '王强', '13800000003', 'registered', '目标院校为曼彻斯特大学'),

(2, 203, '赵敏', '13800000004', 'registered', '线下参加，关注美国名校申请'),
(2, 100, '测试学生A', '13900000001', 'registered', '注册学生报名测试'),

(3, 101, '测试学生B', '13900000002', 'registered', '雅思口语目标7分'),
(3, NULL, '刘洋', '13800000006', 'registered', '游客报名，准备两个月后考试'),
(3, NULL, '孙婷', '13800000007', 'registered', '想试听口语课程'),

(4, NULL, '吴迪', '13800000009', 'registered', '需要文书修改建议'),
(5, NULL, '郑雪', '13800000010', 'registered', '关注海外住宿和生活适应');


-- ============================================================
-- 回写活动当前报名人数
-- ============================================================

UPDATE `event_lecture` e
SET e.`current_participants` = (
    SELECT COUNT(*)
    FROM `event_registration` r
    WHERE r.`event_id` = e.`id`
      AND r.`status` IN ('registered', 'attended')
);


-- ============================================================
-- 种子数据：chat_session
-- ============================================================

INSERT INTO `chat_session`
(`session_id`, `user_id`, `visitor_name`, `visitor_contact`, `status`, `last_message_time`, `create_time`, `close_time`)
VALUES
('sess_20260709_0001', 200, '张明', '13800000001', 'active', '2026-07-09 10:06:30', '2026-07-09 10:00:00', NULL),
('sess_20260709_0002', 201, '李娜', '13800000002', 'closed', '2026-07-09 11:20:10', '2026-07-09 11:00:00', '2026-07-09 11:25:00'),
('sess_20260709_0003', 202, '王强', '13800000003', 'active', '2026-07-09 14:16:45', '2026-07-09 14:00:00', NULL),
('sess_20260709_0004', 203, '赵敏', '13800000004', 'closed', '2026-07-09 15:42:20', '2026-07-09 15:20:00', '2026-07-09 15:50:00'),
('sess_20260709_0005', NULL, '游客A', NULL, 'timeout', '2026-07-09 16:05:00', '2026-07-09 15:55:00', '2026-07-09 16:30:00');


-- ============================================================
-- 种子数据：chat_message
-- ============================================================

INSERT INTO `chat_message`
(`session_id`, `role`, `content`, `intent`, `tokens_used`, `response_time_ms`, `create_time`)
VALUES
('sess_20260709_0001', 'user', '你好，我想了解英国留学申请，有什么课程推荐？', 'course_recommendation', 32, NULL, '2026-07-09 10:00:10'),
('sess_20260709_0001', 'assistant', '您好，我们目前有“英国硕士直通车”等留学申请服务，包含选校定位、文书润色、面试辅导和签证指导。适合本科毕业生或大四在读学生。', 'course_recommendation', 158, 1250, '2026-07-09 10:00:18'),
('sess_20260709_0001', 'user', '最近有英国申请相关讲座吗？', 'event_query', 20, NULL, '2026-07-09 10:03:00'),
('sess_20260709_0001', 'assistant', '有的。最近有“英国留学申请攻略讲座”，时间是2026-07-15 14:00-16:00，线上腾讯会议举行。', 'event_query', 120, 980, '2026-07-09 10:03:08'),
('sess_20260709_0001', 'user', '帮我报名，我叫张明，手机号13800000001。', 'event_register', 28, NULL, '2026-07-09 10:06:20'),
('sess_20260709_0001', 'assistant', '已为您报名“英国留学申请攻略讲座”，请留意后续会议通知。', 'event_register', 86, 1100, '2026-07-09 10:06:30'),

('sess_20260709_0002', 'user', '雅思口语一直上不去，有没有短期课程？', 'course_recommendation', 24, NULL, '2026-07-09 11:02:00'),
('sess_20260709_0002', 'assistant', '可以考虑“雅思7分冲刺班”，课程周期8周，适合雅思基础5.5分以上的学生，包含听说读写强化训练和全真模考。', 'course_recommendation', 146, 1320, '2026-07-09 11:02:08'),
('sess_20260709_0002', 'user', '有没有免费的公开课？', 'event_query', 16, NULL, '2026-07-09 11:18:00'),
('sess_20260709_0002', 'assistant', '有“雅思口语高分技巧公开课”，时间是2026-07-18 19:00-20:30，线上Zoom举行。', 'event_query', 112, 900, '2026-07-09 11:18:09'),

('sess_20260709_0003', 'user', '我想申请美国计算机硕士，但是科研经历比较少，怎么办？', 'background_improvement', 30, NULL, '2026-07-09 14:01:00'),
('sess_20260709_0003', 'assistant', '可以考虑“科研背景提升项目”或“名企实习内推计划”。科研项目适合补充论文、推荐信等申请材料，实习项目适合增强职业背景。', 'background_improvement', 180, 1500, '2026-07-09 14:01:12'),
('sess_20260709_0003', 'user', '科研项目大概多久？', 'course_query', 14, NULL, '2026-07-09 14:16:35'),
('sess_20260709_0003', 'assistant', '科研背景提升项目周期一般为12周，适合本科在读学生。', 'course_query', 80, 850, '2026-07-09 14:16:45'),

('sess_20260709_0004', 'user', '我想参加美国名校申请分享会。', 'event_register', 18, NULL, '2026-07-09 15:21:00'),
('sess_20260709_0004', 'assistant', '可以的。“美国TOP30名校申请经验分享”将在2026-07-20 10:00-12:00线下举行，请提供您的姓名和手机号用于报名。', 'event_register', 140, 980, '2026-07-09 15:21:08'),
('sess_20260709_0004', 'user', '赵敏，13800000004。', 'event_register', 12, NULL, '2026-07-09 15:42:10'),
('sess_20260709_0004', 'assistant', '报名成功，已为您登记“美国TOP30名校申请经验分享”。', 'event_register', 88, 1050, '2026-07-09 15:42:20'),

('sess_20260709_0005', 'user', '你们能不能保证我一定进牛津？', 'fallback', 16, NULL, '2026-07-09 16:04:50'),
('sess_20260709_0005', 'assistant', '我们可以提供专业申请规划和材料辅导，但不能承诺任何院校的绝对录取结果。建议您留下联系方式，由顾问根据背景进行评估。', 'fallback', 120, 1000, '2026-07-09 16:05:00');


-- ============================================================
-- 初始化结果验证
-- ============================================================

SELECT 'sys_user' AS table_name, COUNT(*) AS total FROM `sys_user`
UNION ALL
SELECT 'course_project', COUNT(*) FROM `course_project`
UNION ALL
SELECT 'event_lecture', COUNT(*) FROM `event_lecture`
UNION ALL
SELECT 'event_registration', COUNT(*) FROM `event_registration`
UNION ALL
SELECT 'chat_session', COUNT(*) FROM `chat_session`
UNION ALL
SELECT 'chat_message', COUNT(*) FROM `chat_message`;

SELECT
    e.`id`,
    e.`event_name`,
    e.`max_participants`,
    e.`current_participants`,
    e.`organizer_id`,
    u.`real_name` AS organizer_name
FROM `event_lecture` e
LEFT JOIN `sys_user` u ON e.`organizer_id` = u.`id`
ORDER BY e.`id`;