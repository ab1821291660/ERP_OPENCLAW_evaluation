<div align="center">

# 🧬 Evolution Engine

> *「Agent 不该永远用同一套规则活着」*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Modules](https://img.shields.io/badge/Modules-20-green.svg)](#模块一览)
[![CLI Commands](https://img.shields.io/badge/CLI_Commands-25-orange.svg)](#cli-命令速查)

<br>

**一个让 AI Agent 自动感知经验、反思问题、优化行为的 OpenClaw Skill。**
**不是你教它变好，是它自己学会变好。**

<br>

Hermes Agent 的 GAPA 机制证明了一件事：Agent 可以自己进化。<br>
Evolution Engine 把这个能力搬到了 OpenClaw 上，而且更安全、更可观测、更可控。

[看效果](#效果示例) · [安装](#安装) · [五层架构](#五层架构) · [工作原理](#工作原理) · [安全机制](#安全机制)

</div>

---

## 效果示例

```
用户      ❯ 进化一下

Engine    ❯ 🔍 Phase 1: 信号检测
            从 memory/2026-04-20.md 检测到 2 个强信号 + 2 个中信号
            ✅ Cheap Gate 通过（≥1强 或 ≥2中）
            
            📝 Phase 1: 提案生成
            签名: tools-ddgs-package-name-fix
            目标: TOOLS.md
            证据: "web-search 的 ddgs 包名更新问题修复"
            置信度: 0.86 | 风险: low
            
            🧪 Phase 0: 评测验证
            评测集: 20 cases | 评分: rule 模式
            变体总分: 0.82 vs baseline: 0.78 (+5.1%)
            
            🚦 三重门控: 约束门 ✅ | 回归门 ✅ | 安全门 ✅
            
            📋 提案已写入 evolution-drafts/pending/
            等待审批: approve tools-ddgs-package-name-fix
```

```
用户      ❯ 评测 weather skill

Engine    ❯ 📦 构建评测集: weather → 20 cases
            trigger_positive(6) / procedure(5) / boundary(4) / negative(5)
            分割: train(12) / val(4) / holdout(4)
            
            📊 Baseline 评测 (rule 模式):
            总分: 0.766
            correctness: 0.415 | efficiency: 1.0 | safety: 1.0 | consistency: 1.0
            
            💾 已保存: evolution/eval/baselines/weather_baseline.json
```

```
用户      ❯ 检查进化状态

Engine    ❯ 📈 性能监控 (2026-04-21)
            skill_success_rate:   1.0  ✅ (阈值 0.8)
            user_correction_rate: 0.02 ✅ (阈值 0.1)
            task_completion_rate: 1.0  ✅ (阈值 0.85)
            proposal_approval_rate: 1.0 ✅ (阈值 0.5)
            
            🎯 分诊优先级:
            无需立即进化的目标，系统运行良好
```





---
## 安装+使用
```bash
# 克隆到 OpenClaw skills 目录
git clone https://github.com/xiaoshiyilangzhao1996-droid/evolution-engine.git ~/.openclaw/workspace/skills/evolution-engine
```
或者在 OpenClaw 对话中：
```
> 帮我安装 evolution-engine skill
```


然后直接用：：这不是预设脚本。Engine 根据你的实际对话经验自动检测改进机会，评测验证后，再提交审批。
```
> 进化一下          → 完整进化循环 ##===================================
> 反思一下          → 只分析不修改
> 检查进化状态       → 查看概况
> 评测 weather skill → 跑 baseline ##===================================
> 进化模式均衡       → 切换模式
```
---
## 五层架构+可单独使用
```
          ┌─────────────────────────────────────────┐
          │   Phase 4: 持续进化循环                   │
          │   7×24 监控 → 自动分诊 → 定时调度          │
          ├─────────────────────────────────────────┤
          │   Phase 3: Skill 代码进化                 │
          │   自动创建 / 定向 patch / 反射式进化        │
          ├─────────────────────────────────────────┤
          │   Phase 2: System Prompt 进化             │
          │   失败分析 → 定位段落 → 受控变体 → 测试     │
          ├─────────────────────────────────────────┤
          │   Phase 1: 行为规则沉淀                    │
          │   信号检测 → 提案管理 → 效果追踪            │
          ├─────────────────────────────────────────┤
          │   Phase 0: 评测基础设施                    │
          │   合成评测集 + 多维评分 + 三重门控 + 轨迹     │
          └─────────────────────────────────────────┘
```
每一层独立可用，层层递进。没有 Phase 0 的评测，上面的进化都是盲飞。
| Phase | 名称 | 解决什么问题 | 核心模块 |
|-------|------|------------|---------|
| **Phase 0** | 评测基础设施 | 怎么知道进化是好的？ | dataset_builder, llm_judge, gate_system, eval_runner, trace_collector |
| **Phase 1** | 行为规则沉淀 | 怎么从对话中学到经验？ | signal_detector, proposal_manager, rule_tracker |
| **Phase 2** | Prompt 进化 | 怎么优化 Agent 的行为指导？ | prompt_evolver, prompt_tester |
| **Phase 3** | Skill 代码进化 | 怎么自动创建和修复 Skill？ | skill_evolver |
| **Phase 4** | 持续进化循环 | 怎么让进化自己跑起来？ | performance_monitor, evolution_scheduler |

---

## 工作原理
### Phase 0: 没有评测就没有进化
```
SKILL.md → 自动生成 20 个测试用例 → 模拟执行 → 多维度评分 →→→→ 三重门控
```
- **合成评测集**：从 SKILL.md 自动生成四类用例（正面触发/流程正确性/边界场景/反面否定）
- **多维度评分**：correctness(0.4) + efficiency(0.2) + safety(0.2) + consistency(0.2)
- **三重门控**：约束门（格式大小）+ 回归门（不比 baseline 差）+ 安全门（无危险模式）
- **零成本默认**：rule 模式纯规则评分，不调 API


### Phase 1: 从对话中学到经验
```
memory/YYYY-MM-DD.md → 强/中信号检测 → Cheap Gate → 签名去重 → 提案草稿 → 评测验证 → 审批
```
- **强信号**：用户纠正、稳定偏好、教授工作流、失败后成功
- **中信号**：步骤模式、工具坑点、重复偏好
- **Cheap Gate**：至少 1 强或 2 中，否则跳过
- **签名去重**：同一规则不会重复提案


### Phase 2: 反射式进化，不是随机变异
```
失败轨迹 → 定位导致失败的 prompt 段落 → 理解为什么失败 → 精确修改 → 测试验证
```
不是瞎改。是先搞清楚"这段指导为什么让 Agent 犯错了"，再只改那一段。


### Phase 3: Skill 也会长
```
复杂任务 → 自动提取 Skill → 使用中发现问题 → 定向 patch → 评测通过 → 部署
```
Hermes 最核心的能力：5+ 工具调用的复杂任务完成后，自动生成可复用 Skill。


### Phase 4: 让进化自己跑
```
性能监控 → 指标超阈值 → 自动分诊(改进潜力×使用频率) → 触发对应 Phase → 生成报告
```
可以配置 OpenClaw cron，每天/每周自动检查，有问题才通知你。




---
## 安全机制
进化引擎的第一性原则：**安全 > 进化**。
### 三重门控
```
变体 ──→ 约束门(格式/大小) ──→ 回归门(不比baseline差) ──→ 安全门(无危险模式) ──→ 通过/拒绝
```


### 不可变核心
无论什么进化模式，以下内容永远不可修改：
- SOUL.md 中的底线（隐私、安全、边界）
- `<!-- evolution:freeze -->` 标记的段落
- 凭证、密钥、API key


### 三种进化模式
| 模式 | 自动采纳条件 | 观察期 | 每日上限 | 适合 |
|------|------------|--------|---------|------|
| 🛡️ conservative | low risk + conf≥0.9 | 72h | 1次 | 生产环境 |
| ⚖️ balanced | low+medium + conf≥0.85 | 24h | 3次 | 日常使用 |
| ⚡ aggressive | low+medium + conf≥0.7 | 4h | 5次 | 实验探索 |


### 版本快照 + 一键回滚
每次变异前自动创建版本快照。任何进化都可以随时回滚。




---
## ----模块一览
20 个 Python 模块，6327 行代码，零第三方依赖。
```
scripts/
├── evolution_cli.py           # CLI 入口（25 个子命令）
│
├── 📦 Phase0.评测基础设施
│   ├── dataset_builder.py     # 合成评测集生成
│   ├── llm_judge.py           # 多维度评分（rule/llm 双模式）
│   ├── gate_system.py         # 三重门控
│   ├── eval_runner.py         # 评测运行器
│   └── trace_collector.py     # 执行轨迹收集
│

├── 📝 Phase1.行为规则沉淀
│   ├── signal_detector.py     # 强/中信号检测 + Cheap Gate
│   ├── proposal_manager.py    # 提案生命周期管理
│   └── rule_tracker.py        # 规则效果追踪
│
├── 🔄 Phase2.Prompt进化
│   ├── prompt_evolver.py      # 反射式变体生成
│   └── prompt_tester.py       # baseline vs variant 对比
│
├── 🛠️ Phase3.Skill代码进化
│   └── skill_evolver.py       # 自动创建 + 定向 patch
│
├── 📊 Phase4.持续循环
│   ├── performance_monitor.py # 监控 + 分诊
│   └── evolution_scheduler.py # 每周/每日调度
│

└── 🔧 v0.1核心
    ├── observer.py            # 信号观测
    ├── reflector.py           # 反思引擎
    ├── mutator.py             # 变异器
    ├── evaluator.py           # 评估器
    ├── selector.py            # 选择器
    └── version_manager.py     # 快照 + 回滚
```

---

## ----CLI 命令速查

```bash
# 基础
python3 scripts/evolution_cli.py status #进化状态概览 ##===================================

# Phase 0: 评测
python3 scripts/evolution_cli.py build-dataset --skill-path <path>
python3 scripts/evolution_cli.py eval-baseline --skill-path <path>
python3 scripts/evolution_cli.py eval-variant --skill-path <path> --variant-path <path>



# Phase 1: 规则
python3 scripts/evolution_cli.py detect-signals [--date YYYY-MM-DD]
python3 scripts/evolution_cli.py approve <signature>
python3 scripts/evolution_cli.py list-proposals

# Phase 2: Prompt
python3 scripts/evolution_cli.py evolve-prompt --target AGENTS.md
python3 scripts/evolution_cli.py test-prompt --target AGENTS.md --variant <path>

# Phase 3: Skill
python3 scripts/evolution_cli.py create-skill --task "..." --steps '["s1","s2"]'
python3 scripts/evolution_cli.py patch-skill --skill-path <path> --issue "..."
python3 scripts/evolution_cli.py evolve-skill --skill-path <path>



# Phase 4: 监控
python3 scripts/evolution_cli.py monitor
python3 scripts/evolution_cli.py triage
python3 scripts/evolution_cli.py cron-setup
```


---
## 仓库结构
```
evolution-engine/
├── README.md                 # 你正在看的
├── SKILL.md                  # OpenClaw 入口
├── ARCHITECTURE.md           # 完整架构设计文档（八章节）
├── VERSION.md                # 版本历史
├── scripts/                  # 20 个 Python 模块
├── data/rubrics/             # 评分标准
├── references/               # 评测指南 + 进化模式 + 安全规则
├── templates/                # Skill 模板 + 变异记录模板
└── docs/                     # 各 Phase 实现规格
```


---
## 背后的故事
Hermes Agent（Nous Research, 47000⭐）的 GAPA 机制证明了一个事情：AI Agent 可以感知自己的经验、反思哪里做得不好、自动改进行为。这不是科幻，是已经在跑的东西。

AutoClaw（GLM 出品）把这个能力搬到了 OpenClaw 上，但只做到了"提案"这一步——发现改进机会写个草稿，没有评测闭环，不知道改进到底好不好。

Evolution Engine做了一件更根本的事：**先建评测体系，再驱动进化。** 没有尺子怎么知道变好了还是变坏了？
Phase 0 是一切的地基，上面的每一层都建立在"可评测、可验证"的基础上。


设计灵感来源：
- **Hermes GAPA** — 感知→反思→进化循环
- **GEPA 论文**（ICLR 2026 Oral）— 反射式文本进化
- **六爻项目的"测试驱动修复"方法论** — 先建尺子再量东西
一个不告诉你进化到底有没有效果的引擎，不值得信任。



---
## 技术栈
- **Python 3.12+** — type hints 全覆盖
- **零第三方依赖** — 只用标准库
- **原子性文件操作** — 先写临时文件再 rename
- **LLM 可选** — rule 模式零成本，LLM 模式接口预留
---
<div align="center">
**Hermes** 证明了 Agent 可以进化。<br>
**AutoClaw** 证明了 OpenClaw 上也能进化。<br>
**Evolution Engine** 让进化可评测、、可验证、、可回滚。<br><br> ##===================================##===================================
*没有评测的进化，只是随机变异。*
<br>
MIT License © [隐曜 🦁🌙](https://github.com/xiaoshiyilangzhao1996-droid)
</div>
