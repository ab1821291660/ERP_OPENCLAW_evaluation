// 注释心跳不产生页面消息；多行 data 和跨网络分片的 UTF-8 都在这里重组。
export function parseSseBlock(block) {
  let event = 'message'
  const data = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  return data.length ? { event, data: JSON.parse(data.join('\n')) } : null
}

export async function streamAgent(payload, { signal, onEvent }) {
  const response = await fetch('/api/v1/agent/stream', {
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join('；') :
      detail || '请求失败：HTTP ' + response.status)
  }
  if (!response.body) throw new Error('浏览器不支持流式响应')
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() || ''
      for (const block of blocks) {
        const parsed = parseSseBlock(block)
        if (parsed) onEvent(parsed.event, parsed.data)
      }
      if (done) break
    }
    if (buffer.trim()) {
      const parsed = parseSseBlock(buffer)
      if (parsed) onEvent(parsed.event, parsed.data)
    }
  } finally {
    reader.releaseLock()
  }
}
