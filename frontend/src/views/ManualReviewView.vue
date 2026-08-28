<script setup lang="ts">
import axios from 'axios'
import { onMounted, ref } from 'vue'

import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { ManualReview, Paginated } from '../types/api'

const auth = useAuthStore()
const reviews = ref<ManualReview[]>([])
const error = ref('')

async function load() {
  try { reviews.value = (await api.get<Paginated<ManualReview>>('/manual-review-queue/')).data.results }
  catch { error.value = '無法載入人工複核案件' }
}

async function claim(item: ManualReview) {
  try { await api.post(`/manual-review-queue/${item.id}/claim/`); await load() }
  catch (reason) { error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '認領失敗') : '認領失敗' }
}

async function decide(item: ManualReview, decision: 'approved' | 'rejected') {
  let supplierId: number | undefined
  if (decision === 'approved' && item.review_type === 'supplier_fuzzy_match' && !item.supplier) {
    const input = window.prompt('請輸入確認後的 supplier_id')
    if (!input) return
    supplierId = Number(input)
  }
  try {
    const response = await api.post(`/manual-review-queue/${item.id}/decide/`, { decision, supplier_id: supplierId })
    if (response.data.resume_triggered === false) error.value = '案件已核准，但 n8n 續傳通知失敗，請人工確認。'
    await load()
  } catch (reason) { error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '決議失敗') : '決議失敗' }
}

onMounted(load)
</script>

<template>
  <header class="page-header"><div><p>AI 安全</p><h1>人工複核</h1></div><button class="secondary-button" @click="load">重新整理</button></header>
  <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  <p v-if="reviews.length === 0" class="surface empty-state">目前沒有人工複核案件。</p>
  <div v-else class="card-grid">
    <article v-for="item in reviews" :key="item.id" class="surface approval-card">
      <header><div><small>複核案件 #{{ item.id }}</small><h2>{{ item.review_type === 'hallucination_mismatch' ? 'AI 摘要數字不一致' : '供應商名稱模糊' }}</h2></div><StatusBadge :status="item.status" /></header>
      <section v-if="item.review_type === 'hallucination_mismatch'" class="comparison"><div><strong>AI 生成內容</strong><p>{{ item.ai_generated_text }}</p></div><div><strong>原始真實值</strong><pre>{{ item.expected_value }}</pre></div></section>
      <section v-else class="comparison"><div><strong>使用者原文</strong><p>{{ item.raw_input_text }}</p></div><div><strong>系統候選</strong><p>{{ item.supplier_name || '需人工指定 supplier_id' }}</p></div></section>
      <footer><span v-if="item.claimant_name">已由 {{ item.claimant_name }} 認領</span><button v-if="item.status === 'unclaimed'" class="primary-button" @click="claim(item)">認領案件</button><template v-if="item.status === 'claimed' && item.user === auth.user?.id"><button class="secondary-button danger" @click="decide(item, 'rejected')">駁回</button><button class="primary-button" @click="decide(item, 'approved')">核准</button></template></footer>
    </article>
  </div>
</template>
