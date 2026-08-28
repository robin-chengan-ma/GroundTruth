<script setup lang="ts">
import axios from 'axios'
import { ref } from 'vue'

import { api } from '../api/client'

const rawText = ref('')
const loading = ref(false)
const result = ref('')
const error = ref('')

async function submit() {
  loading.value = true
  result.value = ''
  error.value = ''
  try {
    const response = await api.post('/inquiries/trigger/', { raw_text: rawText.value })
    result.value = typeof response.data === 'string' ? response.data : JSON.stringify(response.data, null, 2)
    rawText.value = ''
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '詢價送出失敗') : '詢價送出失敗'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <header class="page-header"><div><p>採購流程</p><h1>新增詢價</h1></div></header>
  <section class="surface inquiry-card">
    <h2>用一句話描述採購需求</h2>
    <p>請包含產品、數量與供應商全名。系統會先遮罩敏感資訊，再交由 AI 解析。</p>
    <form @submit.prevent="submit">
      <label for="inquiry">詢價內容</label>
      <textarea id="inquiry" v-model.trim="rawText" rows="6" placeholder="例如：跟優品科技採購 20 個 A產品-辦公椅" required />
      <div class="form-actions"><button class="primary-button" :disabled="loading || !rawText" type="submit">{{ loading ? '處理中…' : '送出詢價' }}</button></div>
    </form>
    <pre v-if="result" class="success-panel">{{ result }}</pre>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  </section>
</template>
