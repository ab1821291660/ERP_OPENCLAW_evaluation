# Agent Harness Platform 实现蓝图

## 1. 文档目标

这份文档的目标是把 `Agent Harness Platform` 这个开源项目从想法变成一套可以逐步实现的工程方案。它重点回答 6 个问题：

1. 这个项目到底解决什么问题
2. 为什么它和 AI Infra / Agent Infra JD 高度匹配
3. 整体系统怎么分层
4. 每一层要用什么工具，分别起什么作用
5. 接口应该怎么设计
6. 第一版应该按什么顺序实现

这不是“写一个 Agent Demo”，而是做一个面向生产工程的最小平台：

- 能运行 Agent workflow
- 能接 MCP 工具
- 能采集 trace / token / latency / cost
- 能对 Agent 结果做自动评测
- 能在 CI 里阻止质量回退
- 能本地部署，也能给出 K8s 部署入口

---

## 2. 项目定义

### 2.1 项目一句话定义

`Agent Harness Platform` 是一个面向 AI Agent 的工程化平台，负责把 Agent 从“能跑”推进到“可观测、可评测、可回归、可上线”。

### 2.2 它解决的核心问题

真实团队做 Agent 时，经常遇到下面这些问题：

- Agent 在本地能跑，换个模型或工具就退化
- Tool 调用失败了，但链路里看不清是 Prompt 问题、模型问题还是工具问题
- 没有统一数据集，无法判断某次改动是否真的变好
- 没有回归门禁，PR 合进来之后效果 silently degrade
- 工具执行权限太大，没有审计，也没有安全边界
- PoC 能演示，但没人敢把它放进生产流程

这个项目就是用平台能力解决这些问题。

### 2.3 它和 JD 的映射

这份 JD 关心的能力，你的项目会这样体现：

- `AI 工具驱动研发`：引入 Agent + MCP + 自动评测 + CI gate
- `从 PoC 到上线闭环`：把运行、评测、观测、部署、回归串起来
- `Infra 能力`：Docker、K8s、Redis、Postgres、GitHub Actions
- `可观测性`：OpenTelemetry + Phoenix/Langfuse
- `MCP / Skill / 沙箱执行`：工具网关、权限策略、受控执行
- `Harness Engineering`：数据集、评测器、基线对比、回归门禁

---

## 3. 第一版产品边界

第一版不要做成“大而全平台”，而是做一个清晰的 MVP。

### 3.1 第一版必须支持

- 一个可运行的 Agent workflow
- 两到三个 MCP tools
- 一个统一的 run API
- 一套标准数据集格式
- 一套自动评测流程
- trace 和 metrics 采集
- GitHub Actions 中自动跑回归

### 3.2 第一版不做

- 多租户权限体系
- 完整 Web UI
- 复杂 RBAC
- 分布式调度平台
- 真正的云托管控制台

第一版重点是证明你具备平台抽象能力，而不是堆功能。

---

## 4. 技术栈与角色分工

## 4.1 推荐主栈

- `Python 3.11`
- `FastAPI`
- `LangGraph`
- `PostgreSQL`
- `Redis`
- `Celery` 或 `RQ`
- `OpenTelemetry`
- `Phoenix` 或 `Langfuse`
- `Promptfoo` 或自定义评测器
- `Docker Compose`
- `Kubernetes manifests`
- `GitHub Actions`
- `pytest + ruff + mypy + pre-commit`

## 4.2 每个工具的作用

### FastAPI

作用：

- 提供控制平面 API
- 接收 run 请求、eval 请求、报告查询请求
- 暴露健康检查与配置查看接口

为什么要它：

- 接口清晰
- Python 生态成熟
- 跟 Pydantic 配合非常适合定义 schema

### LangGraph

作用：

- 执行 Agent workflow
- 管理状态流转
- 控制 tool call、memory、retry、branching

为什么要它：

- 它不是只做 chat loop，而是适合多步、长流程、状态化 Agent
- 很容易讲清楚状态机、节点、边和恢复逻辑

### MCP servers

作用：

- 给 Agent 提供标准化工具访问能力
- 把文件系统、Git、外部 API 等暴露为结构化工具

为什么要它：

