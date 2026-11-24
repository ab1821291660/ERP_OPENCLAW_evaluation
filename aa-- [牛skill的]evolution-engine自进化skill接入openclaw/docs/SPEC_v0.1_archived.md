# Evolution Engine — Codex 实现 SPEC

> 实现者：Codex | 审核者：隐曜
> 日期：2026-04-20 | 预估：~2500 行

---

## 项目概述

在 `/root/.openclaw/workspace/skills/evolution-engine/` 下实现一个让 OpenClaw Agent 能自我进化的 skill。

核心循环：**感知 → 反思 → 变异 → 评估 → 选择 → 应用**

## 目录结构

```
skills/evolution-engine/
├── SKILL.md
├── scripts/
│   ├── evolution_cli.py        # CLI入口（必须第一个实现）
│   ├── observer.py             # L0 感知
│   ├── reflector.py            # L1 反思
│   ├── mutator.py              # L2 变异
│   ├── evaluator.py            # L3 评估
│   ├── selector.py             # L4 选择+应用
│   └── version_manager.py      # L5 版本管理
├── references/
│   ├── PATTERNS.md
│   └── SAFETY_RULES.md
└── templates/
    ├── skill_template.md
    └── mutation_record.json
```

数据目录（workspace根）：
```
evolution/
├── config.yaml
├── signals/
├── hypotheses/
├── staging/
├── evaluations/
├── mutations/
└── versions/
```

---

## 文件实现顺序和详细规格

### 1. `scripts/evolution_cli.py` (~200行)

统一 CLI 入口，所有子命令通过它调用。

```python
# 用法：
# python3 evolution_cli.py observe [--date YYYY-MM-DD]
# python3 evolution_cli.py reflect [--date YYYY-MM-DD]
# python3 evolution_cli.py mutate --hypothesis-id H001
# python3 evolution_cli.py evaluate --mutation-id M001
# python3 evolution_cli.py apply --mutation-id M001 [--force]
# python3 evolution_cli.py rollback --version-id V001
# python3 evolution_cli.py status
# python3 evolution_cli.py run-full-cycle  # 执行完整进化循环
```

要求：
- argparse 实现，子命令结构
- 每个子命令调用对应模块
- `run-full-cycle` 按顺序执行 observe → reflect → (对每个auto_approve的假设) mutate → evaluate → apply
- `status` 显示当前进化状态（最近信号数、待审批假设数、今日变异数）
- 所有输出用 JSON 格式到 stdout，日志到 stderr
- exit code: 0=成功, 1=参数错误, 2=执行错误, 3=需要人工审批

### 2. `scripts/version_manager.py` (~250行)

版本快照和回滚。

```python
class VersionManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.evolution_dir = os.path.join(workspace_root, "evolution")
        self.versions_dir = os.path.join(self.evolution_dir, "versions")
    
    def create_snapshot(self, description: str) -> str:
        """创建当前 workspace 的版本快照，返回 version_id"""
        # 快照范围：skills/ 目录 + MEMORY.md + AGENTS.md + SOUL.md
        # 用 tar.gz 压缩，文件名 v_YYYYMMDD_HHMMSS.tar.gz
        # 同时创建 metadata.json 记录 {version_id, timestamp, description, files_hash}
        
    def restore_snapshot(self, version_id: str) -> bool:
        """回滚到指定版本"""
        # 1. 验证快照存在且完整
        # 2. 解压到临时目录
        # 3. 用 ast.parse 验证所有 .py 文件
        # 4. 原子替换（先备份当前为 .bak，再替换）
        # 5. 记录回滚日志
        
    def list_versions(self, limit: int = 20) -> list:
        """列出所有版本"""
        
    def cleanup_old_versions(self, keep_days: int = 30) -> int:
        """清理旧版本"""
        
    def get_current_version_id(self) -> str:
        """获取当前版本ID"""
```

