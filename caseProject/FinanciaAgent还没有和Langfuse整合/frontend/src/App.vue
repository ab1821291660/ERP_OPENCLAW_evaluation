<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink to="/chat" class="brand">
        <span class="brand-mark">FQ</span>
        <span><strong>FinQA Agent</strong><small>财务研究工作台</small></span>
      </RouterLink>
      <nav class="topnav"><RouterLink to="/chat" class="active">Agent 对话</RouterLink></nav>
      <div class="user-chip"><span></span> demo-user</div>
    </header>
    <main class="app-main"><RouterView /></main>
  </div>
</template>
