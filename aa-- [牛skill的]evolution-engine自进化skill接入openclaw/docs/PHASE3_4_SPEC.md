# Phase 3+4: Skill 代码进化 + 持续进化循环 — Codex 实现 SPEC

> Phase 3: Skill 自动创建/patch + SKILL.md 进化
> Phase 4: 持续监控 + 自动分诊 + 定时调度
> 日期：2026-04-21 | 预估：~700 行

---

## Phase 3: Skill 代码进化

### 新增文件

```
skills/evolution-engine/scripts/
├── skill_evolver.py          # [新] Skill 自动创建 + patch + 进化
```

### `scripts/skill_evolver.py` (~400行)

```python
class SkillEvolver:
    """Skill 进化器：自动创建、patch、优化"""
    
    def __init__(self, workspace_root: str):
        ...
    
    def auto_create_skill(
        self,
        task_description: str,
        steps: list,          # 执行步骤列表
        pitfalls: list,       # 遇到的坑
        tools_used: list,     # 使用的工具
        success_output: str   # 成功输出示例
    ) -> dict:
        """
        从成功完成的复杂任务中自动创建 skill
        
        触发条件（Hermes 原版）：
        - 5+ 工具调用
        - 遇到错误后找到解决方案
        - 用户纠正了方法
        - 非平凡工作流
        
        生成内容：
        1. SKILL.md（name, description, When to Use, Procedure, Pitfalls, Verification）
        2. 基于 steps 填充 Procedure
        3. 基于 pitfalls 填充 Pitfalls
        
        先写入 staging，评测通过后才部署。
        """
        ...
    
    def auto_patch_skill(
        self,
        skill_path: str,
        issue: str,           # 问题描述
        fix: str,             # 修复方案
        trace_id: str = None  # 关联的执行轨迹
    ) -> dict:
        """
        定向修复 skill 中的问题（patch，不是全量重写）
        
        patch 策略：
        1. 读取当前 SKILL.md
        2. 定位与 issue 相关的段
        3. 只修改那一段
        4. 不改 name/description（保持触发条件不变）
        5. 写入 staging
        
        返回修改前后的 diff
        """
        ...
    
    def evolve_skill(
        self,
        skill_path: str,
        baseline_scores: dict = None
    ) -> dict:
        """
        用反射式进化优化一个 skill
        
        流程：
        1. 跑 baseline 评测（如果没提供）
        2. 分析 skill 的失败轨迹
        3. 生成变体
        4. 跑评测
        5. 门控检查
        6. 返回最优变体（或无改善）
        """
        ...
    
    def _generate_skill_content(
        self,
        name: str,
        description: str,
        steps: list,
        pitfalls: list,
        tools: list,
        output_example: str
    ) -> str:
        """
        生成完整的 SKILL.md 内容
        
        模板：
        ---
        name: {name}
        description: {description}
        ---
        
        # {name}
        
        ## When to Use
        {trigger_conditions}
        
        ## Procedure
        {numbered_steps}
        
        ## Pitfalls
        {pitfall_list}
        
        ## Verification
        {verification_method}
        """
        ...
    
    def _compute_patch(
        self,
        content: str,
        issue: str,
        fix: str
    ) -> dict:
        """
        计算定向 patch
        
        返回：
        {
            "old_section": "## Procedure\n1. Step one\n2. Step two",
            "new_section": "## Procedure\n1. Step one (注意: xxx)\n2. Step two",
            "section_header": "## Procedure"
        }
        """
        ...
```

---

## Phase 4: 持续进化循环

### 新增文件

```
skills/evolution-engine/scripts/
├── performance_monitor.py    # [新] 性能监控 + 自动分诊
└── evolution_scheduler.py    # [新] 进化调度器
```

### `scripts/performance_monitor.py` (~200行)

