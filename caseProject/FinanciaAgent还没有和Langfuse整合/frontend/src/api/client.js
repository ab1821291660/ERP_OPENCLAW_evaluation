import axios from 'axios'

export const api = axios.create({ baseURL: '/api', timeout: 30000 })
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail
    const message = Array.isArray(detail) ? detail.map((item) => item.msg).join('；') : detail
    return Promise.reject(new Error(message || error.message || '请求失败'))
  },
)
export const sessionsApi = {
  list: () => api.get('/v1/sessions'),
  create: (title = null) => api.post('/v1/sessions', { title }),
  messages: (id) => api.get('/v1/sessions/' + encodeURIComponent(id) + '/messages'),
  rename: (id, title) => api.patch('/v1/sessions/' + encodeURIComponent(id), { title }),
  remove: (id) => api.delete('/v1/sessions/' + encodeURIComponent(id)),
  clear: () => api.delete('/v1/sessions'),
  stop: (id) => api.post('/v1/sessions/' + encodeURIComponent(id) + '/stop'),
}
