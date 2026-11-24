# Phase 1: 行为规则沉淀（增强版）— Codex 实现 SPEC

> 在现有 v0.1 + Phase 0 + AutoClaw hermes-evolution 基础上融合
> 日期：2026-04-21 | 预估：~800 行新增

---

## 目标

将 AutoClaw 的 hermes-evolution 提案机制融入我们的架构，增加评测闭环：
1. 信号检测 → 证据提炼 → 规则变体生成
2. 变体先过评测验证，通过后才提交审批
3. 审批后写入 + 效果追踪
4. 持续无效的规则自动标记清理

## 新增文件

```
skills/evolution-engine/scripts/
├── proposal_manager.py      # [新] 提案管理（草稿/审批/拒绝/生效）
├── rule_tracker.py           # [新] 规则效果追踪
└── signal_detector.py        # [新] 增强版信号检测（强/中信号分级）
```

## 修改文件

```
skills/evolution-engine/scripts/
├── reflector.py              # [改] 融合签名系统+去重逻辑
└── evolution_cli.py          # [改] 添加新子命令
```

---

## 文件详细规格

### 1. `scripts/signal_detector.py` (~200行)

增强版信号检测，替代 observer.py 的简单关键词匹配。

```python
class SignalDetector:
    """增强版进化信号检测"""
    
    STRONG_SIGNALS = {
        "correction": "用户明确纠正了agent的输出或行为",
        "preference": "用户明确表达了稳定偏好（以后都这样/不要这样）",
        "workflow_teach": "用户教授了一个可复用的新工作流",
        "struggle_success": "经过明显失败/重试后才成功"
    }
    
    MEDIUM_SIGNALS = {
        "pattern": "同类任务出现了清晰的步骤模式",
        "tool_pitfall": "某个工具/环境有值得长期记住的坑点",
        "repeated_preference": "同一偏好在近期被重复提到"
    }
    
    SKIP_CONDITIONS = [
        "纯闲聊",
        "单轮简单问答",
        "tool call很少且没有纠正/偏好",
        "一次性上下文要求",
        "用户明确说这次只是临时的"
    ]
    
    def __init__(self, workspace_root: str):
        ...
    
    def detect(self, date: str = None) -> dict:
        """
        检测信号
        
        返回：
        {
            "date": "2026-04-21",
            "strong_signals": [...],
            "medium_signals": [...],
            "skip_reason": null,  # 或跳过原因
            "should_check": true,  # 是否值得做进化检查
            "gate_passed": true   # 是否通过了 Cheap Gate
        }
        """
        ...
    
    def _cheap_gate(self, signals: dict) -> bool:
        """
        Cheap Gate：至少一个强信号，或两个中信号
        
        证据不够明确直接跳过
        """
        ...
    
    def _extract_from_daily_note(self, date: str) -> list:
        """
        从 memory/YYYY-MM-DD.md 提取信号
        
        增强策略（比原 observer.py 更精准）：
        - 搜索用户纠正模式："不对"、"改一下"、"应该是"、"我说的是"
        - 搜索偏好声明："以后"、"总是"、"不要"、"帮我"
        - 搜索重复模式：同类任务出现 2+ 次
        - 搜索失败/重试模式："失败"、"重试"、"换一个"
        """
        ...
```

### 2. `scripts/proposal_manager.py` (~300行)

提案管理，融合 AutoClaw 的草稿系统 + 评测闭环。

```python
class ProposalManager:
    """进化提案管理"""
    
    DRAFT_DIR = "evolution-drafts"  # 相对于 workspace root
    STATUS_DIRS = ["pending", "approved", "rejected"]
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self._ensure_dirs()
    
    def create_proposal(
        self,
        signature: str,
        target_file: str,  # AGENTS.md / TOOLS.md / MEMORY.md / skills/xxx/SKILL.md
        trigger_type: str,  # correction / preference / workflow / struggle
        evidence: list,     # 用户原话列表
        proposed_change: str,  # 具体修改内容
        confidence: str,    # high / medium / low
        reason: str         # 为什么值得持久化
    ) -> dict:
        """
        创建进化提案
        
        流程：
        1. 签名规范化（小写、target+rule组成）
        2. 去重检查（是否已有同签名 pending/approved/rejected）
        3. 写入 pending 草稿
        4. 返回提案详情
        
        草稿格式：
        evolution-drafts/pending/<signature>.md
        """
        ...
    
    def evaluate_proposal(self, signature: str) -> dict:
        """
        用 Phase 0 的评测框架验证提案
        
        流程：
        1. 读取草稿内容
        2. 生成模拟变体（将 proposed_change 应用到 target_file 的副本）
        3. 跑 eval_runner 做对比评测
        4. 跑 gate_system 做门控检查
        5. 返回评测结果
        
        如果评测不通过，标记为 rejected 并记录原因
        """
        ...
    
    def approve_proposal(self, signature: str) -> dict:
        """
        批准提案
        
        流程：
        1. 读取 pending 草稿
        2. 备份当前 target_file（version_manager）
        3. 将 proposed_change 写入 target_file
        4. 移动草稿到 approved/
        5. 记录审计日志
        """
        ...
    
    def reject_proposal(self, signature: str, reason: str = None) -> dict:
        """拒绝提案"""
        ...
    
    def list_proposals(self, status: str = "pending") -> list:
        """列出提案"""
        ...
    
    def check_duplicates(self, signature: str) -> dict:
        """
        去重检查
        
        检查位置：
        - evolution-drafts/pending/
        - evolution-drafts/approved/
        - evolution-drafts/rejected/（14天内的）
        - 目标文件中是否已有同义规则
        
        返回：
        {
            "is_duplicate": false,
            "existing_draft": null,  # 或路径
            "existing_rule": null,   # 或目标文件中的已有规则
            "action": "create"       # create / update / skip
        }
        """
        ...
```