```python
class PerformanceMonitor:
    """性能监控和自动分诊"""
    
    METRICS = {
        "skill_success_rate": {
            "threshold": 0.8,
            "window_days": 7,
            "action": "触发 skill 进化"
        },
        "user_correction_rate": {
            "threshold": 0.1,
            "window_days": 7,
            "action": "触发 prompt 进化"
        },
        "task_completion_rate": {
            "threshold": 0.85,
            "window_days": 7,
            "action": "全局诊断"
        },
        "proposal_approval_rate": {
            "threshold": 0.5,
            "window_days": 14,
            "action": "降低进化敏感度"
        }
    }
    
    def __init__(self, workspace_root: str):
        ...
    
    def collect_metrics(self) -> dict:
        """
        收集当前所有指标
        
        数据源：
        - evolution/traces/ → skill 成功率
        - memory/YYYY-MM-DD.md → 用户纠正频率
        - evolution-drafts/ → 提案批准率
        
        返回：
        {
            "metrics": {
                "skill_success_rate": {"value": 0.87, "status": "ok"},
                "user_correction_rate": {"value": 0.15, "status": "alert"},
                ...
            },
            "alerts": ["user_correction_rate 超过阈值 (0.15 > 0.1)"],
            "actions": ["建议触发 prompt 进化"]
        }
        """
        ...
    
    def auto_triage(self) -> list:
        """
        自动分诊：按 (改进潜力 × 使用频率) 排序所有可进化目标
        
        返回优先级列表：
        [
            {"target": "skills/weather/SKILL.md", "priority": 0.85, "reason": "成功率低(0.7)且使用频繁"},
            {"target": "AGENTS.md", "priority": 0.6, "reason": "用户纠正率高(0.15)"},
            ...
        ]
        """
        ...
    
    def generate_report(self) -> str:
        """生成 Markdown 格式的进化状态报告"""
        ...
```

### `scripts/evolution_scheduler.py` (~100行)

```python
class EvolutionScheduler:
    """进化调度器"""
    
    def __init__(self, workspace_root: str):
        ...
    
    def run_weekly_review(self) -> dict:
        """
        每周完整审查
        
        流程：
        1. 收集指标
        2. 跑全部 skill 的 baseline 评测
        3. 与上周 baseline 对比
        4. 自动分诊
        5. 对优先级最高的目标触发进化
        6. 生成报告
        """
        ...
    
    def run_daily_check(self) -> dict:
        """
        每日轻量检查
        
        流程：
        1. 检查指标是否超阈值
        2. 检查是否有新的强信号
        3. 如有问题触发定向进化
        """
        ...
    
    def suggest_cron_setup(self) -> str:
        """
        生成 OpenClaw cron 命令建议
        
        输出：
        openclaw cron add --name weekly-evolution-review --cron "0 3 * * 1" --message "执行每周进化审查：python3 evolution_scheduler.py weekly-review"
        openclaw cron add --name daily-evolution-check --cron "0 8 * * *" --message "执行每日进化检查：python3 evolution_scheduler.py daily-check"
        """
        ...
```

### 扩展 CLI

```bash
# Phase 3
python3 evolution_cli.py create-skill --task "..." --steps '["s1","s2"]' --pitfalls '["p1"]'
python3 evolution_cli.py patch-skill --skill-path <path> --issue "..." --fix "..."
python3 evolution_cli.py evolve-skill --skill-path <path>

# Phase 4
python3 evolution_cli.py monitor
python3 evolution_cli.py triage
python3 evolution_cli.py weekly-review
python3 evolution_cli.py daily-check
python3 evolution_cli.py cron-setup
```

---

## 验收标准

1. 所有新 .py 通过 ast.parse
2. auto_create_skill 能从任务信息生成完整 SKILL.md
3. auto_patch_skill 能定向修复 skill 中的问题
4. performance_monitor 能收集指标和生成报告
5. auto_triage 能按优先级排序进化目标
6. cron-setup 能生成 OpenClaw cron 命令
7. CLI 新子命令不破坏已有功能
