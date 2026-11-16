# Agent-Learning

**四个关联项目统一放在 [repos/ 项目文件夹](repos/) 下，从工具调用、知识检索和数据库分析，逐步学到 ERP_OPENCLAW 综合业务 Agent。**

```text
Agent-Learning/
├── repos/
│   ├── agent_ctrip_assistant/  # 携程助手：工具、路由与审批
│   ├── RAG/                    # 企业知识库：检索与引用
│   ├── Text2SQL/               # 采购数据分析：自然语言查数
│   └── ERP_OPENCLAW/           # 综合采购平台：Agent 与业务流程
├── docs/                       # 学习路线、项目关系与使用说明
└── learn.py                    # 统一下载、演示与验证入口
```

在 GitHub 打开 **[repos/](repos/)**，即可一起看到四个项目。点击项目目录会进入原仓库的固定版本；各项目的独立仓库、提交历史和章节标签继续保留。目录关联用于统一浏览与下载，业务接口的后续整合仍按学习路线推进。

[![Learning projects](https://github.com/ooo1208/Agent-Learning/actions/workflows/quality.yml/badge.svg)](https://github.com/ooo1208/Agent-Learning/actions/workflows/quality.yml)

这是学习总入口，通过 Git 子模块将下面四个仓库放入同一目录。三个入门工程可用 Python 3.11+ 离线运行；ERP 另有 Java、前端和服务依赖。

| 顺序 | 仓库 | 核心练习 | 章节 |
|---|---|---|---|
| 1 | [agent_ctrip_assistant](https://github.com/ooo1208/agent_ctrip_assistant) | 工具调用、预订提案、人工审批、状态恢复 | 6 章 |
| 2 | [RAG](https://github.com/ooo1208/RAG) | 文档入库、词法检索、引用、可选向量和混合检索 | 6 章 |
| 3 | [Text2SQL](https://github.com/ooo1208/Text2SQL) | 采购指标、真实 SQLite 查询、只读约束与执行预算 | 6 章 |
| 4 | [ERP_OPENCLAW](https://github.com/ooo1208/ERP_OPENCLAW) | Java ERP、MCP、DeepAgents、Skills、人工介入与异步评估 | 14 章 |
| 贯穿 | [评估学习说明](docs/evaluation.md) | 失败例、评分、回归门禁、运行追踪 | 使用 ERP 已有评估模块 |

## 项目之间的关系

```mermaid
flowchart LR
    C[携程助手：工具与审批] --> E[ERP_OPENCLAW：综合采购业务]
    S[Text2SQL：数据库分析] -. 后续整合为数据工具 .-> E
    R[RAG：知识与引用] -. 后续整合为知识工具 .-> E
    Q[评估：失败与回归证据] --> C
    Q --> S
    Q --> R
    Q --> E
```

求职作品可以最终收敛为 **ERP_OPENCLAW 综合采购平台 + 企业知识库 RAG**。携程项目用于建立基础；Text2SQL 可逐步接入采购分析。图中的整合箭头是后续练习，当前独立教学仓库还没有自动接入 ERP；RAG 中 OCR/GME/Milvus 等多模态内容仍是进阶计划。

## 快速开始

先安装 Python 3.11+ 和 Git。在终端执行：

```sh
git clone --recurse-submodules https://github.com/ooo1208/Agent-Learning.git
cd Agent-Learning
python learn.py verify
python learn.py demo all
```

递归克隆会一次下载四个项目的固定版本。GitHub 普通 ZIP 下载不包含子模块源码，请优先使用上面的命令。下载代码不会自动安装或启动 ERP 服务。

如果此前使用普通 `git clone`，仍可执行 `python learn.py clone` 下载或初始化三个入门工程；执行 `python learn.py clone --with-erp` 可包含全部四个项目。脚本会保留已有工作目录和修改，不会强行覆盖；已有版本与记录不一致时，请按提示处理。更新已有总仓库和子项目的步骤见 [项目文件夹使用说明](docs/repository-folders.md)。

离线演示和测试不调用模型，不需要密钥。演示使用合成数据；测试通过不表示真实模型问答效果已经验收。

想学习 ERP 时，按照 `repos/ERP_OPENCLAW/README.md` 安装其独立依赖。`python learn.py verify --include-erp` 仅额外运行 ERP 的合成评估门禁，并不替代完整 ERP 集成测试。

每个仓库都有中文 README、来源说明、章节文档和 `chapter-NN` 标签。切到标签前先保存自己的改动；可以另建目录学习某章：

```sh
git -C repos/RAG worktree add ../../RAG-chapter-03 chapter-03
```

章节是本次按知识依赖重新编排并提交的教学顺序，使用真实提交时间，不是官方课程原目录。各章覆盖范围以相应 README 为准。

## 学习与资料

- [项目文件夹使用说明：下载、更新与保留修改](docs/repository-folders.md)
- [学习路线与完成标准](docs/learning-path.md)
- [15 条公开教学资料及原厂参考](资料索引.md)
- [实验记录模板](实验记录模板.md)
- [ERP 模块与基础项目对应](docs/project-map.md)
- [LangGraph 官方历史 notebook](reference/LangGraph-Customer-Support/customer-support.ipynb)：附原许可证、固定提交和 SHA256；未执行其历史依赖。
- [来源与许可](SOURCES.md)
- [从 GitHub 下载后的验收记录](docs/verification.md)：40 项测试，6 项运行检查。

总入口自己的三个章节标签分别对应路线与资料、带许可的原始参考 notebook、可复现运行工具与 CI。文件夹关联作为后续维护提交保留，原有章节标签不变。它是四个项目的导航与下载入口。
