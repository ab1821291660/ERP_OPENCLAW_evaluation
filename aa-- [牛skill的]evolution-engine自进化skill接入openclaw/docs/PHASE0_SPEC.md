# Phase 0: 评测基础设施 — Codex 实现 SPEC

> 实现 Phase 0，为后续所有进化提供地基
> 日期：2026-04-20 | 预估：~1500 行

---

## 目标

搭建评测框架和数据管道，使得：
1. 能对任意 SKILL.md 生成合成评测集
2. 能用 LLM-as-Judge 对 skill 输出做多维度评分
3. 能通过三重门控（约束+回归+安全）决定变体是否可部署
4. 能跑一个完整的最小闭环验证

## 目录结构

在现有 `skills/evolution-engine/` 下新增：

```
skills/evolution-engine/
├── scripts/
│   ├── evolution_cli.py          # 已有，需扩展子命令
│   ├── observer.py               # 已有
│   ├── reflector.py              # 已有
│   ├── mutator.py                # 已有
│   ├── evaluator.py              # 已有
│   ├── selector.py               # 已有
│   ├── version_manager.py        # 已有
│   │
│   ├── dataset_builder.py        # [新] 合成评测集生成
│   ├── llm_judge.py              # [新] LLM-as-Judge 评分
│   ├── gate_system.py            # [新] 三重门控
│   ├── eval_runner.py            # [新] 评测运行器
│   └── trace_collector.py        # [新] 执行轨迹收集
│
├── data/                         # [新] 评测数据
│   ├── rubrics/                  # 评分规则
│   │   └── default.json          # 默认评分标准
│   └── datasets/                 # 评测集存储
│       └── .gitkeep
│
└── references/
    └── EVAL_GUIDE.md             # [新] 评测使用指南
```

数据目录：
```
evolution/
├── eval/                         # [新] 评测结果
│   ├── baselines/                # baseline 分数
│   └── runs/                     # 每次评测的完整记录
```

---

## 文件详细规格

### 1. `scripts/dataset_builder.py` (~300行)

从 SKILL.md 自动生成评测集。

```python
class DatasetBuilder:
    """从 SKILL.md 生成合成评测集"""
    
    def __init__(self, skill_path: str):
        self.skill_path = skill_path
        self.skill_content = self._read_skill()
    
    def generate_dataset(
        self,
        num_cases: int = 20,
        output_path: str = None,
        seed: int = 42
    ) -> dict:
        """
        生成评测集
        
        流程：
        1. 解析 SKILL.md 的 frontmatter（name, description）
        2. 提取 skill 的核心功能描述
        3. 生成 num_cases 个 (task_input, expected_behavior) 对
        4. 自动分割为 train(60%) / val(20%) / holdout(20%)
        5. 保存为 JSONL 格式
        """
        ...
    
    def _parse_skill(self) -> dict:
        """解析 SKILL.md 的 frontmatter 和正文结构"""
        # 提取 name, description, 正文中的 When to Use / Procedure / Pitfalls
        ...
    
    def _generate_cases(self, skill_info: dict, n: int) -> list:
        """
        基于 skill 信息生成测试用例
        
        不调 LLM！用模板+规则生成，零成本。
        
        策略：
        - 读取 SKILL.md 的 "When to Use" 段落 → 生成正面触发用例
        - 读取 "Procedure" 段落 → 生成流程正确性用例
        - 读取 "Pitfalls" 段落 → 生成边界/异常用例
        - 自动生成一些"不应该触发"的反面用例
        
        每个用例格式：
        {
            "id": "TC001",
            "task_input": "用户请求描述",
            "expected_behavior": "期望的 agent 行为描述（rubric）",
            "category": "trigger_positive | procedure | boundary | negative",
            "difficulty": "easy | medium | hard",
            "source": "synthetic"
        }
        """
        ...
    
    def _split_dataset(self, cases: list, seed: int) -> dict:
        """分割为 train/val/holdout"""
        ...
    
    def load_dataset(self, path: str) -> dict:
        """加载已有评测集"""
        ...
```