- MCP 是 JD 里的直接加分项
- 你可以把重点放在“接入与治理层”，而不是写一堆 ad-hoc tools

### Tool Gateway

这不是现成工具，而是你要做的核心模块。

作用：

- 统一注册多个 MCP tools
- 做工具调用审计
- 做 allowlist / denylist / timeout / rate limit
- 屏蔽上层 Agent 对具体 MCP 实现差异的感知

为什么它重要：

- 这是“平台味”的关键
- 没有它，系统只是“Agent + tools”
- 有了它，系统才像“Agent 基础设施”

### OpenTelemetry

作用：

- 采集 trace、span、metrics
- 给 LLM call、tool call、eval run 统一观测格式

为什么要它：

- 这是现代可观测平台的通用标准
- 很适合和 Phoenix、OpenLIT、Langfuse 做联动

### Phoenix 或 Langfuse

作用：

- 查看 trace
- 分析 Agent 调用链
- 对比实验与运行效果

建议：

- 如果你强调 `observability + eval + tracing`，优先 `Phoenix`
- 如果你强调 `LLM engineering platform`，优先 `Langfuse`

### Promptfoo

作用：

- 在 CI/CD 中跑 prompt / model / app 的自动评测
- 对不同版本做回归比较
- 给 PR 提供 gate

为什么要它：

- 这是最容易把“评测工程化”做出来的工具

### Postgres

作用：

- 存 run metadata、eval metadata、配置、报告索引

### Redis

作用：

- 队列
- 缓存
- 异步任务状态

### Celery 或 RQ

作用：

- 执行异步 run / eval / report 任务

### Docker Compose

作用：

- 本地一键启动开发环境

### Kubernetes manifests

作用：

- 体现你知道如何把这套系统推进到正式部署形态

---

## 5. 总体架构

## 5.1 分层架构

建议按 5 层理解这个系统：

1. `Control Plane`
2. `Runtime Layer`
3. `Tool Access Layer`
4. `Observability & Eval Layer`
5. `Infra Layer`

### 1. Control Plane

由 FastAPI 提供：

- 创建 Agent run
- 查询 run 状态
- 提交 eval 任务
- 查询报告
- 管理工具配置与策略

### 2. Runtime Layer

由 LangGraph 驱动：

- 接收任务输入
- 执行多步 Agent workflow
- 选择模型
- 决定何时调用工具
- 输出结果与中间轨迹

### 3. Tool Access Layer

由 Tool Gateway + MCP 构成：

- 发现工具
- 注册工具
- 调用工具
- 注入策略
- 记录审计日志

### 4. Observability & Eval Layer

由 OTel + Phoenix/Langfuse + Eval Harness 构成：

- trace run 全链路
- 计算成本、延迟、失败率
- 评测结果质量
- 对比基线版本

### 5. Infra Layer

由 Postgres、Redis、Docker、K8s、GitHub Actions 构成：

- 持久化
- 异步执行
- 部署
- 自动回归

## 5.2 逻辑流

一次完整的请求大致如下：

1. 用户调用 `POST /runs`
2. API 校验请求参数并创建 run 记录
3. API 把任务扔给 worker
4. worker 调用 runtime 执行 Agent workflow
5. Agent 需要工具时，通过 Tool Gateway 调 MCP tool
6. 所有模型调用、工具调用、异常都写 trace
7. run 完成后，结果写入数据库
8. 如果开启自动评测，则异步触发 evaluator
9. evaluator 读取任务结果与 ground truth，计算分数
10. 报告生成模块聚合 run 与 eval 结果
11. 用户调用 `GET /reports/{id}` 查看结果

---

## 6. 推荐目录结构

