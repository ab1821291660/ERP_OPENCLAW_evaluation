import test from 'node:test'
import assert from 'node:assert/strict'
import { parseSseBlock, streamAgent } from '../src/api/sse.js'

test('心跳注释不创建消息', () => assert.equal(parseSseBlock(': heartbeat'), null))

test('UTF-8 中文、CRLF 边界与最终无空行事件都可以恢复', async () => {
  const previous = globalThis.fetch
  const raw = 'event: text_delta\r\ndata: {"content":"财务分析"}\r\n\r\n: heartbeat\r\n\r\nevent: done\ndata: {"status":"success"}'
  const bytes = new TextEncoder().encode(raw)
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += 2) controller.enqueue(bytes.slice(i, i + 2))
      controller.close()
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
  const events = []
  try {
    await streamAgent({ question: '测试', session_id: 's' }, {
      onEvent: (event, data) => events.push({ event, data }),
    })
  } finally { globalThis.fetch = previous }
  assert.deepEqual(events, [
    { event: 'text_delta', data: { content: '财务分析' } },
    { event: 'done', data: { status: 'success' } },
  ])
})