输出格式（JSONL 文件）：
```json
{
    "skill_name": "weather",
    "generated_at": "2026-04-20T23:45:00",
    "total_cases": 20,
    "splits": {
        "train": ["TC001", "TC002", ...],
        "val": ["TC013", "TC014", ...],
        "holdout": ["TC017", "TC018", ...]
    },
    "cases": [
        {
            "id": "TC001",
            "task_input": "今天北京天气怎么样",
            "expected_behavior": "agent 应调用天气查询工具，返回北京的当前天气信息，包括温度、天气状况",
            "category": "trigger_positive",
            "difficulty": "easy",
            "source": "synthetic"
        }
    ]
}
```

CLI 用法：
```bash
python3 dataset_builder.py --skill-path ~/workspace/skills/weather/SKILL.md --num-cases 20 --output evolution/eval/datasets/weather.json
```

### 2. `scripts/llm_judge.py` (~350行)

LLM-as-Judge 多维度评分。**关键：支持两种模式——有 LLM API 时用 LLM，没有时用规则评分。**

```python
class LLMJudge:
    """多维度评分系统"""
    
    DIMENSIONS = {
        "correctness": {
            "weight": 0.4,
            "description": "输出是否完成了任务目标"
        },
        "efficiency": {
            "weight": 0.2,
            "description": "是否用最少的步骤完成任务"
        },
        "safety": {
            "weight": 0.2,
            "description": "是否遵守所有安全规则"
        },
        "consistency": {
            "weight": 0.2,
            "description": "输出风格是否一致"
        }
    }
    
    def __init__(self, mode: str = "auto"):
        """
        mode:
        - "llm": 调用 LLM API 做评分（需要 API key）
        - "rule": 纯规则评分（零成本，不用 API）
        - "auto": 优先 LLM，不可用则降级为 rule
        """
        self.mode = self._resolve_mode(mode)
    
    def score(
        self,
        task_input: str,
        agent_output: str,
        expected_behavior: str,
        rubric: dict = None
    ) -> dict:
        """
        评分单个输出
        
        返回：
        {
            "total_score": 0.82,
            "dimensions": {
                "correctness": {"score": 0.9, "reason": "..."},
                "efficiency": {"score": 0.7, "reason": "..."},
                "safety": {"score": 1.0, "reason": "..."},
                "consistency": {"score": 0.8, "reason": "..."}
            },
            "mode": "rule",
            "passed": true
        }
        """
        ...
    
    def score_batch(
        self,
        cases: list,
        outputs: list,
        baseline_scores: dict = None
    ) -> dict:
        """
        批量评分
        
        如果提供 baseline_scores，自动做对比分析
        """
        ...
    
    def _score_with_rules(
        self,
        task_input: str,
        agent_output: str,
        expected_behavior: str
    ) -> dict:
        """
        纯规则评分（零成本模式）
        
        规则：
        - correctness: 检查输出是否包含 expected_behavior 中的关键词
        - efficiency: 输出长度是否合理（不过短也不过长）
        - safety: 检查是否包含危险操作关键词
        - consistency: 检查格式是否一致
        """
        ...
    
    def _score_with_llm(
        self,
        task_input: str,
        agent_output: str,
        expected_behavior: str,
        rubric: dict = None
    ) -> dict:
        """
        LLM 评分（需要 API）
        
        通过 exec 调用 curl 或 python requests 调用 LLM API
        使用环境变量中的 API key
        """
        # 构造评分 prompt
        # 解析 LLM 返回的 JSON 评分
        ...
```

CLI 用法：
```bash
# 对单个输出评分
python3 llm_judge.py score --task "今天天气" --output "北京今天晴..." --expected "返回天气信息" --mode rule

# 批量评分
python3 llm_judge.py batch --dataset evolution/eval/datasets/weather.json --outputs evolution/eval/runs/run001/outputs.json --mode rule
```

### 3. `scripts/gate_system.py` (~200行)

三重门控系统。

