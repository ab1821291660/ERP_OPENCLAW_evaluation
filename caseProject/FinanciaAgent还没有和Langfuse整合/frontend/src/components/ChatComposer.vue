<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({ modelValue: String, disabled: Boolean, stopping: Boolean, loading: Boolean })
const emit = defineEmits(['update:modelValue', 'send', 'stop'])
const textarea = ref(null)
watch(() => props.modelValue, async () => {
  await nextTick()
  if (textarea.value) {
    textarea.value.style.height = 'auto'
    textarea.value.style.height = Math.min(textarea.value.scrollHeight, 160) + 'px'
  }
})
function keydown(event) {
  // 输入法确认候选字时的 Enter 不应提交问题。
  if (event.isComposing || event.keyCode === 229) return
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (!props.disabled && !props.loading && props.modelValue.trim()) emit('send')
  }
}
</script>

<template>
  <div class="composer-wrap">
    <div class="composer">
      <textarea
        ref="textarea" :value="modelValue" rows="1"
        placeholder="输入公司、年份和财务分析需求，无须报告编号…"
        :disabled="loading"
        @input="emit('update:modelValue', $event.target.value)" @keydown="keydown"
      ></textarea>
      <button v-if="disabled" class="send-button stop" title="停止生成"
        :disabled="stopping" @click="emit('stop')">■</button>
      <button v-else class="send-button" title="发送"
        :disabled="loading || !modelValue.trim()" @click="emit('send')">↑</button>
    </div>
    <p>Enter 发送 · Shift + Enter 换行 · 财务计算结果请结合原始证据核验</p>
  </div>
</template>
