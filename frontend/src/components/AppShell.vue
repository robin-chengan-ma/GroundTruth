<script setup lang="ts">
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function logout() {
  await auth.logout()
  await router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/inquiry"><span>G</span> GroundTruth</RouterLink>
      <nav aria-label="主要導覽">
        <RouterLink to="/inquiry">新增詢價</RouterLink>
        <RouterLink to="/quotes">採購清單</RouterLink>
        <RouterLink v-if="auth.canApprove" to="/approvals">簽核工作區</RouterLink>
        <RouterLink v-if="auth.isAdmin" to="/reviews">AI 人工複核</RouterLink>
      </nav>
      <div class="account-panel">
        <strong>{{ auth.user?.name }}</strong>
        <small>{{ auth.user?.role }}</small>
        <button class="text-button" type="button" @click="logout">登出</button>
      </div>
    </aside>
    <main class="workspace"><slot /></main>
  </div>
</template>
