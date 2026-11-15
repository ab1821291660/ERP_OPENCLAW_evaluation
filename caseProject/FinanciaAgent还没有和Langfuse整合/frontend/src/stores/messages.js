// 刷新后的历史来自 Checkpointer；未保存的临时子 Agent 过程不在这里伪造。
export function normalizeHistory(messages) {
  const result = []
  const tools = new Map()
  for (const message of messages) {
    if (message.role === 'ai') {
      if (message.content) result.push({ ...message, streaming: false })
      for (const call of message.tool_calls || []) {
        const tool = {
          id: 'tool-' + call.id, role: 'tool', tool_call_id: call.id,
          name: call.name, arguments: JSON.stringify(call.args || {}, null, 2),
          content: '', agent: message.agent || 'main', status: 'incomplete',
        }
        tools.set(call.id, tool)
        result.push(tool)
      }
    } else if (message.role === 'tool') {
      const existing = tools.get(message.tool_call_id)
      if (existing) Object.assign(existing, { content: message.content, status: message.status || 'success' })
      else result.push({ ...message, status: message.status || 'success' })
    } else result.push({ ...message, streaming: false })
  }
  return result
}

export function applyFinalAnswer(messages, data) {
  let message = messages.find((item) => item.id === data.message_id && item.role === 'ai')
  if (!message) {
    message = { id: data.message_id, role: 'ai', agent: 'main', content: '' }
    messages.push(message)
  }
  Object.assign(message, { content: data.answer, streaming: false, final: true, request_id: data.request_id })
}

export function settlePendingTools(messages, start, status) {
  for (const item of messages.slice(start)) {
    if (item.role === 'tool' && item.status === 'running') {
      item.status = status === 'success' ? 'incomplete' : status === 'error' ? 'error' : 'cancelled'
    }
    if (item.role === 'ai') item.streaming = false
  }
}
