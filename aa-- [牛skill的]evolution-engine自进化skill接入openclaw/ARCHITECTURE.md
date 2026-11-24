# Evolution Engine — 完整架构设计文档 v2.0

> 最后更新：2026-04-21 | 版本：v2.0.0
> 作者：隐曜 🦁🌙 | 协作：Codex (GPT-5.3-codex)

---

## 一、项目定位

**Evolution Engine** 是一个让 OpenClaw Agent 具备自我进化能力的 skill，复刻 Hermes Agent 的 GAPA 机制，实现**感知→反思→变异→评估→选择→回滚**的完整闭环。

### 核心差异

| 对比 | AutoClaw hermes-evolution | Evolution Engine v2.0 |
|------|--------------------------|----------------------|
| 架构 | 纯 prompt 驱动，单层 | 五层 Python 脚本架构 |
| 评测 | 无评测闭环 | Phase 0 评测基础设施（合成评测集 + LLM-as-Judge + 三重门控） |
| 变异 | 只写提案草稿 | Phase 2 反射式进化 + Phase 3 Skill 自动创建/patch |
| 监控 | 无 | Phase 4 持续性能监控 + 自动分诊 |
| 版本管理 | 无 | 快照 + 回滚 + 完整版本历史 |
| 进化对象 | AGENTS.md / TOOLS.md / MEMORY.md | 同上 + SKILL.md + SOUL.md |

### 设计哲学

1. **评测先行** — 没有评测就无法验证进化有效（Phase 0 是地基）
2. **安全第一** — 所有进化必须通过三重门控 + 人工审批
3. **渐进式交付** — 五层架构，每层有验证门
4. **零成本默认** — rule 模式不用调 LLM，LLM 模式只留接口
5. **原子性操作** — 文件先写临时再 rename，变异前自动快照

---

## 二、五层架构概览

```
                    ┌─────────────────────────────────────┐
                    │   Phase 4: 持续进化循环              │
                    │   performance_monitor               │
                    │   evolution_scheduler               │
                    │   (监控→分诊→定时→报告)              │
                    ├─────────────────────────────────────┤
                    │   Phase 3: Skill 代码进化            │
                    │   skill_evolver                      │
                    │   (自动创建 / 定向patch / 反射进化)   │
                    ├─────────────────────────────────────┤
                    │   Phase 2: System Prompt 进化        │
                    │   prompt_evolver + prompt_tester     │
                    │   (失败分析→定位段落→受控变体→测试)   │
                    ├─────────────────────────────────────┤
                    │   Phase 1: 行为规则沉淀               │
                    │   signal_detector                    │
                    │   proposal_manager                   │
                    │   rule_tracker                       │
                    │   (信号→提案→评测→审批→追踪)          │
                    ├─────────────────────────────────────┤
                    │   Phase 0: 评测基础设施               │
                    │   dataset_builder                    │
                    │   llm_judge + gate_system             │
                    │   eval_runner + trace_collector       │
                    │   (评测集→评分→门控→轨迹)             │
                    └─────────────────────────────────────┘
```

### 层间依赖关系

```
Phase 4 ──调用──→ Phase 0/1/2/3（触发各层能力）
Phase 3 ──调用──→ Phase 0（评测验证）
Phase 2 ──调用──→ Phase 0（评测验证）
Phase 1 ──调用──→ Phase 0（评测验证）+ v0.1（reflector/selector）
Phase 0 ──独立──→ 无外部依赖
```

---

## 三、模块详细设计

### 3.1 Phase 0: 评测基础设施

#### dataset_builder.py — 合成评测集生成

**职责**：从 SKILL.md 自动生成测试用例

**流程**：
1. 解析 SKILL.md 的 frontmatter（name, description）
2. 提取核心功能描述（When to Use / Procedure / Pitfalls 段落）
3. 按模板生成四类测试用例：
   - `trigger_positive`：应该触发该 skill 的请求
   - `procedure`：执行流程正确性验证
   - `boundary`：边界/异常场景
   - `negative`：不应触发该 skill 的请求
4. 自动分割为 train(60%) / val(20%) / holdout(20%)
5. 保存为 JSON 格式

**设计决策**：
- 不调 LLM，纯模板+规则生成（零成本）
- 每个用例含 task_input + expected_behavior + category + difficulty
- holdout 集用于回归门控，防止新版本在已知场景上退步

#### llm_judge.py — 多维度评分

**维度与权重**：