```text
agent-harness-platform/
├─ apps/
│  ├─ api/
│  │  ├─ main.py
│  │  ├─ dependencies.py
│  │  ├─ routers/
│  │  │  ├─ runs.py
│  │  │  ├─ evals.py
│  │  │  ├─ reports.py
│  │  │  └─ tools.py
│  │  └─ schemas/
│  ├─ worker/
│  │  ├─ worker.py
│  │  ├─ tasks/
│  │  │  ├─ run_tasks.py
│  │  │  ├─ eval_tasks.py
│  │  │  └─ report_tasks.py
│  └─ demo_agent/
│     └─ sample_workflow.py
├─ platform/
│  ├─ runtime/
│  │  ├─ graph.py
│  │  ├─ nodes.py
│  │  ├─ state.py
│  │  └─ runner.py
│  ├─ tool_gateway/
│  │  ├─ registry.py
│  │  ├─ client.py
│  │  ├─ policy.py
│  │  ├─ audit.py
│  │  └─ schemas.py
│  ├─ sandbox/
│  │  ├─ executor.py
│  │  ├─ limits.py
│  │  └─ policy.py
│  ├─ observability/
│  │  ├─ tracing.py
│  │  ├─ metrics.py
│  │  └─ instrumentation.py
│  ├─ evals/
│  │  ├─ dataset.py
│  │  ├─ runner.py
│  │  ├─ evaluators/
│  │  │  ├─ exact_match.py
│  │  │  ├─ rubric_judge.py
│  │  │  └─ tool_success.py
│  │  └─ comparator.py
│  ├─ reports/
│  │  ├─ generator.py
│  │  └─ serializers.py
│  ├─ db/
│  │  ├─ models.py
│  │  ├─ session.py
│  │  └─ repositories/
│  └─ common/
│     ├─ config.py
│     ├─ enums.py
│     └─ exceptions.py
├─ mcp_servers/
├─ datasets/
├─ configs/
├─ deployments/
├─ tests/
├─ docs/
└─ .github/workflows/
```

---

## 7. 核心模块设计

## 7.1 Control Plane

### 目标

让外部系统以 API 的方式触发 run、eval、report，不直接碰内部执行细节。

### 职责

- 请求校验
- run 创建
- eval 任务调度
- 报告查询
- 工具与策略管理

### 为什么单独做这一层

因为平台系统的关键不是“跑一个脚本”，而是“把能力通过稳定接口暴露出来”。Control Plane 就是平台对外的合同。

---

## 7.2 Runtime Layer

### 目标

负责执行 Agent workflow。

### 内部组成

- `state.py`：定义 workflow 状态
- `nodes.py`：定义每个步骤的逻辑
- `graph.py`：定义节点连接关系
- `runner.py`：包装执行入口

### 状态设计

可以先定义一个统一状态对象：

```python
class AgentRunState(TypedDict):
    run_id: str
    task_type: str
    user_input: dict
    context: dict
    messages: list
    tool_calls: list
    intermediate_results: list
    final_output: dict | None
    status: str
    error: dict | None
```

### 基本节点

- `prepare_context`
- `plan`
- `select_tool`
- `invoke_tool`
- `synthesize_answer`
- `validate_output`
- `finish`

### 一次典型流程

1. prepare_context：准备任务上下文
2. plan：让模型生成执行计划
3. select_tool：判断是否要调工具
4. invoke_tool：通过 Tool Gateway 调用工具
5. synthesize_answer：综合工具输出生成结果
6. validate_output：检查输出格式与完整性
7. finish：持久化最终结果

这样设计的好处是每个节点都能单独 trace、单独测试、单独替换。

---

## 7.3 Tool Gateway

### 目标

提供统一的工具接入层，隔离上层 Agent 与具体 MCP server。

### 它要解决的问题

- 不同 tool 的调用协议差异
- 工具超时与失败处理
- 工具权限边界
- 工具调用审计
- 工具版本与元数据管理

### 核心对象

#### ToolSpec

定义工具的静态元信息：

```python
class ToolSpec(BaseModel):
    tool_name: str
    source: str
    description: str
    input_schema: dict
    timeout_seconds: int = 30
    requires_approval: bool = False
    tags: list[str] = []
```

#### ToolPolicy

定义工具的调用规则：

```python
class ToolPolicy(BaseModel):
    tool_name: str
    enabled: bool = True
    allow_task_types: list[str] = []
    deny_task_types: list[str] = []
    max_calls_per_run: int = 5
```

#### ToolInvocationRecord

记录运行时调用信息：

```python
class ToolInvocationRecord(BaseModel):
    run_id: str
    tool_name: str
    request_payload: dict
    response_payload: dict | None
    status: str
    latency_ms: int
    error: dict | None
```

