<script setup>
import { computed, ref } from 'vue'

const agentLabels = { main: '主 Agent', researcher: '研究员', reviewer: '复核员', subagent: '子 Agent' }
const props = defineProps({ message: { type: Object, required: true } })
const expanded = ref(false)
const label = computed(() => {
  const names = {
    safe_calculate: '财务计算',
    search_financial_reports: '检索财务报告',
    find_finqa_reports: '按公司和年份定位报告',
    get_financial_report: '读取财务报告',
    task: '子 Agent 任务',
  }
  return names[props.message.name] || props.message.name || '工具调用'
})
const statusText = computed(() =>
  ({ running: '执行中', error: '失败', cancelled: '已停止', incomplete: '未完成' })[
    props.message.status
  ] || '已完成',
)
</script>

<template>
  <div class="tool-card" :class="message.status">
    <button class="tool-summary"  :aria-expanded="expanded" @click="expanded = !expanded">
      <span class="tool-icon">⌁</span>
      <span><strong>{{ label }}</strong><small>{{ agentLabels[message.agent] || message.agent || 'Agent 工具' }}</small></span>
      <span class="tool-status"><i></i>{{ statusText }}</span>
      <span class="chevron" :class="{ open: expanded }">⌄</span>
    </button>
    <div v-if="expanded" class="tool-detail">
      <div v-if="message.arguments"><label>输入参数</label><pre>{{ message.arguments }}</pre></div>
      <div v-if="message.content"><label>工具输出</label><pre>{{ message.content }}</pre></div>
      <p v-if="!message.arguments && !message.content" class="empty-note">等待工具返回结果…</p>
    </div>
  </div>
</template>