快照范围：
```python
SNAPSHOT_PATHS = [
    "skills/",          # 所有 skill
    "MEMORY.md",        # 长期记忆
    "AGENTS.md",        # Agent 配置
    "SOUL.md",          # 人格
    "IDENTITY.md",      # 身份
    "USER.md",          # 用户信息
    "TOOLS.md",         # 工具清单
    "HEARTBEAT.md",     # 心跳配置
]
```

### 3. `scripts/observer.py` (~300行)

从交互日志中提取进化信号。

```python
class Observer:
    def __init__(self, workspace_root: str):
        ...
    
    def observe(self, date: str = None) -> dict:
        """执行感知，返回信号"""
        signals = []
        
        # 1. 读 memory/{date}.md 提取信号
        signals.extend(self._extract_from_daily_note(date))
        
        # 2. 检查 skill 使用统计
        signals.extend(self._check_skill_coverage(date))
        
        # 3. 检查最近执行失败记录
        signals.extend(self._check_execution_failures(date))
        
        return {
            "date": date,
            "signals": signals,
            "summary": self._summarize(signals)
        }
```

信号类型枚举：
```python
class SignalType(Enum):
    SKILL_MISS = "skill_miss"               # 缺少覆盖场景的skill
    SKILL_QUALITY_LOW = "skill_quality_low"  # skill输出质量差
    REPEATED_REQUEST = "repeated_request"    # 重复同类请求（说明首次不满足）
    USER_CORRECTION = "user_correction"      # 用户纠正了agent的输出
    EXECUTION_FAILURE = "execution_failure"  # 命令/skill执行失败
    ROUTING_ERROR = "routing_error"          # skill路由错误（该用没用）
    CONFIG_GAP = "config_gap"                # 配置缺失或不合理
    PROCESS_IMPROVEMENT = "process_improvement"  # 流程优化机会
```

信号严重度：
```python
class Severity(Enum):
    LOW = "low"          # 小问题，可以等
    MEDIUM = "medium"    # 影响体验，应该改进
    HIGH = "high"        # 影响功能，必须改进
    CRITICAL = "critical"  # 影响安全/稳定，立即处理
```

从 daily note 提取信号的启发式规则：
- 搜索"失败"、"错误"、"不行"、"重试"等关键词
- 搜索用户纠正模式（正元说"不对"、"改一下"等）
- 搜索 skill 未命中模式（agent 回复中没有引用相关 skill）
- 统计同类请求的频率

### 4. `scripts/reflector.py` (~350行)

分析信号，生成改进假设。

```python
class Reflector:
    def __init__(self, workspace_root: str):
        ...
    
    def reflect(self, signals: dict) -> dict:
        """分析信号，生成假设"""
        hypotheses = []
        
        for signal in signals.get("signals", []):
            hypothesis = self._analyze_signal(signal)
            if hypothesis:
                hypotheses.append(hypothesis)
        
        # 去重和合并相似假设
        hypotheses = self._deduplicate(hypotheses)
        
        return {
            "date": signals["date"],
            "hypotheses": hypotheses,
            "signal_count": len(signals.get("signals", [])),
            "hypothesis_count": len(hypotheses)
        }
    
    def _analyze_signal(self, signal: dict) -> dict:
        """单个信号的假设生成"""
        ...
```

假设格式：
```python
{
    "id": "H001",                    # 唯一ID
    "created_at": "2026-04-20T15:00:00",
    "signal_refs": ["S001", "S002"], # 关联的信号ID
    "root_cause": "...",             # 根因分析
    "action_type": "create_skill",   # 动作类型
    "action_detail": { ... },        # 动作详情
    "confidence": 0.85,              # 置信度 0-1
    "risk": "low",                   # 风险等级
    "reasoning": "...",              # 推理过程
    "auto_approve_eligible": True    # 是否符合自动采纳条件
}
```

