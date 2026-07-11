# B「国际教育编辑型门户」示意图索引

所有图片为 `1440×960` 的桌面端设计说明稿。视觉基准是象牙纸白、学院酒红、深墨与古铜，不使用真实品牌、个人数据或经营结果。

| 文件 | 页面 / 路由 | 角色 | 主操作 | 状态与数据依赖 |
| --- | --- | --- | --- | --- |
| 01-login.png | 登录 `/login` | 全部用户 | 身份验证 | 校验、Loading、401、Token |
| 02-dashboard.png | 首页 `/dashboard` | 顾问/管理者 | 进入服务档案 | REAL/MOCK/PENDING、待办、报告 |
| 03-customer-assessment.png | 客户研判 | 顾问 | 上传资料、确认匹配 | 解析、追问、风险、匹配依据 |
| 04-customer-service.png | 客服助手 | 客服 | 发送问题、查看来源 | RAG 引用、免责声明、重试 |
| 05-student-assistant.png | 学生助手 | 学生 | 查询进度、发起求助 | 隐私、风险、人工介入 |
| 06-enterprise-assistant.png | 企业助手 | 运营 | 更新跟进、提交审批 | 权限、只读、二次确认 |
| 07-report-list.png | 报告列表 | 管理者 | 筛选、打开报告 | 分页、空状态、质量 |
| 08-report-generate.png | 报告生成 | 管理者 | 提交委托单 | 校验、202、轮询、取消 |
| 09-report-detail.png | 报告详情 | 管理者 | 阅读与创建行动 | schema、来源、失败重试 |
| 10-report-schedules.png | 报告计划 | 管理者 | 新建/启停计划 | 校验、确认、执行状态 |
| 11-report-actions.png | 报告行动 | 负责人 | 更新行动状态 | 影响确认、责任、时间线 |
| 12-report-data-maintenance.png | 数据维护 | 管理者 | 修正数据来源 | 权限、质量预警、确认 |
