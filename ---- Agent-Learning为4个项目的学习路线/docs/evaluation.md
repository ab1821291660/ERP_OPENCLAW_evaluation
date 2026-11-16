# 贯穿各项目的评估练习

先记录确定性结果，再逐步加入真实模型评分。当前入门演示均为合成数据，不能用它们推断真实业务准确率。

| 项目 | 最先记录的失败 | 进一步记录 |
|---|---|---|
| 携程 | 模型自行批准、重复订单、过期提案、库存变化 | 工具选择、参数完整度、任务完成与成本 |
| RAG | 找错文档、漏检、无依据引用、无答案仍生成 | 召回率、忠实度、延迟与费用 |
| Text2SQL | 写库、越权、超时、口径错误 | 自然语言转 SQL 的语义正确率与错误分类 |
| ERP | 审批拒绝后执行、任务丢失、重试重复操作 | 全流程成功率、人工接管、恢复时间 |

现有 [ERP_OPENCLAW](https://github.com/ooo1208/ERP_OPENCLAW) 已提供 `asu_eval`、合成黄金集、正反门禁、Worker、Outbox 和人工反馈模块。请阅读其第 10—12 章以及验收文档。

总入口可在安装 ERP 的 `.venv` 后执行 `python learn.py verify --include-erp`。基线应返回 0；故意回退应返回 1，表示成功发现退化。总入口只核验这两个退出码，不替代 ERP 全量测试。

接入真实模型后再接 [Langfuse 评估](https://langfuse.com/docs/evaluation/overview) 和 [RAGAS](https://docs.ragas.io/en/stable/getstarted/rag_eval/)。保存题集出处、提示词版本、模型、检索配置、预期答案、实际结果和失败原因；不要把示例数据和他人测量当成自己的实验结果。