动作类型：
```python
class ActionType(Enum):
    CREATE_SKILL = "create_skill"              # 创建新skill
    MODIFY_SKILL_MD = "modify_skill_md"        # 修改SKILL.md
    MODIFY_SKILL_SCRIPT = "modify_skill_script" # 修改skill脚本
    MODIFY_MEMORY = "modify_memory"            # 修改MEMORY.md
    MODIFY_AGENTS = "modify_agents"            # 修改AGENTS.md
    MODIFY_SOUL = "modify_soul"                # 修改SOUL.md
    CREATE_STANDING_ORDER = "create_standing_order" # 创建常驻指令
    CREATE_CRON = "create_cron"                # 创建定时任务
    MODIFY_CONFIG = "modify_config"            # 修改配置
```

风险判定规则：
```python
RISK_RULES = {
    "create_skill": "low",
    "modify_skill_md": "medium",
    "modify_skill_script": "high",
    "modify_memory": "low",
    "modify_agents": "medium",
    "modify_soul": "high",
    "create_standing_order": "medium",
    "create_cron": "medium",
    "modify_config": "critical"
}
```

### 5. `scripts/mutator.py` (~300行)

执行变异。

```python
class Mutator:
    def __init__(self, workspace_root: str):
        ...
    
    def mutate(self, hypothesis: dict) -> dict:
        """执行变异"""
        action_type = hypothesis["action_type"]
        
        # 1. 在 staging 目录创建工作空间
        staging_dir = self._create_staging(hypothesis["id"])
        
        # 2. 根据动作类型执行
        if action_type == "create_skill":
            result = self._create_skill(staging_dir, hypothesis)
        elif action_type == "modify_skill_md":
            result = self._modify_skill_md(staging_dir, hypothesis)
        elif action_type == "modify_skill_script":
            result = self._modify_skill_script(staging_dir, hypothesis)
        # ... 其他动作
        
        # 3. 记录变异元数据
        mutation = {
            "id": f"M{int(time.time())}",
            "hypothesis_id": hypothesis["id"],
            "action_type": action_type,
            "staging_path": staging_dir,
            "files_created": result.get("files_created", []),
            "files_modified": result.get("files_modified", []),
            "created_at": datetime.now().isoformat(),
            "status": "staged"
        }
        
        return mutation
```

变异操作必须：
- **原子性**：先写临时文件，验证通过后再 rename
- **可追溯**：每个变异记录完整的 before/after
- **安全**：不执行任何网络操作、不修改系统文件

`_create_skill` 实现细节：
1. 在 staging 目录创建 skill 目录结构
2. 从 templates/skill_template.md 生成 SKILL.md
3. 根据 hypothesis 的 action_detail 填充内容
4. 如果需要 scripts/，创建对应的脚本骨架

`_modify_skill_md` 实现细节：
1. 复制原 SKILL.md 到 staging
2. 根据 hypothesis 定位修改点
3. 应用修改
4. 记录 diff

`_modify_skill_script` 实现细节：
1. 复制原脚本到 staging
2. 根据 hypothesis 生成修改方案
3. 应用修改
4. ast.parse 验证

### 6. `scripts/evaluator.py` (~200行)

评估变异。

```python
class Evaluator:
    def __init__(self, workspace_root: str):
        ...
    
    def evaluate(self, mutation: dict) -> dict:
        """评估变异"""
        checks = {
            "syntax": self._check_syntax(mutation),
            "structure": self._check_structure(mutation),
            "security": self._check_security(mutation),
            "size": self._check_size(mutation),
            "regression": self._check_regression(mutation),
        }
        
        all_passed = all(c["passed"] for c in checks.values())
        
        return {
            "mutation_id": mutation["id"],
            "checks": checks,
            "overall": "pass" if all_passed else "fail",
            "recommendation": self._recommend(checks)
        }
    
    def _check_syntax(self, mutation: dict) -> dict:
        """语法检查"""
        results = []
        for f in mutation.get("files_created", []) + mutation.get("files_modified", []):
            if f.endswith(".py"):
                try:
                    with open(f) as fh:
                        ast.parse(fh.read())
                    results.append({"file": f, "passed": True})
                except SyntaxError as e:
                    results.append({"file": f, "passed": False, "error": str(e)})
            elif f.endswith(".json") or f.endswith(".yaml"):
                # JSON/YAML 解析检查
                ...
        return {"passed": all(r["passed"] for r in results), "details": results}
    
    def _check_security(self, mutation: dict) -> dict:
        """安全扫描"""
        DANGEROUS_PATTERNS = [
            "rm -rf", "os.remove", "shutil.rmtree",
            "subprocess.call", "os.system",
            "requests.post", "urllib.request",
            "__import__", "eval(", "exec(",
            "open('/etc", "open('~/.ssh",
        ]
        # 扫描所有新增/修改的文件
        ...
    
    def _check_structure(self, mutation: dict) -> dict:
        """结构检查"""
        # 如果是 create_skill，验证 SKILL.md frontmatter
        # 验证文件大小 > 100 bytes
        # 验证目录结构符合规范
        ...
    
    def _check_size(self, mutation: dict) -> dict:
        """大小检查"""
        # 单个文件不超过 500KB
        # 总变异不超过 1MB
        ...
    
    def _check_regression(self, mutation: dict) -> dict:
        """回归测试"""
        # 如果修改了已有 skill 的脚本，尝试 import
        # 检查关键函数签名是否改变
        ...
```

