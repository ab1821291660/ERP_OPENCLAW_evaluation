<script setup>
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import ToolMessageCard from './ToolMessageCard.vue'

const props = defineProps({ message: Object })
const labels = { main: '财务 Agent', researcher: '研究员 researcher', reviewer: '复核员 reviewer', subagent: '子 Agent' }
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
const rendered = computed(() => DOMPurify.sanitize(markdown.render(props.message.content || '')))
</script>

<template>
  <ToolMessageCard v-if="message.role === 'tool'" :message="message" />
  <article v-else class="chat-message" :class="message.role">
    <div class="avatar">{{ message.role === 'human' ? '你' : 'FQ' }}</div>
    <div class="message-body">
      <header>
        <strong>{{ message.role === 'human' ? '你' : labels[message.agent] || message.agent || '财务 Agent' }}</strong>
        <span v-if="message.streaming" class="stream-indicator"><i></i> 正在生成</span>
      </header>
      <div v-if="message.role === 'human'" class="human-content">{{ message.content }}</div>
      <div v-else class="markdown-body" v-html="rendered"></div>
    </div>
  </article>
</template>
