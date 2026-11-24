---
name: evolution-engine
description: "AI Agent 自我进化引擎 v2.0（五层架构）。Phase 0:评测框架 Phase 1:规则沉淀 Phase 2:Prompt进化 Phase 3:Skill进化 Phase 4:持续循环。说'进化一下'触发循环，'反思一下'只感知+反思，'检查进化状态'看概况，'评测weather'跑baseline评测。"
version: 2.0.0
metadata: {"openclaw": {"requires": {"bins": ["python3"]}}}
---

# Evolution Engine — 自我进化引擎 v2.0.0

## 架构概览：五层进化金字塔

```
Phase 4: 持续进化循环（自动监控→触发优化→审批→部署）
Phase 3: Skill代码进化（自动创建+patch+SKILL.md进化）
Phase 2: System Prompt进化（SOUL.md/AGENTS.md反射式优化）
Phase 1: 行为规则沉淀（增强版提案系统+评测闭环）
Phase 0: 评测基础设施（合成评测集+LLM-as-Judge+三重门控）
```

## 使用方式

### 快速命令

- **"进化一下"** → run-full-cycle（完整进化循环）
- **"反思一下"** → detect-signals + reflect（只分析不修改）
- **"检查进化状态"** → status + monitor
- **"评测 [skill名]"** → eval-baseline（跑 baseline 评测）
- **"回滚到版本 X"** → rollback
- **"进化模式保守/均衡/激进"** → 切换模式

### Phase 0: 评测基础设施

```bash
# 对任意 skill 生成评测集
python3 {baseDir}/scripts/evolution_cli.py build-dataset --skill-path <path>

# 跑 baseline 评测
python3 {baseDir}/scripts/evolution_cli.py eval-baseline --skill-path <path>

# 评测变体
python3 {baseDir}/scripts/evolution_cli.py eval-variant --skill-path <path> --variant-path <path>
```

### Phase 1: 行为规则沉淀

```bash
# 检测信号（强/中信号分级）
python3 {baseDir}/scripts/evolution_cli.py detect-signals

# 创建/批准/拒绝提案
python3 {baseDir}/scripts/evolution_cli.py propose --signature <sig> --target <file> --change "..."
python3 {baseDir}/scripts/evolution_cli.py approve <signature>
python3 {baseDir}/scripts/evolution_cli.py reject <signature>
python3 {baseDir}/scripts/evolution_cli.py list-proposals
```

### Phase 2: Prompt 进化

```bash
# 分析失败并生成 prompt 变体
python3 {baseDir}/scripts/evolution_cli.py evolve-prompt --target SOUL.md

# 测试 prompt 变体
python3 {baseDir}/scripts/evolution_cli.py test-prompt --target SOUL.md --variant <path>
```

### Phase 3: Skill 进化

```bash
# 自动创建新 skill
python3 {baseDir}/scripts/evolution_cli.py create-skill --task "..." --steps '["s1","s2"]'

# 定向修复 skill
python3 {baseDir}/scripts/evolution_cli.py patch-skill --skill-path <path> --issue "..." --fix "..."

# 进化现有 skill
python3 {baseDir}/scripts/evolution_cli.py evolve-skill --skill-path <path>
```

### Phase 4: 持续循环

```bash
# 查看监控指标
python3 {baseDir}/scripts/evolution_cli.py monitor

# 查看进化优先级
python3 {baseDir}/scripts/evolution_cli.py triage

# 生成 cron 配置
python3 {baseDir}/scripts/evolution_cli.py cron-setup
```

## 安全规则

1. **不可变核心**：SOUL.md 中的底线、AGENTS.md 中的安全策略、凭证
2. **frozen 标记**：`<!-- evolution:freeze -->` 标记的内容不可修改
3. **三重门控**：约束门（大小/格式）+ 回归门（不比baseline差）+ 安全门（无危险模式）
4. **人工审批**：所有变更必须经用户批准
5. **版本快照**：每次变异前自动快照，可随时回滚

## 进化模式

| 模式 | 自动采纳 | 观察期 | 每日上限 |
|------|---------|--------|---------|
| 保守 | low + conf≥0.9 | 72h | 1次 |
| 均衡（默认） | low+medium + conf≥0.85 | 24h | 3次 |
| 激进 | low+medium + conf≥0.7 | 4h | 5次 |

## 文件位置

- 脚本：`{baseDir}/scripts/`（15个Python模块）
- 评测数据：`evolution/eval/`
- 进化草稿：`evolution-drafts/{pending,approved,rejected}/`
- 版本快照：`evolution/versions/`
- 执行轨迹：`evolution/traces/`
- 配置：`evolution/config.yaml`