| 维度 | 权重 | 评分内容 |
|------|------|---------|
| correctness | 0.4 | 输出是否完成了任务目标 |
| efficiency | 0.2 | 是否用最少步骤完成 |
| safety | 0.2 | 是否遵守安全规则 |
| consistency | 0.2 | 输出风格是否一致 |

**两种模式**：
- `rule` 模式（默认）：纯规则评分，零成本，不用 API
  - correctness：关键词匹配
  - efficiency：输出长度合理性
  - safety：危险操作关键词检测
  - consistency：格式一致性
- `llm` 模式（接口预留）：调 LLM API 做语义评分
  - 接口已定义但未实现，后续可接入

**评分范围**：0.0 ~ 1.0，总分 = 加权平均

#### gate_system.py — 三重门控

```
变体 ──→ 约束门 ──→ 回归门 ──→ 安全门 ──→ 通过/拒绝
```

**约束门（Constraint Gate）**：
- 文件大小 ≤ 15KB（SKILL.md）
- frontmatter 格式正确（name + description）
- description ≤ 1024 字符
- 无非法字符

**回归门（Regression Gate）**：
- 变体总分不低于 baseline - tolerance（默认 2%）
- holdout 集上无任何维度退步超过 5%
- 首次运行无 baseline 时默认通过

**安全门（Safety Gate）**：
- 无危险代码模式（rm -rf, os.system, eval, exec 等）
- 无凭证/密钥泄露
- 不修改 `evolution:freeze` 标记的内容
- Python 文件通过 ast.parse
- 不改变 name/description（保持触发条件）

#### eval_runner.py — 评测运行器

串联全部 Phase 0 组件的编排器：
1. `build-dataset` → 生成评测集
2. `_simulate_execution` → 基于 SKILL.md 内容生成模拟输出
3. `llm_judge.score_batch` → 批量评分
4. `gate_system.run_all_gates` → 三重门控
5. 保存结果到 `evolution/eval/`

**模拟执行**不是真正的 skill 运行，而是基于 SKILL.md 的 Procedure 段落生成预期行为描述。

#### trace_collector.py — 执行轨迹收集

记录每次 skill 执行的完整轨迹：
- skill_name、task_input、tool_calls、output
- success/failure、user_feedback、duration_ms
- 支持按 skill/成功失败/时间窗口查询
- 自动统计 skill 成功率和常见失败原因

---

### 3.2 Phase 1: 行为规则沉淀

#### signal_detector.py — 增强版信号检测

**信号分级**：

| 级别 | 信号类型 | 示例 |
|------|---------|------|
| 强 | correction | 用户明确纠正了 agent 输出 |
| 强 | preference | "以后都这样"/"不要这样" |
| 强 | workflow_teach | 教授可复用的新工作流 |
| 强 | struggle_success | 失败/重试后才成功 |
| 中 | pattern | 同类任务出现清晰步骤模式 |
| 中 | tool_pitfall | 工具/环境有值得记住的坑 |
| 中 | repeated_preference | 同一偏好被重复提到 |

**Cheap Gate**：至少一个强信号或两个中信号才值得做进化检查。

**信号提取策略**（从 memory/YYYY-MM-DD.md）：
- 搜索纠正模式："不对"、"改一下"、"应该是"、"我说的是"
- 搜索偏好声明："以后"、"总是"、"不要"、"帮我"
- 搜索重复模式：同类任务出现 2+ 次
- 搜索失败/重试模式："失败"、"重试"、"换一个"

#### proposal_manager.py — 提案管理

**提案生命周期**：

```
创建草稿(pending) → 评测验证 → 审批(approved)/拒绝(rejected)
                                        ↓
                              写入目标文件 + 版本备份
```

**签名系统**（去重）：
- 格式：`{target}-{normalized_rule}`
- 示例：`agents-research-before-writing`、`memory-reply-briefly`
- 检查位置：pending/ + approved/ + rejected/(14天内) + 目标文件已有规则

**目标文件路由**：

| 规则类型 | 写入目标 |
|---------|---------|
| 行为规则、安全边界、协作方式、全局 workflow | AGENTS.md |
| 工具坑点、环境路径、命令参数 | TOOLS.md |
| 稳定偏好、长期事实 | MEMORY.md |
| 可复用多步骤 workflow | skills/xxx/SKILL.md |

**评测闭环**：每个提案先通过 eval_runner 验证效果，不通过直接 rejected。

#### rule_tracker.py — 规则效果追踪

追踪已写入规则的实际表现：
- 触发次数、平均效果评分
- effectiveness 标记：positive / neutral / negative
- recommendation：keep / review / cleanup
- 陈旧规则扫描（30天未触发 → 建议清理）

---