### 3. `scripts/rule_tracker.py` (~200行)

规则效果追踪。

```python
class RuleTracker:
    """追踪已写入规则的实际效果"""
    
    def __init__(self, workspace_root: str):
        ...
    
    def record_rule_application(
        self,
        signature: str,
        target_file: str,
        context: str  # 触发该规则的对话上下文摘要
    ) -> str:
        """记录一次规则被触发"""
        ...
    
    def get_rule_stats(self, signature: str, window_days: int = 30) -> dict:
        """
        获取规则统计
        
        返回：
        {
            "signature": "agents-research-before-writing",
            "trigger_count": 5,
            "avg_outcome_score": 0.85,
            "last_triggered": "2026-04-21T10:30:00",
            "effectiveness": "positive",  # positive / neutral / negative
            "recommendation": "keep"       # keep / review / cleanup
        }
        """
        ...
    
    def scan_stale_rules(self, threshold_days: int = 30) -> list:
        """
        扫描长期未触发或效果为负的规则
        
        返回建议清理的规则列表
        """
        ...
    
    def generate_effect_report(self) -> dict:
        """生成全部规则的效果报告"""
        ...
```

### 4. 修改 `scripts/reflector.py`

在现有的 Reflector 类中增加：
1. 签名生成（`_generate_signature`）
2. 去重检查（调用 ProposalManager.check_duplicates）
3. 目标文件路由（决定写入 AGENTS.md / TOOLS.md / MEMORY.md / SKILL.md）
4. 评测验证（调用 eval_runner 做对比）

```python
# 新增方法
def _generate_signature(self, action_type: str, action_detail: dict) -> str:
    """
    生成稳定签名
    
    规则：小写 + target + normalized rule
    示例：agents-research-before-writing, memory-reply-briefly
    """
    ...

def _route_target(self, hypothesis: dict) -> str:
    """
    路由到最合适的目标文件
    
    写入 AGENTS.md：行为规则、安全边界、协作方式、全局 workflow
    写入 TOOLS.md：工具坑点、环境路径、命令参数
    写入 MEMORY.md：稳定偏好、长期事实
    写入 SKILL.md：可复用多步骤 workflow
    """
    ...

def reflect_with_proposals(self, signals: dict) -> dict:
    """
    增强版反思：生成带签名的提案而非原始假设
    """
    ...
```

### 5. 扩展 `evolution_cli.py` 新子命令

```bash
# Phase 1 新增
python3 evolution_cli.py detect-signals [--date YYYY-MM-DD]
python3 evolution_cli.py propose --signature <sig> --target <file> --change "..."
python3 evolution_cli.py approve <signature>
python3 evolution_cli.py reject <signature> [--reason "..."]
python3 evolution_cli.py list-proposals [--status pending]
python3 evolution_cli.py rule-stats [--signature <sig>]
python3 evolution_cli.py stale-rules
```

### 6. 创建 evolution-drafts 目录结构

```
evolution-drafts/
├── pending/
├── approved/
└── rejected/
```

---

## 编码规范

同之前，只用标准库。

## 验收标准

1. 所有新 .py 通过 ast.parse
2. `detect-signals` 能从 memory 日志检测强/中信号
3. `propose` 能创建带签名的草稿到 pending/
4. `approve` 能将草稿内容写入目标文件（带版本备份）
5. 去重检查正常工作
6. 规则追踪可记录和查询
7. CLI 新子命令不破坏已有功能
