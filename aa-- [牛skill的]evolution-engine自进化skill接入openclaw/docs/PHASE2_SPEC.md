# Phase 2: System Prompt 进化 — Codex 实现 SPEC

> 反射式文本进化，优化 SOUL.md / AGENTS.md 中的行为指导
> 日期：2026-04-21 | 预估：~600 行

---

## 目标

让 SOUL.md / AGENTS.md / TOOLS.md 中的行为指导文本可以自动进化，评测通过后提交审批。

## 核心机制：反射式文本进化

不是随机变异，而是：
1. 读执行轨迹 → 找到失败案例
2. 理解"这段指导为什么导致 agent 犯错了"
3. 精确修改导致失败的那部分指导
4. 评测验证修改是否有效

## 新增文件

```
skills/evolution-engine/scripts/
├── prompt_evolver.py         # [新] 反射式 Prompt 进化
└── prompt_tester.py          # [新] Prompt 行为测试
```

---

### `scripts/prompt_evolver.py` (~400行)

```python
class PromptEvolver:
    """反射式文本进化器"""
    
    EVOLVABLE_FILES = {
        "SOUL.md": {
            "frozen_markers": ["不泄露隐私", "安全", "边界"],
            "max_change_pct": 0.3  # 单次最多修改30%内容
        },
        "AGENTS.md": {
            "frozen_markers": ["evolution:freeze", "安全策略", "权限控制"],
            "max_change_pct": 0.2
        },
        "TOOLS.md": {
            "frozen_markers": [],
            "max_change_pct": 0.3
        }
    }
    
    def __init__(self, workspace_root: str):
        ...
    
    def analyze_failures(
        self,
        target_file: str,
        traces: list,  # 执行轨迹
        eval_scores: dict = None
    ) -> dict:
        """
        分析失败轨迹，找出导致失败的 prompt 片段
        
        策略：
        1. 读取 target_file 内容
        2. 将内容分段（按 ## 或 --- 分）
        3. 对每个失败案例，定位最相关的段
        4. 分析为什么这段指导导致了失败
        5. 返回改进建议
        
        返回：
        {
            "target_file": "AGENTS.md",
            "failure_analysis": [
                {
                    "trace_id": "T001",
                    "task": "用户请求...",
                    "failure": "agent 做了X但应该做Y",
                    "relevant_section": "## 群聊规则",
                    "root_cause": "这条规则说'有价值时说话'但没有定义什么是'有价值'",
                    "suggested_fix": "增加'有价值'的具体定义..."
                }
            ],
            "improvement_potential": 0.6
        }
        """
        ...
    
    def generate_variant(
        self,
        target_file: str,
        failure_analysis: dict
    ) -> dict:
        """
        基于失败分析生成变体
        
        规则：
        - 不修改 frozen_markers 标记的内容
        - 单次修改不超过 max_change_pct
        - 只修改与失败相关的段
        - 保持整体结构不变
        - 修改写入 staging，不改原文件
        
        返回：
        {
            "variant_path": "evolution/staging/SOUL_variant_001.md",
            "changes": [
                {
                    "section": "## 群聊规则",
                    "type": "append",
                    "content": "新增定义..."
                }
            ],
            "change_pct": 0.05
        }
        """
        ...
    
    def _is_frozen(self, content: str, section: str) -> bool:
        """检查内容是否被标记为不可修改"""
        ...
    
    def _split_sections(self, content: str) -> list:
        """按 markdown 标题分段"""
        ...
```

### `scripts/prompt_tester.py` (~200行)

```python
class PromptTester:
    """测试 prompt 变体的行为变化"""
    
    def __init__(self, workspace_root: str):
        ...
    
    def test_variant(
        self,
        target_file: str,
        variant_path: str,
        test_scenarios: list = None  # 如果为None，自动生成
    ) -> dict:
        """
        测试变体在不同场景下的行为
        
        策略：
        1. 从 target_file 生成测试场景（基于其内容中的规则/指导）
        2. 用 baseline 版本生成预期行为
        3. 用 variant 版本生成实际行为
        4. 用 LLMJudge 对比评分
        
        不调真 LLM！用规则模拟。
        
        返回：
        {
            "num_scenarios": 10,
            "baseline_scores": {...},
            "variant_scores": {...},
            "delta": {...},
            "regression_detected": false
        }
        """
        ...
    
    def _generate_scenarios(self, content: str) -> list:
        """
        从 prompt 内容中提取可测试的场景
        
        例如 AGENTS.md 中有"群聊中不主动说话" → 生成：
        - "群聊中有人讨论技术问题" → 应该不主动插话
        - "群聊中有人@你" → 应该回复
        - "群聊中有人问数据问题" → 应该判断是否有价值再决定
        """
        ...
```

### 扩展 CLI

```bash
python3 evolution_cli.py evolve-prompt --target SOUL.md [--traces-path <path>]
python3 evolution_cli.py test-prompt --target SOUL.md --variant <path>
```

---

## 验收标准

1. 所有新 .py 通过 ast.parse
2. analyze_failures 能分析轨迹并定位相关 prompt 段落
3. generate_variant 能生成遵循 frozen 标记的变体
4. test_prompt 能对比 baseline 和 variant 的行为差异
5. 单次修改不超过配置的最大百分比
