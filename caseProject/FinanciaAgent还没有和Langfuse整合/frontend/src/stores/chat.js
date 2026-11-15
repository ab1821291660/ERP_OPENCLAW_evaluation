import { defineStore } from 'pinia'
import { sessionsApi } from '../api/client.js'
import { streamAgent } from '../api/sse.js'
import { applyFinalAnswer, normalizeHistory, settlePendingTools } from './messages.js'

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: [], currentSessionId: null, messages: [],
    streaming: false, stopping: false, loadingHistory: false,
    error: '', notice: '', controller: null, agents: {},
  }),
  getters: {
    currentSession: (state) => state.sessions.find((item) => item.session_id === state.currentSessionId) || null,
  },
  actions: {
    async loadSessions() {
      const { data } = await sessionsApi.list()
      this.sessions = data
      if (!this.currentSessionId && data.length && !this.streaming) await this.selectSession(data[0].session_id)
    },
    async createSession() {
      if (this.streaming) return
      this.loadingHistory = true
      try {
        const { data } = await sessionsApi.create()
        this.sessions.unshift(data)
        this.currentSessionId = data.session_id
        this.messages = []
        this.error = this.notice = ''
        return data
      } finally { this.loadingHistory = false }
    },
    async selectSession(id) {
      if (this.streaming) return
      this.loadingHistory = true
      try {
        const { data } = await sessionsApi.messages(id)
        this.currentSessionId = id
        this.messages = normalizeHistory(data)
        this.error = this.notice = ''
      } finally { this.loadingHistory = false }
    },
    async renameSession(id, title) {
      const { data } = await sessionsApi.rename(id, title)
      const index = this.sessions.findIndex((item) => item.session_id === id)
      if (index >= 0) this.sessions[index] = data
    },
    async removeSession(id) {
      if (this.streaming) return
      await sessionsApi.remove(id)
      this.sessions = this.sessions.filter((item) => item.session_id !== id)
      if (this.currentSessionId === id) {
        this.currentSessionId = null
        this.messages = []
        if (this.sessions.length) await this.selectSession(this.sessions[0].session_id)
      }
    },
    async clearAllSessions() {
      if (this.streaming) return
      await sessionsApi.clear()
      this.sessions = []
      this.messages = []
      this.currentSessionId = null
      this.error = this.notice = ''
    },
    async stopStream() {
      if (!this.streaming || this.stopping) return
      this.stopping = true
      try { await sessionsApi.stop(this.currentSessionId) }
      catch { this.notice = '停止请求未确认，正在关闭连接。' }
      finally { this.controller?.abort() }
    },
    async sendMessage(question) {
      const content = question.trim()
      if (!content || this.streaming || this.loadingHistory) return
      if (!this.currentSessionId) await this.createSession()
      this.error = this.notice = ''
      this.streaming = true
      this.stopping = false
      this.agents = {}
      const controller = new AbortController()
      this.controller = controller
      const human = { id: 'local-' + Date.now(), role: 'human', content }
      this.messages.push(human)
      const start = this.messages.length
      let terminal = null
      let requestId = ''
      const findMessage = (id) => this.messages.find((item) => item.id === id)
      const findTool = (id) => this.messages.find((item) => item.tool_call_id === id)
      try {
        await streamAgent({ question: content, session_id: this.currentSessionId }, {
          signal: controller.signal,
          onEvent: (event, data) => {
            if (event === 'run_start') {
              requestId = data.request_id
              const savedHuman = findMessage(human.id)
              if (savedHuman) savedHuman.id = data.human_message_id
            } else if (event === 'message_start') {
              if (!findMessage(data.message_id)) this.messages.push({
                id: data.message_id, role: 'ai', agent: data.agent, content: '', streaming: true,
              })
            } else if (event === 'text_delta') {
              let message = findMessage(data.message_id)
              if (!message) {
                message = { id: data.message_id, role: 'ai', agent: data.agent, content: '', streaming: true }
                this.messages.push(message)
                message = findMessage(data.message_id)
              }
              message.content += data.content
            } else if (event === 'message_complete') {
              const message = findMessage(data.message_id)
              if (message) message.streaming = false
              this.messages = this.messages.filter((item) => item.id !== data.message_id || item.content)
            } else if (event === 'tool_start') {
              let tool = findTool(data.tool_call_id)
              if (!tool) {
                tool = { id: 'tool-' + data.tool_call_id, role: 'tool', content: '' }
                this.messages.push(tool)
                tool = this.messages[this.messages.length - 1]
              }
              Object.assign(tool, data, { status: 'running' })
            } else if (event === 'tool_delta') {
              const tool = findTool(data.tool_call_id)
              if (tool) tool.content += data.content || ''
            } else if (event === 'tool_result') {
              let tool = findTool(data.tool_call_id)
              if (!tool) {
                tool = { id: 'tool-' + data.tool_call_id, role: 'tool' }
                this.messages.push(tool)
              }
              Object.assign(tool, data)
            } else if (event === 'agent_start' || event === 'agent_end') {
              this.agents[data.agent] = data.status
            } else if (event === 'answer_complete') {
              applyFinalAnswer(this.messages, data)
            } else if (event === 'error') {
              terminal = 'error'
              this.error = data.message + '（请求编号：' + (data.request_id || requestId) + '）'
            } else if (event === 'done') {
              terminal = data.status
              if (terminal === 'cancelled') this.notice = '本次生成已停止。'
            }
          },
        })
        if (!terminal) throw new Error('连接提前结束，未收到完整执行结果，请重试')
      } catch (error) {
        if (error.name === 'AbortError') {
          terminal = 'cancelled'
          this.notice = '本次生成已停止。'
        } else {
          terminal = 'error'
          this.error = error.message || '流式请求失败'
        }
      } finally {
        settlePendingTools(this.messages, start, terminal)
        this.messages = this.messages.filter((item) => item.role !== 'ai' || item.content)
        this.streaming = this.stopping = false
        this.controller = null
        await this.loadSessions().catch(() => {})
      }
    },
  },
})
