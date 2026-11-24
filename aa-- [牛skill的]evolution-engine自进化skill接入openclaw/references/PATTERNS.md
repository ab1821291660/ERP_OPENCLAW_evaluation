# 常见进化模式库

## 模式 1: Skill 缺失 → 自动创建

**触发条件**：用户反复请求某类任务，但无 skill 覆盖
**动作**：create_skill
**风险**：low
**示例**：用户频繁要求"分析 CSV 数据"，无对应 skill → 创建 data-analyzer skill

## 模式 2: Skill 质量 → 定向修复

**触发条件**：skill 输出不稳定，用户频繁纠正
**动作**：modify_skill_md（patch）
**风险**：medium
**示例**：yinyo-writer 的某个检查项遗漏 → patch 补充规则

## 模式 3: 流程优化 → 创建常驻指令

**触发条件**：agent 反复执行相同的多步骤操作
**动作**：create_standing_order
**风险**：medium
**示例**：每天检查邮件 → 自动创建邮件巡检常驻指令

## 模式 4: Prompt 调优

**触发条件**：agent 在特定场景下表现不佳
**动作**：modify_agents / modify_soul
**风险**：high（需审批）
**示例**：agent 在群聊中过于活跃 → 调整 AGENTS.md 中的群聊规则

## 模式 5: 配置优化

**触发条件**：检测到配置不合理导致效率低下
**动作**：modify_config
**风险**：critical（必须审批）
**示例**：skill description 过长导致 token 浪费 → 精简 description