### 3.3 Phase 2: System Prompt 进化

#### prompt_evolver.py — 反射式 Prompt 进化

**核心机制**：不是随机变异，而是从失败中学习。

```
执行轨迹(失败案例) → 定位导致失败的 prompt 段落 → 理解为什么失败 → 精确修改
```

**受保护文件配置**：

| 文件 | frozen 标记 | 单次最大修改 |
|------|------------|-------------|
| SOUL.md | "不泄露隐私"、"安全"、"边界" | 30% |
| AGENTS.md | "evolution:freeze"、"安全策略"、"权限控制" | 20% |
| TOOLS.md | 无 | 30% |

**变体生成规则**：
- 只修改与失败相关的段
- 不修改 frozen 标记的内容
- 单次修改不超过配置的最大百分比
- 保持整体结构不变
- 写入 staging 不改原文件

#### prompt_tester.py — Prompt 行为测试

对比 baseline 和 variant 在相同场景下的行为差异：
1. 从 prompt 内容中提取可测试场景
2. 用 baseline 生成预期行为
3. 用 variant 生成实际行为
4. 用 LLMJudge 对比评分
5. 检测是否有回归（regression_detected）

---

### 3.4 Phase 3: Skill 代码进化

#### skill_evolver.py — Skill 自动创建 + patch + 进化

**三种进化能力**：

1. **auto_create_skill** — 从成功任务自动创建 skill
   - 触发条件：5+ 工具调用 / 遇到错误后解决 / 用户纠正方法
   - 输出：完整 SKILL.md（name + description + When to Use + Procedure + Pitfalls + Verification）

2. **auto_patch_skill** — 定向修复
   - 只修改与 issue 相关的段
   - 不改 name/description（保持触发条件）
   - 返回修改前后的 diff

3. **evolve_skill** — 反射式进化
   - 跑 baseline → 分析失败轨迹 → 生成变体 → 评测 → 门控 → 返回最优变体

---

### 3.5 Phase 4: 持续进化循环

#### performance_monitor.py — 性能监控 + 自动分诊

**四项监控指标**：

| 指标 | 阈值 | 窗口 | 超阈值动作 |
|------|------|------|-----------|
| skill_success_rate | 0.8 | 7天 | 触发 skill 进化 |
| user_correction_rate | 0.1 | 7天 | 触发 prompt 进化 |
| task_completion_rate | 0.85 | 7天 | 全局诊断 |
| proposal_approval_rate | 0.5 | 14天 | 降低进化敏感度 |

**自动分诊**：按 `(改进潜力 × 使用频率)` 排序所有可进化目标。

#### evolution_scheduler.py — 进化调度器

**每周审查**：
1. 收集指标 → 跑全部 skill baseline → 与上周对比 → 自动分诊 → 触发最高优先级进化 → 生成报告

**每日检查**：
1. 检查指标是否超阈值 → 检查新强信号 → 如有问题触发定向进化

**Cron 集成**：生成 OpenClaw cron 命令，配置定时调度。

---

## 四、数据流

### 4.1 目录结构

```
evolution/
├── eval/
│   ├── baselines/          # 各 skill 的 baseline 评分
│   ├── datasets/           # 合成评测集
│   └── runs/               # 每次评测的完整记录
├── signals/                # 检测到的进化信号
├── hypotheses/             # 反思生成的假设
├── staging/                # 变异暂存区（不直接修改原文件）
│   └── skills/             # 自动创建的 skill 暂存
├── evaluations/            # 评估结果
├── mutations/              # 变异记录
├── versions/               # 版本快照
├── traces/                 # 执行轨迹
├── reports/                # 性能报告
└── log/                    # 审计日志

evolution-drafts/
├── pending/                # 待审批的提案草稿
├── approved/               # 已批准的提案
└── rejected/               # 已拒绝的提案
```

### 4.2 核心数据格式

**评测集**（JSON）：
```json
{
  "skill_name": "weather",
  "total_cases": 20,
  "splits": {"train": [...], "val": [...], "holdout": [...]},
  "cases": [{"id": "TC001", "task_input": "...", "expected_behavior": "...", "category": "trigger_positive", "difficulty": "easy"}]
}
```

**评测结果**（JSON）：
```json
{
  "skill_name": "weather",
  "total_score": 0.766,
  "dimensions": {"correctness": 0.415, "efficiency": 1.0, "safety": 1.0, "consistency": 1.0},
  "judge_mode": "rule",
  "generated_at": "2026-04-20T23:57:39"
}
```

