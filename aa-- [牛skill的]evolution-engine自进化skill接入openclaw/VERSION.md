# Evolution Engine — 版本历史

> 所有迭代留痕，每次变更记录在这里。

---

## v2.0.0 (2026-04-21) — 五层架构完整交付

**里程碑：从单层脚本到完整五层进化金字塔**

### 新增模块（Phase 0-4，13个新文件）

| 文件 | Phase | 行数 | 职责 |
|------|-------|------|------|
| `dataset_builder.py` | Phase 0 | ~300 | 从 SKILL.md 自动生成合成评测集（20个测试用例，train/val/holdout 分割） |
| `llm_judge.py` | Phase 0 | ~350 | 多维度评分（correctness/efficiency/safety/consistency），支持 rule 模式（零成本）和 LLM 模式（留接口） |
| `gate_system.py` | Phase 0 | ~200 | 三重门控：约束门（格式/大小）+ 回归门（不比 baseline 差）+ 安全门（无危险模式） |
| `eval_runner.py` | Phase 0 | ~250 | 评测运行器，串联 dataset_builder + llm_judge + gate_system |
| `trace_collector.py` | Phase 0 | ~150 | 执行轨迹收集，支持按 skill/成功失败查询 |
| `signal_detector.py` | Phase 1 | ~200 | 增强版信号检测（强/中信号分级 + Cheap Gate） |
| `proposal_manager.py` | Phase 1 | ~300 | 提案管理（草稿/审批/拒绝/去重/评测验证） |
| `rule_tracker.py` | Phase 1 | ~200 | 规则效果追踪（触发次数/效果评分/陈旧清理） |
| `prompt_evolver.py` | Phase 2 | ~400 | 反射式 Prompt 进化（失败轨迹分析→定位相关段落→生成受控变体） |
| `prompt_tester.py` | Phase 2 | ~200 | Prompt 行为测试（baseline vs variant 对比评分） |
| `skill_evolver.py` | Phase 3 | ~400 | Skill 自动创建 + 定向 patch + 反射式进化 |
| `performance_monitor.py` | Phase 4 | ~200 | 性能监控 + 自动分诊（按改进潜力×使用频率排序） |
| `evolution_scheduler.py` | Phase 4 | ~100 | 进化调度器（每周审查 + 每日检查 + cron 配置生成） |

### 修改的文件（v0.1 原有7个）

| 文件 | 变更内容 |
|------|---------|
| `observer.py` | 无变更 |
| `reflector.py` | 新增 `_generate_signature`、`_route_target`、`reflect_with_proposals` |
| `mutator.py` | 无变更 |
| `evaluator.py` | 无变更 |
| `selector.py` | 无变更 |
| `version_manager.py` | 无变更 |
| `evolution_cli.py` | 扩展 25 个子命令（Phase 0: 5个, Phase 1: 7个, Phase 2: 2个, Phase 3: 3个, Phase 4: 5个, 原有: 3个） |

### 总计

- **20 个 Python 模块**
- **6327 行代码**
- **25 个 CLI 子命令**
- **5 个文档文件**（ARCHITECTURE.md、SKILL.md、README.md、VERSION.md、EVAL_GUIDE.md）

### 验证结果

- ✅ 全部 20 个 .py 通过 ast.parse
- ✅ weather skill baseline 评分 0.766
- ✅ 信号检测从日记中识别出强信号（preference + workflow_teach）
- ✅ 三重门控全部通过
- ✅ 自动创建 skill 生成完整 SKILL.md
- ✅ 定向 patch 返回 diff
- ✅ 性能监控四项指标全部 ok

### 调研基础

本版本基于以下调研和参考：
- Hermes Agent GAPA 机制拆解（Nous Research, 47000⭐）
- AutoClaw hermes-evolution skill 原版（399行，纯 prompt 驱动提案器）
- AutoClaw 自我进化方案设计（五层渐进式交付）
- OpenClaw 原生机制研究（standing-orders、hooks、dreaming、memory）
- GEPA 论文（ICLR 2026 Oral，反射式文本进化）
- GitHub 生态参考：OpenViking、EvoMap/evolver、vibeeval

---

## v0.1.0 (2026-04-20) — 初始六层架构

**里程碑：第一个可运行的进化循环**

### 新增模块（7个文件，2191行）

| 文件 | 职责 |
|------|------|
| `observer.py` | 信号观测（关键词匹配，从 memory 日志提取） |
| `reflector.py` | 反思引擎（信号→假设，生成 H-YYYYMMDD-NNN） |
| `mutator.py` | 变异器（假设→具体变更，写入 staging） |
| `evaluator.py` | 评估器（语法检查 + 安全扫描 + 质量评分） |
| `selector.py` | 选择器（按 confidence 和 risk 决定是否采纳） |
| `version_manager.py` | 版本快照 + 回滚 |
| `evolution_cli.py` | CLI 入口（observe/reflect/mutate/evaluate/apply/status） |

### 配套文件

- `config.yaml` — 进化模式配置
- `ARCHITECTURE.md` — 六层架构设计
- `SPEC.md` — 详细规格（~16000字）
- `references/PATTERNS.md` — 进化模式参考
- `references/SAFETY_RULES.md` — 安全规则
- `templates/skill_template.md` — Skill 模板
- `templates/mutation_record.json` — 变异记录模板

### 验证结果

- ✅ 全部 ast.parse 通过
- ✅ observe → reflect 完整循环跑通
- ✅ 从 memory/2026-04-20.md 提取信号 → 生成假设 H20260420001

---

## 版本命名规则

- **主版本（Major）**：架构层级变化（如 v0→v1→v2）
- **次版本（Minor）**：新增模块或重大功能变更
- **修订版本（Patch）**：Bug 修复、配置调整、文档更新

格式：`vMAJOR.MINOR.PATCH`，如 `v2.0.0`