### Gateway 对外接口

- `register_tool(spec: ToolSpec)`
- `list_tools() -> list[ToolSpec]`
- `get_tool(tool_name: str) -> ToolSpec`
- `invoke_tool(run_id: str, tool_name: str, payload: dict) -> dict`

### 实现逻辑

`invoke_tool()` 的处理流程建议是：

1. 查 `ToolSpec`
2. 查 `ToolPolicy`
3. 校验当前 run 是否允许调用
4. 创建 invocation record
5. 发起 MCP 调用
6. 记录 latency / status / output
7. 返回统一格式的结果

这样上层 runtime 永远只面对一个统一接口，不需要知道某个 tool 背后是 filesystem、git 还是外部 API。

---

## 7.4 Sandbox

### 目标

给高风险工具调用或命令执行提供边界。

### 为什么必须有

JD 里明确提到 `沙箱执行`。如果你的平台可以触发 shell、文件系统、代码修改、外部 API，那就应该有“受控执行”的抽象。

### 第一版可以做的最小能力

- timeout
- 工作目录限制
- 白名单命令
- 输出大小限制
- 审计日志

### Sandbox 抽象接口

```python
class SandboxExecutor(Protocol):
    def execute(self, command: list[str], cwd: str, timeout_seconds: int) -> dict: ...
```

### 返回结构

```python
{
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "duration_ms": 1200,
  "timed_out": False
}
```

### 后续可升级方向

- 容器级隔离
- seccomp / rootless
- network deny
- 文件路径策略

---

## 7.5 Observability

### 目标

让系统每个关键动作都可追踪。

### 你至少要打哪些 span

- run lifecycle
- model call
- tool selection
- tool invocation
- eval run
- report generation

### 你至少要采哪些指标

- run_success_rate
- run_latency_ms
- tool_error_rate
- avg_tool_calls_per_run
- token_usage_input
- token_usage_output
- estimated_cost_usd
- eval_pass_rate

### span 层级建议

```text
run
├─ prepare_context
├─ plan
│  └─ llm_call
├─ invoke_tool
│  └─ mcp_call
├─ synthesize_answer
│  └─ llm_call
└─ validate_output
```

### 实现建议

- 在 `runner.py` 最外层包一个 run span
- 在每个 LangGraph node 内部创建子 span
- 在 Tool Gateway 里打 tool invocation span
- 在 eval runner 里打 eval span

---

## 7.6 Eval Harness

### 目标

让 Agent 的质量变成“可以被持续度量的东西”。

### 它由哪几部分构成

- 数据集格式
- evaluator 集合
- 比较器 comparator
- 报告生成器
- CI gate

### 数据集格式建议

每条数据至少包含：

```json
{
  "case_id": "support-001",
  "task_type": "customer_support",
  "input": {
    "question": "订单什么时候发货？"
  },
  "expected": {
    "must_include": ["订单号", "物流状态"],
    "format": "json"
  },
  "metadata": {
    "difficulty": "easy"
  }
}
```

### evaluator 分类

#### 1. 规则型 evaluator

适合判断：

- 字段是否齐全
- JSON 格式是否合法
- 是否调用了必要工具
- 是否超过调用预算

#### 2. LLM judge evaluator

适合判断：

- 回答是否相关
- 是否忠于上下文
- 是否完整
- 是否存在明显幻觉

#### 3. 运行时 evaluator

适合判断：

- tool 成功率
- latency
- token / cost
- error rate

### Comparator

作用：

- 比较 baseline 和 candidate 两个版本
- 输出哪些指标提升、哪些指标退化

### CI gate 规则示例

- success_rate 不能低于 baseline 2%
- avg_latency 不能升高 20% 以上
- tool_error_rate 不能升高 5% 以上
- hallucination_score 不能更差

这一步最能体现 Harness Engineering 能力。

---

## 7.7 Report Generator

### 目标

把运行数据和评测结果整理成可读的输出。

### 第一版输出格式

- JSON 报告
- Markdown 报告

### Markdown 报告内容建议

- run 概览
- 样本总数
- 成功率
- 平均 latency
- 平均 cost
- 失败案例 Top N
- 与 baseline 的 diff

