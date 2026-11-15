import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/chat', name: 'chat', component: ChatView },
  ],
})
