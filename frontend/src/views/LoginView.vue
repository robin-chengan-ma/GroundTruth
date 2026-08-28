<script setup lang="ts">
import axios from 'axios'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(email.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/inquiry'
    await router.replace(redirect)
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '登入失敗，請稍後再試') : '登入失敗'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-intro">
      <div class="brand"><span>G</span> GroundTruth</div>
      <div>
        <h1>讓每一次 AI 採購決策，都有真實資料可追溯。</h1>
        <p>從詢價、驗證到簽核，以固定規則守住敏感資料與關鍵數字。</p>
      </div>
      <small>內部採購與簽核系統</small>
    </section>
    <section class="login-form-area">
      <form class="login-form" @submit.prevent="submit">
        <h2>登入工作台</h2>
        <p>使用公司 Email 繼續</p>
        <label for="email">Email</label>
        <input id="email" v-model.trim="email" type="email" autocomplete="username" placeholder="name@company.com" required>
        <label for="password">密碼</label>
        <div class="password-field">
          <input id="password" v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" required>
          <button type="button" @click="showPassword = !showPassword">{{ showPassword ? '隱藏' : '顯示' }}</button>
        </div>
        <button class="primary-button" type="submit" :disabled="loading">{{ loading ? '登入中…' : '登入' }}</button>
        <p v-if="error" class="error-message" role="alert">{{ error }}</p>
        <small>僅供授權使用者存取。登入問題請聯絡系統管理員。</small>
      </form>
    </section>
  </main>
</template>
