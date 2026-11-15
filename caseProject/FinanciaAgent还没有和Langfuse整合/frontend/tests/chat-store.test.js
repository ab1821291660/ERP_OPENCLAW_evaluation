import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick, watch } from 'vue'
import { useChatStore } from '../src/stores/chat.js'
import { sessionsApi } from '../src/api/client.js'

const session = { session_id: 'session-test', title: '新会话', updated_at: '2026-10-14T00:00:00Z' }
const encode = (event, data) => new TextEncoder().encode('event: ' + event + '\ndata: ' + JSON.stringify(data) + '\n\n')

async function withMocks(callback) {
  const originalFetch = globalThis.fetch
  const originalSessions = { ...sessionsApi }
  setActivePinia(createPinia())
  Object.assign(sessionsApi, {
    create: async () => ({ data: { ...session } }),
    list: async () => ({ data: [{ ...session }] }),
    messages: async () => ({ data: [{ id: 'history-user', role: 'human', content: '历史提问' }] }),
    rename: async (id, title) => ({ data: { ...session, session_id: id, title } }),
    remove: async () => ({}), clear: async () => ({}), stop: async () => ({}),
  })
  try { await callback(useChatStore()) }
  finally { globalThis.fetch = originalFetch; Object.assign(sessionsApi, originalSessions) }
}

function responseFrom(events) {
  let index = 0
  return new Response(new ReadableStream({
    async pull(controller) {
      await new Promise((resolve) => setTimeout(resolve, 2))
      if (index === events.length) controller.close()
      else controller.enqueue(encode(...events[index++]))
    },
  }))
}

test('Pinia 逐块更新文本/工具；最终答案不重复；历史切换及删除可用', async () => {
  await withMocks(async (chat) => {
    globalThis.fetch = async () => responseFrom([
      ['run_start', { request_id: 'request-1', human_message_id: 'user-1' }],
      ['message_start', { message_id: 'research-1', agent: 'researcher' }],
      ['text_delta', { message_id: 'research-1', agent: 'researcher', content: '原始证据' }],
      ['message_complete', { message_id: 'research-1' }],
      ['tool_start', { tool_call_id: 'calc-1', name: 'safe_calculate', agent: 'reviewer', arguments: '{}' }],
      ['tool_result', { tool_call_id: 'calc-1', name: 'safe_calculate', agent: 'reviewer', content: '25', status: 'success' }],
      ['message_start', { message_id: 'answer-1', agent: 'main' }],
      ['text_delta', { message_id: 'answer-1', agent: 'main', content: '增长率' }],
      ['text_delta', { message_id: 'answer-1', agent: 'main', content: '25%' }],
      ['message_complete', { message_id: 'answer-1' }],
      ['answer_complete', { message_id: 'answer-1', request_id: 'request-1', answer: '增长率25%' }],
      ['done', { status: 'success' }],
    ])
    const updates = []
    const unwatch = watch(
      () => chat.messages.map((item) => item.content + ':' + item.status).join('|'),
      (value) => updates.push(value),
    )
    await chat.sendMessage('分析增长率')
    await nextTick()
    unwatch()
    assert.equal(chat.error, '')
    assert.equal(chat.streaming, false)
    assert.equal(chat.messages[0].id, 'user-1')
    assert.equal(chat.messages.filter((item) => item.id === 'answer-1').length, 1)
    assert.equal(chat.messages.find((item) => item.id === 'answer-1').content, '增长率25%')
    assert.equal(chat.messages.find((item) => item.id === 'research-1').content, '原始证据')
    assert.equal(chat.messages.find((item) => item.tool_call_id === 'calc-1').status, 'success')
    assert.ok(updates.some((value) => value.includes('增长率:')), '文本没有逐块触发响应式更新')
    assert.ok(updates.some((value) => value.includes(':running')), '工具没有显示运行态')
    await chat.renameSession(session.session_id, '新标题')
    assert.equal(chat.currentSession.title, '新标题')
    await chat.selectSession(session.session_id)
    assert.equal(chat.messages[0].content, '历史提问')
    await chat.removeSession(session.session_id)
    assert.equal(chat.currentSessionId, null)
    await chat.createSession()
    await chat.clearAllSessions()
    assert.deepEqual(chat.messages, [])
    assert.deepEqual(chat.sessions, [])
  })
})

test('流式连接提前结束会报错并收尾工具，不永久显示执行中', async () => {
  await withMocks(async (chat) => {
    globalThis.fetch = async () => responseFrom([
      ['run_start', { request_id: 'request-2', human_message_id: 'user-2' }],
      ['tool_start', { tool_call_id: 'lost', name: 'task', agent: 'main' }],
    ])
    await chat.sendMessage('测试意外断连')
    assert.match(chat.error, /连接提前结束/)
    assert.equal(chat.messages.find((item) => item.tool_call_id === 'lost').status, 'error')
    assert.equal(chat.streaming, false)
  })
})
