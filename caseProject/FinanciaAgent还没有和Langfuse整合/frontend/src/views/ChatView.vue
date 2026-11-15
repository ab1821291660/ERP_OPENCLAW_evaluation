<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import ChatComposer from '../components/ChatComposer.vue'
import ChatMessage from '../components/ChatMessage.vue'
import SessionSidebar from '../components/SessionSidebar.vue'
import { useChatStore } from '../stores/chat'

const chat = useChatStore()
const draft = ref('')
const messageList = ref(null)
const showHistory = ref(false)
const labels = { researcher: '研究员', reviewer: '复核员', subagent: '子 Agent' }
watch(() => chat.messages.map((item) => item.id + ':' + (item.content?.length || 0)).join('|'), async () => {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
})
onMounted(() => action(() => chat.loadSessions()))
async function action(callback) {
  try { await callback() }
  catch (error) { chat.error = error.message || '操作失败，请重试' }
}
async function send() {
  if (!draft.value.trim() || chat.loadingHistory || chat.streaming) return
  const content = draft.value
  draft.value = ''
  await action(() => chat.sendMessage(content))
}
async function select(sessionId) {
  showHistory.value = false
  await action(() => chat.selectSession(sessionId))
}
</script>

<template>
  <div class="chat-layout" :class="{ 'sidebar-open': showHistory }">
    <SessionSidebar
      :sessions="chat.sessions" :current-id="chat.currentSessionId"
      :disabled="chat.streaming || chat.loadingHistory"
      @create="action(() => chat.createSession())"
      @select="select"
      @rename="(id, title) => action(() => chat.renameSession(id, title))"
      @remove="(id) => action(() => chat.removeSession(id))"
      @clear="action(() => chat.clearAllSessions())"
    />
    <section class="conversation">
      <header class="conversation-header">
        <div>
          <span class="status-dot"></span>
          <div><h1>{{ chat.currentSession?.title || '新的财务分析' }}</h1><p>DeepAgents · 财务证据检索 · 独立复核</p></div>
        </div>
        <button class="mobile-history-toggle" @click="showHistory = !showHistory">历史会话</button>
      </header>
      <div v-if="chat.streaming" class="agent-status-list" role="status">
        {{ chat.stopping ? '正在停止生成…' : 'Agent 正在分析…' }}
        <span v-for="(status, name) in chat.agents" :key="name">
          {{ labels[name] || name }}：{{ status === 'started' ? '执行中' : status === 'completed' ? '已完成' : status }}
        </span>
      </div>
      <div ref="messageList" class="message-list" aria-live="polite">
        <div v-if="chat.loadingHistory" class="empty-note">正在加载会话…</div>
        <div v-else-if="!chat.messages.length" class="welcome-panel">
          <span class="welcome-mark">FQ</span>
          <p class="eyebrow">FINANCIAL RESEARCH AGENT</p>
          <h2>从财报数字中，找到可信答案</h2>
          <p>输入公司、年份和分析需求，Agent 会查询 FinQA 证据、计算并按要求独立复核。执行过程实时展示。</p>
          <div class="suggestion-grid">
            <button @click="draft = '请查询 Apple 2014 年的固定资产净额和2013年的可比数值，列出原始数据、单位和出处，计算同比增长率，并独立复核。'">固定资产增长率<span>自动定位 Apple 报告 →</span></button>
            <button @click="draft = '请查询 Apple 2014 年长期债务和经营活动产生的现金，列出原始证据，计算长期债务占经营现金流的比例，并独立复核。'">债务与现金流<span>检查公式与单位 →</span></button>
            <button @click="draft = '请说明财务分析中的同比增长率公式，并举一个简单的数字例子。'">了解分析方法<span>查看公式与计算过程 →</span></button>
          </div>
        </div>
        <ChatMessage v-for="message in chat.messages" :key="message.id" :message="message" />
        <div v-if="chat.notice" class="notice-banner" role="status">{{ chat.notice }}</div>
        <div v-if="chat.error" class="error-banner" role="alert">{{ chat.error }}</div>
      </div>
      <ChatComposer v-model="draft" :disabled="chat.streaming" :stopping="chat.stopping"
        :loading="chat.loadingHistory" @send="send" @stop="chat.stopStream" />
    </section>
  </div>
</template>
