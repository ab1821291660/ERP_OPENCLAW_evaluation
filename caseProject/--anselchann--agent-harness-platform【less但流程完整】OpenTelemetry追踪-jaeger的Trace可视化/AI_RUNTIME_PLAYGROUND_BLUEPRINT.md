# AI Runtime Playground 蓝图

## 1. 项目目标

`AI Runtime Playground` 是一个面向 AI Infra 的 C++/Python 混合项目，用来展示你在以下方向的能力：

- 调度
- 并发执行
- 共享内存 / 高性能消息通道
- mock model serving 解耦
- tracing / benchmark / regression

第一版项目不追求“跑本地大模型”，而是先把运行时、控制面、观测和评测闭环打通。

---

## 2. 为什么先用 OpenAI-compatible mock

先用 mock 的原因是把系统问题和模型部署问题分开：

- 先验证 scheduler、worker、IPC、trace、benchmark
- 避免一开始被 CUDA、显存、权重和本地推理环境拖住
- 后续可以无缝替换成 vLLM 或其他 OpenAI-compatible provider

第一版要证明的是：

- 你能做平台分层
- 你能做调度和执行系统
- 你能做共享内存和性能对比实验

---

## 3. 总体架构

系统分成 6 层：

1. API / Control Plane
2. Scheduler Layer
3. Worker Runtime Layer
4. Provider Layer
5. Observability / Benchmark Layer
6. Infra Layer

### 3.1 API / Control Plane

职责：

- 接收任务
- 查询状态
- 触发 benchmark
- 读取报告

技术：

- Python
- FastAPI
- Pydantic

### 3.2 Scheduler Layer

职责：

- 任务入队
- 优先级调度
- worker 分配
- 记录 queue wait

技术：

- C++17/20
- priority queue
- mutex / condition variable

### 3.3 Worker Runtime Layer

职责：

- 从队列取任务
- 调 provider
- 汇总执行结果
- 返回结果

技术：

- C++ worker pool
- chrono / atomic / thread

### 3.4 Provider Layer

第一版：

- Python OpenAI-compatible mock provider

后续可替换：

- vLLM
- SGLang
- 任何兼容 `/v1/chat/completions` 的服务

### 3.5 Observability / Benchmark Layer

职责：

- trace 全链路
- 统计排队、执行、provider 延迟
- 对比不同策略
- 生成 Markdown 报告

技术：

- OpenTelemetry
- Python benchmark runner
- pandas

### 3.6 Infra Layer

职责：

- 持久化
- 部署
- 自动回归

技术：

- Postgres
- Docker Compose
- GitHub Actions

---

## 4. 技术边界划分

## 4.1 Python 负责

- API 层
- schema 校验
- mock provider
- benchmark orchestration
- 报告生成
- 数据库存储

## 4.2 C++ 负责

- runtime daemon
- scheduler
- queue
- worker pool
- shared-memory channel

## 4.3 Python 和 C++ 怎么通信

第一版推荐：

- Python API 调本地 `runtime daemon`
- runtime daemon 使用本地 TCP 或 Unix socket 暴露控制接口

这样实现最简单，调试也最方便。

第二版如果你要继续深入，再考虑：

- gRPC
- pybind11
- 更低开销的本地调用

---

## 5. 目录结构

```text
ai-runtime-playground/
├─ apps/
│  ├─ api/
│  ├─ mock_provider/
│  └─ benchmark_runner/
├─ runtime/
│  ├─ cpp/
│  └─ python_bindings/
├─ platform/
│  ├─ db/
│  ├─ observability/
│  ├─ reports/
│  └─ common/
├─ benchmarks/
│  ├─ scenarios/
│  └─ results/
├─ deployments/
├─ tests/
└─ docs/
```

---

## 6. 核心数据流

1. 用户调用 `POST /api/v1/tasks`
2. API 校验请求并写库
3. API 将任务发给 runtime daemon
4. scheduler 将任务放入队列
5. worker 从队列取任务
6. worker 调 mock provider
7. worker 返回结果和 metrics
8. API 更新任务状态
9. benchmark runner 聚合结果
10. report 模块生成报告

---

## 7. 接口设计

## 7.1 API 层

### `POST /api/v1/tasks`

提交任务。

请求体：

```json
{
  "task_type": "chat_completion",
  "priority": 5,
  "payload": {
    "model": "mock-gpt",
    "messages": [
      {
        "role": "user",
        "content": "hello"
      }
    ]
  },
  "options": {
    "timeout_ms": 5000
  }
}
```

响应：