```python
class GateSystem:
    """三重门控：约束 + 回归 + 安全"""
    
    def __init__(self, config: dict = None):
        self.config = config or self._default_config()
    
    def run_all_gates(
        self,
        variant_content: str,
        baseline_content: str,
        variant_scores: dict,
        baseline_scores: dict,
        target_type: str = "skill"  # skill | prompt | config
    ) -> dict:
        """
        运行所有门控
        
        返回：
        {
            "passed": true,
            "gates": {
                "constraint": {"passed": true, "details": {...}},
                "regression": {"passed": true, "details": {...}},
                "safety": {"passed": true, "details": {...}}
            },
            "recommendation": "approve" | "reject" | "needs_review"
        }
        """
        results = {
            "constraint": self.constraint_gate(variant_content, target_type),
            "regression": self.regression_gate(variant_scores, baseline_scores),
            "safety": self.safety_gate(variant_content, baseline_content),
        }
        
        all_passed = all(r["passed"] for r in results.values())
        
        return {
            "passed": all_passed,
            "gates": results,
            "recommendation": "approve" if all_passed else "reject"
        }
    
    def constraint_gate(self, content: str, target_type: str) -> dict:
        """
        约束门控
        
        检查项：
        - SKILL.md ≤ 15KB
        - frontmatter 格式正确（name + description）
        - description ≤ 1024 字符
        - 无非法字符或编码问题
        - 文件非空
        """
        ...
    
    def regression_gate(
        self,
        variant_scores: dict,
        baseline_scores: dict,
        tolerance: float = 0.02
    ) -> dict:
        """
        回归门控
        
        检查项：
        - variant 的总分不能比 baseline 低超过 tolerance（默认 2%）
        - 在 holdout 集上不能有任何维度退步超过 5%
        - 如果没有 baseline 数据，默认通过（首次运行）
        """
        ...
    
    def safety_gate(self, variant_content: str, baseline_content: str) -> dict:
        """
        安全门控
        
        检查项：
        - 无危险代码模式（rm -rf, os.system, eval 等）
        - 不包含凭证/密钥泄露
        - 不修改不可变核心（检查是否包含 evolution:freeze 标记的内容）
        - Python 文件通过 ast.parse
        - 语义保持：变体不能完全改变原内容的核心意图
          （简单实现：检查 name/description 字段是否被修改）
        """
        ...
```

CLI 用法：
```bash
# 对一个变体运行门控
python3 gate_system.py check --variant evolution/staging/H001/SKILL.md --baseline skills/weather/SKILL.md --scores evolution/eval/runs/run001/scores.json --baseline-scores evolution/eval/baselines/weather_baseline.json
```

### 4. `scripts/eval_runner.py` (~250行)

评测运行器，串联以上所有组件。

```python
class EvalRunner:
    """评测运行器"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
    
    def run_baseline(
        self,
        skill_path: str,
        num_cases: int = 20,
        judge_mode: str = "auto"
    ) -> dict:
        """
        对一个 skill 跑 baseline 评测
        
        完整流程：
        1. 用 DatasetBuilder 生成评测集
        2. 模拟执行每个测试用例（基于 SKILL.md 内容生成模拟输出）
        3. 用 LLMJudge 评分
        4. 保存 baseline 结果
        
        返回：
        {
            "skill_name": "weather",
            "total_score": 0.78,
            "dimensions": {...},
            "num_cases": 20,
            "judge_mode": "rule",
            "saved_to": "evolution/eval/baselines/weather_baseline.json"
        }
        """
        ...
    
    def run_evaluation(
        self,
        skill_path: str,
        variant_path: str,
        dataset_path: str = None,
        baseline_path: str = None,
        judge_mode: str = "auto"
    ) -> dict:
        """
        评测一个变体
        
        完整流程：
        1. 加载评测集（如果没有则用 skill 的 baseline 集）
        2. 用变体内容模拟执行每个测试用例
        3. 用 LLMJudge 评分
        4. 加载 baseline 做对比
        5. 运行三重门控
        6. 保存评测结果
        """
        ...
    
    def _simulate_execution(
        self,
        skill_content: str,
        task_input: str
    ) -> str:
        """
        模拟 skill 执行（不真正跑 skill，用规则生成模拟输出）
        
        基于 SKILL.md 的 Procedure 段落，生成模拟的执行步骤和输出。
        这不是真正的 skill 执行，而是基于 skill 指令生成预期行为描述。
        """
        ...
    
    def compare_runs(self, run_a_path: str, run_b_path: str) -> dict:
        """对比两次评测结果"""
        ...
```

CLI 用法：
```bash
# 跑 baseline
python3 eval_runner.py baseline --skill-path skills/weather/SKILL.md

# 评测变体
python3 eval_runner.py evaluate --skill-path skills/weather/SKILL.md --variant-path evolution/staging/H001/SKILL.md --baseline-path evolution/eval/baselines/weather_baseline.json

# 对比两次运行
python3 eval_runner.py compare --run-a evolution/eval/runs/baseline_001.json --run-b evolution/eval/runs/variant_001.json
```

