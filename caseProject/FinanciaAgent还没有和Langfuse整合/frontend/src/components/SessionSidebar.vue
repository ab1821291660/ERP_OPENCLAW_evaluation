<script setup>
defineProps({ sessions: Array, currentId: String, disabled: Boolean })
const emit = defineEmits(['create', 'select', 'rename', 'remove', 'clear'])

function rename(item) {
  const value = window.prompt('修改会话标题', item.title)
  if (value?.trim()) emit('rename', item.session_id, value.trim())
}

function remove(item) {
  if (window.confirm(`确定删除会话“${item.title}”吗？`)) emit('remove', item.session_id)
}

function clearHistory() {
  if (window.confirm('确定清空全部历史会话吗？这会删除本地会话目录和 Agent 运行历史，财务数据不会被删除。')) {
    emit('clear')
  }
}

function relativeTime(value) {
  const time = new Date(value).getTime()
  const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.floor(minutes / 60)} 小时前`
  return new Date(value).toLocaleDateString('zh-CN')
}
</script>

<template>
  <aside class="session-sidebar">
    <div class="sidebar-heading">
      <div><span class="eyebrow">WORKSPACE</span><h2>研究会话</h2></div>
      <button class="icon-button" title="新建会话" :disabled="disabled" @click="emit('create')">＋</button>
    </div>
    <button class="new-session" :disabled="disabled" @click="emit('create')">
      <span>✦</span> 新建分析会话
    </button>
    <button
      class="clear-history"
      :disabled="disabled || !sessions?.length"
      @click="clearHistory"
    >
      <span>🗑</span> 清空历史会话 <em v-if="sessions?.length">({{ sessions.length }})</em>
    </button>
    <div class="session-list">
      <p v-if="!sessions?.length" class="empty-note">还没有历史会话</p>
      <article
        v-for="item in sessions"
        :key="item.session_id"
        class="session-item"
        :class="{ active: item.session_id === currentId }"
        @click="emit('select', item.session_id)"
      >
        <div class="session-title"><span>◫</span><strong>{{ item.title }}</strong></div>
        <p>{{ item.last_message_preview || '等待开始分析' }}</p>
        <footer>
          <time>{{ relativeTime(item.updated_at) }}</time>
          <span class="session-actions">
            <button class="session-rename" title="重命名会话" :disabled="disabled" @click.stop="rename(item)">✎</button>
            <button class="session-delete" title="删除此会话" :disabled="disabled" @click.stop="remove(item)">🗑 删除</button>
          </span>
        </footer>
      </article>
    </div>
  </aside>
</template>
