# 财务分析 Agent：本地对话与历史

后端 FastAPI + DeepAgents 主 Agent、researcher、reviewer；前端 Vue 3 + JavaScript + Pinia + Vite。当前版本不连接 Langfuse，不提供反馈、财务数据浏览或评估功能。不新增请求表或页面消息快照表。

## 启动

已有 `.venv`、`.env` 和财务种子库 `data/agent.db` 可直接复用。若需要安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
corepack yarn install --frozen-lockfile
cd ..
.\.venv\Scripts\python.exe start_all.py --check
.\.venv\Scripts\python.exe start_all.py
```

打开 http://127.0.0.1:5173 ，后端文档为 http://127.0.0.1:8000/docs 。Ctrl+C 停止两个服务。

独立启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# 另一个终端
cd frontend
corepack yarn dev --host 127.0.0.1 --port 5173
```

如更换端口，建议用 `start_all.py --backend-port 8011 --frontend-port 5174`，脚本同步设置 Vite 代理和 CORS。手动分别启动时自行设置 `API_TARGET` / `FRONTEND_ORIGIN`。

## 使用与数据职责

- 输入中文财务问题即可；不用强制提供 report_id，也不需要选择 train/dev/test。
- Enter 发送；Shift+Enter 换行。文本、工具调用、子 Agent 输出按事件逐步显示，工具卡片可展开。
- 左侧可新建、切换、重命名、删除、清空会话；生成时避免切换，并可点击“停止生成”。
- `agent.db`：仅查询既有财务报告、题目及公司别名；Web 启动不迁移、不重建业务表。
- `checkpoints.db`：LangGraph 保存真实运行状态和主图消息历史。刷新页面从这里恢复；两个子 Agent 的临时逐字过程不会额外保存为页面快照，但主图的 task 交接及结果会保留。
- `store.db`：固定 demo-user 的会话目录、标题和最近更新时间。
- 删除会话会删除对应 Checkpointer thread 和 Store 目录，不删除财务数据。控制台测试自建 UUID 的 thread 没有会话目录，不会自动列在左侧。
- `logs/agent.jsonl` / `logs/error.log`：日志和错误堆栈。SSE 错误附请求编号便于查找。

SSE 使用 DeepAgents/LangGraph `astream_events(version="v3")`（当前框架标记为实验协议），经事件转换、有界 asyncio.Queue 和心跳传给前端。断连或停止会取消本轮图执行。一个会话同时只允许一次生成。当前为**本地单进程教学版**；不要增加 Uvicorn worker 数量来获得分布式并发保护，也不要未加认证直接公网部署。

## 无 pytest 的验证

```powershell
.\.venv\Scripts\python.exe tests/manual_web_check.py
.\.venv\Scripts\python.exe tests/manual_evidence_check.py
cd frontend
corepack yarn test
corepack yarn build
```

`manual_web_check.py` 使用临时 SQLite 库和离线模型验证真实 DeepAgents v3 / FastAPI / 会话 / 停止，不消耗模型 Token，不改变项目历史。证据检查只读真实财务库。

真实模型端到端检查需要自己在网页提问，会消耗模型 Token 并保存会话。例如：

> 请分析 Apple 2013 至 2014 年不动产、厂房和设备净额、经营活动产生的现金流、长期债务的变化，先找原始数据与出处，再计算增长率和债务增加额，并独立复核；没有找到的指标请明确说明，不要编造。

`app/agent_factory.py` 原有公开函数参数保持不变，仅修正 reviewer 回退实例初始化与运行时并发初始化。暂未接入 Langfuse SDK；配置中的旧 Langfuse 字段不触发采集。