**假设/提案**：
```json
{
  "id": "H20260420001",
  "signature": "agents-research-before-writing",
  "target_file": "AGENTS.md",
  "confidence": 0.86,
  "risk": "low",
  "trigger_type": "workflow_teach",
  "evidence": ["用户原话..."],
  "proposed_change": "具体修改内容...",
  "status": "pending"
}
```

---

## 五、安全机制

### 5.1 不可变核心

以下内容无论任何进化模式都不可修改：
- SOUL.md 中的底线价值观（隐私、安全、边界）
- AGENTS.md 中标记 `<!-- evolution:freeze -->` 的段落
- 凭证、密钥、API key

### 5.2 三重门控

所有变体必须通过：
1. **约束门** — 格式/大小/编码合规
2. **回归门** — 不比 baseline 差（holdout 集验证）
3. **安全门** — 无危险模式 + 不改核心字段

### 5.3 进化模式

| 模式 | 自动采纳条件 | 观察期 | 每日上限 | 适用场景 |
|------|------------|--------|---------|---------|
| conservative | low risk + conf≥0.9 | 72h | 1次 | 生产环境 |
| balanced（默认） | low+medium risk + conf≥0.85 | 24h | 3次 | 日常使用 |
| aggressive | low+medium risk + conf≥0.7 | 4h | 5次 | 实验探索 |

### 5.4 人工审批

- 所有 critical risk 必须人工审批
- 高风险变更即使自动采纳也有 24h 冷静期
- 用户可随时 `/evolution rollback` 回滚到任意版本

---

## 六、CLI 命令速查

### 基础命令（v0.1）

```bash
python3 evolution_cli.py observe              # 观测信号
python3 evolution_cli.py reflect              # 反思生成假设
python3 evolution_cli.py status               # 查看进化状态
```

### Phase 0: 评测

```bash
python3 evolution_cli.py build-dataset --skill-path <path> [--num-cases 20]
python3 evolution_cli.py eval-baseline --skill-path <path>
python3 evolution_cli.py eval-variant --skill-path <path> --variant-path <path>
python3 evolution_cli.py eval-compare --run-a <path> --run-b <path>
python3 evolution_cli.py skill-stats --skill-name <name>
```

### Phase 1: 规则沉淀

```bash
python3 evolution_cli.py detect-signals [--date YYYY-MM-DD]
python3 evolution_cli.py propose --signature <sig> --target <file> --change "..."
python3 evolution_cli.py approve <signature>
python3 evolution_cli.py reject <signature> [--reason "..."]
python3 evolution_cli.py list-proposals [--status pending]
python3 evolution_cli.py rule-stats [--signature <sig>]
python3 evolution_cli.py stale-rules
```

### Phase 2: Prompt 进化

```bash
python3 evolution_cli.py evolve-prompt --target SOUL.md|AGENTS.md|TOOLS.md [--traces-path <path>]
python3 evolution_cli.py test-prompt --target SOUL.md|AGENTS.md|TOOLS.md --variant <path>
```

### Phase 3: Skill 进化

```bash
python3 evolution_cli.py create-skill --task "..." --steps '["s1","s2"]' --pitfalls '["p1"]'
python3 evolution_cli.py patch-skill --skill-path <path> --issue "..." --fix "..."
python3 evolution_cli.py evolve-skill --skill-path <path>
```

### Phase 4: 持续循环

```bash
python3 evolution_cli.py monitor
python3 evolution_cli.py triage
python3 evolution_cli.py weekly-review
python3 evolution_cli.py daily-check
python3 evolution_cli.py cron-setup
```

---

## 七、技术约束

- **Python 3.12+**，type hints 全覆盖
- **只用标准库**（json, os, argparse, ast, re, hashlib, datetime, enum, dataclasses, glob, tempfile, logging, random, math, statistics）
- **不依赖第三方库**
- **所有文件操作原子性**（先写临时文件再 rename）
- **不调用外部 LLM API**（rule 模式为主，LLM 模式只留接口）

---

## 八、已知限制与后续规划

### 当前限制

1. **信号提取**仍基于关键词匹配，语义理解能力有限
2. **模拟执行**不是真正的 skill 运行，评测精度有限
3. **LLM-as-Judge** 只有 rule 模式，LLM 模式未实现
4. **FTS5 会话搜索**未实现（后续迭代）
5. **OpenClaw dreaming 整合**未实现

### 后续规划

1. 接入真实 LLM API 做语义级评分
2. 实现语义理解信号提取
3. FTS5 会话搜索增强
4. 与 OpenClaw dreaming/cron/hooks 深度整合
5. 外部记忆提供商支持
6. 多 Agent 协作进化
