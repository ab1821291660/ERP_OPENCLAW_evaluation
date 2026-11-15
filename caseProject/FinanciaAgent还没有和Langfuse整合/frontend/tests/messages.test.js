import test from 'node:test'
import assert from 'node:assert/strict'
import { applyFinalAnswer, normalizeHistory, settlePendingTools } from '../src/stores/messages.js'

test('最终答案按消息 ID 回填，不替换子 Agent 草稿', () => {
  const messages = [
    { id: 'review', role: 'ai', agent: 'reviewer', content: '复核草稿' },
    { id: 'main', role: 'ai', agent: 'main', content: '部分答案', streaming: true },
  ]
  applyFinalAnswer(messages, { message_id: 'main', answer: '完整答案', request_id: 'request' })
  assert.equal(messages.length, 2)
  assert.equal(messages[0].content, '复核草稿')
  assert.equal(messages[1].content, '完整答案')
  assert.equal(messages[1].streaming, false)
})

test('历史工具请求和结果合并为一张卡片，缺失结果不永久显示执行中', () => {
  const history = normalizeHistory([
    { id: 'ai', role: 'ai', content: '', tool_calls: [{ id: 'c1', name: 'task', args: {} }, { id: 'c2', name: 'safe_calculate', args: {} }] },
    { id: 'tool', role: 'tool', tool_call_id: 'c1', content: '证据', status: 'success' },
  ])
  assert.equal(history.length, 2)
  assert.equal(history[0].content, '证据')
  assert.equal(history[0].status, 'success')
  assert.equal(history[1].status, 'incomplete')
})

test('停止本轮只收尾本轮的待完成工具', () => {
  const messages = [{ role: 'tool', status: 'running' }, { role: 'tool', status: 'running' }]
  settlePendingTools(messages, 1, 'cancelled')
  assert.equal(messages[0].status, 'running')
  assert.equal(messages[1].status, 'cancelled')
})