---

## 8. API 设计

下面这部分是系统最关键的“合同层”。

## 8.1 Runs API

### `POST /api/v1/runs`

作用：

- 创建一次 Agent run

请求体：

```json
{
  "agent_name": "support-agent",
  "task_type": "customer_support",
  "input": {
    "question": "请帮我查一下订单 12345 的状态"
  },
  "config": {
    "model": "gpt-4.1",
    "max_tool_calls": 4,
    "timeout_seconds": 60
  },
  "metadata": {
    "source": "manual-api"
  }
}
```

响应：

```json
{
  "run_id": "run_001",
  "status": "queued"
}
```

### 实现逻辑

1. 校验参数
2. 创建数据库记录
3. 投递 worker 任务
4. 返回 run_id

---

### `GET /api/v1/runs/{run_id}`

作用：

- 查询一次 run 的状态与结果

响应：

```json
{
  "run_id": "run_001",
  "status": "completed",
  "input": {...},
  "output": {...},
  "metrics": {
    "latency_ms": 3200,
    "tool_calls": 2,
    "estimated_cost_usd": 0.012
  },
  "error": null
}
```

---

### `GET /api/v1/runs/{run_id}/trace`

作用：

- 返回 trace 索引或 trace 链接

响应：

```json
{
  "run_id": "run_001",
  "trace_id": "abc123",
  "trace_url": "http://phoenix.local/traces/abc123"
}
```

---

## 8.2 Evals API

### `POST /api/v1/evals`

作用：

- 提交一次评测任务

请求体：

```json
{
  "agent_name": "support-agent",
  "dataset_name": "customer_support_v1",
  "candidate_config": {
    "model": "gpt-4.1"
  },
  "baseline_config": {
    "model": "gpt-4o-mini"
  },
  "evaluators": [
    "json_validity",
    "tool_success",
    "rubric_judge"
  ]
}
```

响应：

```json
{
  "eval_id": "eval_001",
  "status": "queued"
}
```

### 实现逻辑

1. 校验数据集是否存在
2. 创建 eval 记录
3. 投递异步任务
4. 逐条样本跑 candidate 与 baseline
5. 聚合结果

---

### `GET /api/v1/evals/{eval_id}`

作用：

- 查询评测任务进度与摘要

---

### `GET /api/v1/evals/{eval_id}/report`

作用：

- 获取完整报告

---

## 8.3 Tools API

### `GET /api/v1/tools`

作用：

- 列出当前已注册工具

### `POST /api/v1/tools/register`

作用：

- 注册新工具

请求体：

```json
{
  "tool_name": "git_status",
  "source": "mcp://git-server/status",
  "description": "Read git status from repository",
  "input_schema": {
    "type": "object",
    "properties": {
      "repo_path": {
        "type": "string"
      }
    }
  }
}
```

### `POST /api/v1/tools/{tool_name}/invoke`

作用：

- 手工测试某个工具

这个接口很适合调试，也很适合写集成测试。

---

## 8.4 Reports API

### `GET /api/v1/reports/{report_id}`

作用：

- 查询报告内容

### `GET /api/v1/reports/{report_id}.md`

作用：

- 下载 Markdown 报告

---

## 9. 数据模型设计

第一版数据库模型不用太复杂，核心有 5 张表就够了。

## 9.1 agent_runs

字段建议：

- id
- agent_name
- task_type
- status
- input_payload
- output_payload
- config_payload
- metrics_payload
- error_payload
- created_at
- updated_at

## 9.2 tool_invocations

- id
- run_id
- tool_name
- request_payload
- response_payload
- status
- latency_ms
- error_payload
- created_at

## 9.3 eval_runs

- id
- dataset_name
- candidate_config
- baseline_config
- status
- summary_payload
- created_at
- updated_at

## 9.4 eval_cases

- id
- eval_run_id
- case_id
- candidate_output
- baseline_output
- scores_payload
- passed

## 9.5 tool_registry

- id
- tool_name
- source
- description
- input_schema
- policy_payload
- enabled

---

## 10. 第一版实现路径

这里按照“最少阻塞路径”来排。

## 10.1 Phase 1：骨架