### 5. `scripts/trace_collector.py` (~150行)

执行轨迹收集。

```python
class TraceCollector:
    """收集和存储 skill 执行轨迹"""
    
    def __init__(self, workspace_root: str):
        self.trace_dir = os.path.join(workspace_root, "evolution", "traces")
    
    def record_trace(
        self,
        skill_name: str,
        task_input: str,
        tool_calls: list,
        output: str,
        success: bool,
        user_feedback: str = None,
        duration_ms: int = None
    ) -> str:
        """
        记录一次执行轨迹
        
        返回 trace_id
        """
        ...
    
    def get_traces(
        self,
        skill_name: str = None,
        success_only: bool = False,
        failure_only: bool = False,
        limit: int = 100
    ) -> list:
        """查询轨迹"""
        ...
    
    def get_skill_stats(self, skill_name: str, window_days: int = 7) -> dict:
        """
        获取 skill 的统计信息
        
        返回：
        {
            "skill_name": "weather",
            "window_days": 7,
            "total_calls": 23,
            "success_rate": 0.87,
            "avg_duration_ms": 3200,
            "common_failures": ["timeout", "wrong_city"],
            "improvement_potential": 0.13
        }
        """
        ...
```

### 6. `data/rubrics/default.json` (~50行)

```json
{
    "dimensions": {
        "correctness": {
            "weight": 0.4,
            "description": "输出是否正确完成了任务目标",
            "scoring_guide": {
                "1.0": "完全正确，所有要求都满足",
                "0.8": "基本正确，小瑕疵",
                "0.6": "部分正确，有遗漏",
                "0.4": "方向对但执行有问题",
                "0.2": "大部分错误",
                "0.0": "完全错误或无输出"
            }
        },
        "efficiency": {
            "weight": 0.2,
            "description": "是否用最少的步骤完成任务",
            "scoring_guide": {
                "1.0": "最短路径完成",
                "0.7": "多了一两步但合理",
                "0.4": "明显绕路",
                "0.0": "大量冗余操作"
            }
        },
        "safety": {
            "weight": 0.2,
            "description": "是否遵守所有安全规则",
            "scoring_guide": {
                "1.0": "完全安全",
                "0.0": "违反安全规则"
            }
        },
        "consistency": {
            "weight": 0.2,
            "description": "输出风格和格式是否一致",
            "scoring_guide": {
                "1.0": "格式完美一致",
                "0.7": "轻微不一致",
                "0.4": "格式混乱",
                "0.0": "完全不一致"
            }
        }
    },
    "pass_threshold": 0.7,
    "regression_tolerance": 0.02
}
```

### 7. 扩展 `evolution_cli.py`

在现有 CLI 中添加子命令：

```bash
# Phase 0 新增子命令
python3 evolution_cli.py build-dataset --skill-path <path> [--num-cases 20]
python3 evolution_cli.py eval-baseline --skill-path <path>
python3 evolution_cli.py eval-variant --skill-path <path> --variant-path <path>
python3 evolution_cli.py eval-compare --run-a <path> --run-b <path>
python3 evolution_cli.py skill-stats --skill-name <name>
```

---

## 编码规范

同之前的 SPEC：
- Python 3.12+，type hints
- 只用标准库（json, os, argparse, ast, re, hashlib, datetime, enum, dataclasses, glob, tempfile, logging, random, math, statistics）
- 不依赖第三方库
- 所有文件操作原子性
- JSON 输出用 ensure_ascii=False, indent=2

## 验收标准

1. 所有新 .py 文件通过 ast.parse
2. `python3 evolution_cli.py build-dataset --skill-path skills/weather/SKILL.md` 能生成评测集
3. `python3 evolution_cli.py eval-baseline --skill-path skills/weather/SKILL.md` 能跑 baseline 评分
4. gate_system.py 的三个门控都能正常工作
5. 评测结果保存到 evolution/eval/ 目录
6. CLI 新子命令不破坏已有的 observe/reflect/mutate/evaluate/apply/status

## 不要做的事

1. 不调用任何外部 LLM API（rule 模式为主，LLM 模式只留接口）
2. 不修改已有的 7 个 .py 文件的已有功能
3. 不安装第三方包
4. 不做真正的 skill 执行（只做模拟）

---

*Phase 0 SPEC 结束。Codex 按此实现。*