```json
{
  "task_id": "task_001",
  "status": "queued"
}
```

### `GET /api/v1/tasks/{task_id}`

查询结果。

### `POST /api/v1/benchmarks/run`

触发 benchmark。

---

## 7.2 Runtime daemon

建议至少暴露下面这些能力：

- `submit_task`
- `get_task_status`
- `health`

第一版可以是非常简单的 HTTP 风格接口或本地 socket 协议。

内部结构建议：

- `Scheduler`
- `WorkerPool`
- `ProviderClient`
- `MetricsCollector`

---

## 7.3 Mock provider

### `POST /v1/chat/completions`

模拟模型响应。

能力建议：

- 固定响应
- 可配置 latency
- 可配置 error_rate
- 可配置 token_usage

这样可以稳定复现实验场景。

---

## 8. 模块设计

## 8.1 Scheduler

第一版先实现：

- priority + FIFO

输入：

- task_id
- priority
- timeout
- payload

输出：

- 任务出队顺序
- queue wait time

后续可实验：

- latency-aware scheduling
- shortest-job-first mock
- round-robin worker assignment

## 8.2 WorkerPool

第一版实现：

- 固定数量 worker
- 从 scheduler 拉任务
- 调 provider
- 上报 metrics

记录指标：

- dequeue_time
- provider_latency
- total_execution_time

## 8.3 Shared Memory Channel

第一版不必一上来就强绑主链路，可以先做成可选实验路径。

目标：

- 比较普通内存队列和共享内存 ring buffer 的传递性能
- 为后续项目亮点做准备

## 8.4 Metrics / Reports

至少输出：

- throughput
- p50/p95 latency
- queue wait time
- provider latency
- success rate

---

## 9. 实现顺序

## Phase 1：骨架

完成：

- FastAPI API 服务
- FastAPI mock provider
- 基础 README
- skeleton 目录

验收：

- API 和 mock provider 都能启动

## Phase 2：最小 runtime

完成：

- C++ runtime daemon
- FIFO queue
- worker pool
- provider client placeholder

验收：

- API 提交任务后能拿到 mock 结果

## Phase 3：priority scheduler

完成：

- priority queue
- queue wait metrics

验收：

- 高优先级请求先执行

## Phase 4：benchmark

完成：

- 固定场景 benchmark runner
- Markdown 报告

验收：

- 能生成对比报告

## Phase 5：observability

完成：

- OTel trace
- runtime / provider span

验收：

- 能查看完整链路

## Phase 6：shared memory path

完成：

- shared memory ring buffer 实验实现

验收：

- 普通队列 vs shm 队列对比数据可见

## Phase 7：CI gate

完成：

- benchmark regression workflow

验收：

- 退化时 CI fail

---

## 10. 每一块工具及作用

- `FastAPI`：快速搭控制面和 mock provider
- `Pydantic`：严格定义请求和响应
- `CMake`：构建 C++ runtime
- `C++ thread/mutex/atomic`：实现 scheduler 和 worker
- `mmap/shm_open`：共享内存实验
- `OpenTelemetry`：trace 链路
- `pandas`：benchmark 聚合
- `Docker Compose`：本地环境
- `GitHub Actions`：回归自动化

---

## 11. 简历项目描述版本

```text
AI Runtime Playground（个人项目）
AI Infra / Runtime 系统项目｜C++、Python、FastAPI、OpenTelemetry

- 设计并实现面向 AI Infra 的 C++/Python 混合运行时平台，采用 Python 构建控制平面，使用 C++ 实现任务调度、worker 执行与消息传递骨架。
- 基于 OpenAI-compatible mock provider 抽象模型服务接口，将 runtime orchestration 与 provider 解耦，支持后续平滑替换为真实推理服务。
- 设计优先级调度与多 worker 执行模型，支持任务排队、执行、结果回传以及排队时延、执行时延、总时延等指标采集。
- 规划共享内存 ring buffer 实验路径，用于对比普通队列与共享内存方案在任务传递场景下的性能差异。
- 集成 tracing、benchmark 和回归评测思路，为后续 AI runtime 性能优化与 CI regression gate 打基础。
```

---

## 12. 当前 skeleton 与下一步

当前 skeleton 的意义是：

- 把工程边界固定下来
- 让你后续实现时不至于乱
- 让仓库一开始就具备“平台项目”的样子

下一步建议优先做：

1. 启动 `apps/mock_provider`
2. 启动 `apps/api`
3. 让 API 能返回一个假 task id
4. 再补 C++ runtime daemon 的最小实现