### 7. `scripts/selector.py` (~200行)

选择和应用。

```python
class Selector:
    def __init__(self, workspace_root: str, config: dict = None):
        ...
        self.mode = config.get("mode", "balanced")  # conservative/balanced/aggressive
    
    def select(self, evaluation: dict, hypothesis: dict) -> dict:
        """决定是否采纳"""
        risk = hypothesis.get("risk", "medium")
        confidence = hypothesis.get("confidence", 0.5)
        
        # 决策矩阵
        if evaluation["overall"] == "fail":
            decision = "reject"
        elif risk == "critical":
            decision = "requires_approval"
        elif risk == "high" and confidence < 0.8:
            decision = "requires_approval"
        elif self.mode == "conservative" and risk in ["high", "medium"]:
            decision = "requires_approval"
        elif self.mode == "aggressive" and risk != "critical":
            decision = "auto_approve"
        elif risk == "low" and confidence >= 0.7:
            decision = "auto_approve"
        elif risk == "medium" and confidence >= 0.85:
            decision = "auto_approve"
        else:
            decision = "requires_approval"
        
        return {
            "mutation_id": evaluation["mutation_id"],
            "decision": decision,
            "reason": self._explain_decision(decision, risk, confidence, evaluation)
        }
    
    def apply(self, mutation: dict, force: bool = False) -> dict:
        """应用变异"""
        # 1. 创建快照
        version_id = self.version_manager.create_snapshot(
            f"Pre-mutation: {mutation['id']}"
        )
        
        # 2. 从 staging 复制到目标位置
        for file_info in mutation.get("files_created", []):
            shutil.copy2(file_info["staging_path"], file_info["target_path"])
        
        for file_info in mutation.get("files_modified", []):
            shutil.copy2(file_info["staging_path"], file_info["target_path"])
        
        # 3. 记录
        return {
            "mutation_id": mutation["id"],
            "version_id": version_id,
            "applied_at": datetime.now().isoformat(),
            "observation_until": (datetime.now() + timedelta(hours=self.observation_period)).isoformat()
        }
    
    def rollback(self, version_id: str) -> dict:
        """回滚"""
        success = self.version_manager.restore_snapshot(version_id)
        return {
            "version_id": version_id,
            "success": success,
            "rolled_back_at": datetime.now().isoformat()
        }
```

### 8. `SKILL.md` (~500行)

完整的 SKILL.md 指令文件。

```yaml
---
name: evolution-engine
description: "AI Agent 自我进化引擎。自动感知交互中的改进机会，生成优化方案，在安全沙箱中验证后应用。支持 create_skill/modify_skill/modify_prompt 等多种进化动作。使用方式：说'进化一下'、'反思一下'、'检查进化状态'。"
metadata: {"openclaw": {"requires": {"bins": ["python3"]}}}
---
```

SKILL.md 正文结构：