先做：

- FastAPI skeleton
- DB session
- run table
- worker skeleton
- docker compose

验收标准：

- `POST /runs` 能返回 `queued`
- worker 能消费任务

## 10.2 Phase 2：最小 Runtime

再做：

- LangGraph workflow
- 一个 demo task_type
- run result 持久化

验收标准：

- `GET /runs/{id}` 能看到结果

## 10.3 Phase 3：Tool Gateway

再做：

- Tool registry
- MCP client wrapper
- tool invoke tracing
- tool audit log

验收标准：

- Agent 至少能调用一个 filesystem 或 git tool

## 10.4 Phase 4：Observability

再做：

- OTel spans
- metrics export
- Phoenix/Langfuse 接通

验收标准：

- 能从 trace 看到一次完整 run 链路

## 10.5 Phase 5：Eval Harness

再做：

- dataset loader
- exact-match / schema / rubric evaluators
- report generator

验收标准：

- 一次 eval run 能输出汇总报告

## 10.6 Phase 6：CI Gate

再做：

- GitHub Actions workflow
- regression compare
- 失败阈值

验收标准：

- PR 能自动拦截退化

## 10.7 Phase 7：Sandbox

最后做：

- command allowlist
- timeout / cwd constraints
- 安全边界文档

验收标准：

- 高风险工具走受控执行链路

---

## 11. 测试策略

## 11.1 单元测试

覆盖：

- Tool policy 判断
- evaluator 评分逻辑
- report serializer
- run state 转换

## 11.2 集成测试

覆盖：

- API -> worker -> runtime 全链路
- runtime -> tool gateway -> MCP 全链路
- eval pipeline 全链路

## 11.3 回归测试

覆盖：

- 固定数据集
- baseline 对比
- 指标阈值检查

---

## 12. GitHub Actions 设计

建议至少有 3 个 workflow：

### `ci.yml`

负责：

- lint
- type check
- unit tests

### `integration.yml`

负责：

- 启动 Postgres / Redis
- 跑 API + worker 集成测试

### `eval-regression.yml`

负责：

- 加载标准数据集
- 跑 candidate eval
- 对比 baseline
- 生成 markdown summary
- 失败时阻止合并

---

## 13. 你在面试里该怎么讲这个项目

你可以按下面这条线讲：

1. 问题定义：Agent 最大问题不是“能不能回答”，而是“怎么稳定演进”
2. 架构分层：runtime、tool gateway、eval、observability、infra
3. 平台价值：把运行、评测、回归、观测串起来
4. 工程取舍：第一版不做大 UI，优先把平台内核打通
5. 安全意识：tool policy、sandbox、审计日志
6. 生产思维：CI gate、K8s manifests、runbook、threat model

这样讲，会明显比“我做了个 agent”更像 AI Infra 工程师。

---

## 14. 最后给你的落地建议

### 14.1 第一版最值得优先做的能力

优先级从高到低建议是：

1. run API
2. LangGraph runtime
3. Tool Gateway
4. OTel tracing
5. Eval Harness
6. CI regression gate
7. Sandbox

### 14.2 最容易做出作品感的交付物

- 一张架构图
- 一次 trace 截图
- 一份 eval report
- 一个 PR regression gate 截图
- 一段 2 分钟 demo gif

### 14.3 最能体现“这是你的作品”的增强点

如果你是在现有开源项目基础上二开，最建议你把原创性放在这几块：

- `Tool Gateway`
- `Policy Layer`
- `Eval Comparator`
- `PR Gate`
- `Sandbox Executor`

这些模块最能体现你的平台抽象能力。

---

## 15. 下一步建议

如果继续往下走，最自然的下一步是：

1. 先初始化仓库骨架
2. 我帮你写第一版目录和基础代码
3. 先把 `POST /runs` + `GET /runs/{id}` 跑通
4. 再接入第一个 MCP tool
5. 再补 trace 和 eval

如果你愿意，下一轮我可以直接继续帮你把这个仓库的 `MVP skeleton` 搭出来，包括：

- FastAPI 入口
- 项目目录
- Pydantic schema
- run API
- worker 骨架
- Docker Compose
- 第一版 README