```
# Evolution Engine — 自我进化引擎

## 概述
（什么是什么，解决什么问题）

## 使用方式
### 触发进化
- 用户说"进化一下" → 执行完整进化循环
- 用户说"反思一下" → 只执行 observe + reflect
- 用户说"检查进化状态" → 显示 status
- 用户说"回滚到版本 X" → 执行 rollback

### 手动审批
当有需要审批的假设时，通知用户并等待确认。

### 进化模式切换
- 用户说"保守进化" → conservative
- 用户说"均衡进化" → balanced（默认）
- 用户说"激进进化" → aggressive

## 进化流程（详细步骤）

### Step 1: 感知（Observe）
执行命令：
```bash
python3 {baseDir}/scripts/evolution_cli.py observe --date $(date +%Y-%m-%d)
```
读取输出 JSON，提取信号摘要报告给用户。

### Step 2: 反思（Reflect）
...

### Step 3: 变异（Mutate）
...

### Step 4: 评估（Evaluate）
...

### Step 5: 选择与应用（Select & Apply）
...

### Step 6: 记录（Record）
...

## 安全规则
（硬性红线列表）

## 进化模式配置
（三种模式的详细说明）

## 交互协议
（agent 应如何与用户沟通进化事项）

## 故障处理
（出问题怎么办）
```

### 9. 配置文件 `evolution/config.yaml` (默认)

```yaml
# Evolution Engine 配置
version: "1.0"

mode: balanced  # conservative / balanced / aggressive

# 进化模式参数
modes:
  conservative:
    auto_approve_risk_levels: ["low"]
    observation_period_hours: 72
    max_mutations_per_day: 1
    min_confidence_for_auto: 0.9
  balanced:
    auto_approve_risk_levels: ["low", "medium"]
    observation_period_hours: 24
    max_mutations_per_day: 3
    min_confidence_for_auto: 0.85
  aggressive:
    auto_approve_risk_levels: ["low", "medium"]
    observation_period_hours: 4
    max_mutations_per_day: 5
    min_confidence_for_auto: 0.7

# 安全配置
safety:
  protected_files:
    - "SOUL.md"
    - "USER.md"
    - "IDENTITY.md"
    - "openclaw.json"
  protected_dirs:
    - "/etc"
    - "~/.ssh"
  max_file_size_kb: 500
  max_total_mutation_size_kb: 1024
  require_approval_for_delete: true

# 版本管理
versions:
  keep_days: 30
  max_snapshots: 50

# 通知配置
notification:
  channel: "current"  # 在当前会话通知
  quiet_hours: ["23:00-08:00"]  # 安静时段不通知
```

---

## 编码规范

1. **Python 3.12+**，type hints 全覆盖
2. **不依赖第三方库**，只用标准库（json, os, argparse, ast, shutil, tarfile, datetime, enum, dataclasses, hashlib, re, glob, tempfile, logging）
3. 每个文件独立可运行（通过 `if __name__ == "__main__"` 入口）
4. 所有文件操作先写临时文件再 rename（原子性）
5. 所有 JSON 输出用 `json.dumps(data, ensure_ascii=False, indent=2)`
6. 日志用 logging 模块，不用 print（除了 CLI 的最终输出）
7. 错误处理：每个外部操作（文件IO等）都有 try/except，错误信息具体

## 验收标准

1. `python3 -c "import ast; ast.parse(open('scripts/evolution_cli.py').read())"` 对所有 .py 文件通过
2. `python3 scripts/evolution_cli.py status` 正常运行
3. `python3 scripts/evolution_cli.py observe` 能读取 memory 日志并输出 JSON
4. 完整循环 `run-full-cycle` 不报错（即使没有信号也能正常完成）
5. 版本快照创建和回滚正常工作
6. 安全扫描能检测到危险模式

---

## 不要做的事

1. 不要修改 evolution-engine/ 目录外的任何文件
2. 不要安装任何第三方包
3. 不要写测试文件（我会在验收时手动测试）
4. 不要写 setup.py 或 __init__.py
5. 不要用 f-string 以外的字符串格式化方式

---

*SPEC 结束。Codex 按此实现。*
