<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref } from 'vue'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { ManualReview, Paginated } from '../types/api'

const auth = useAuthStore()
const reviews = ref<ManualReview[]>([])
const error = ref('')
const statusFilter = ref('')

// 認領狀態（status）與決議結果（decision）是兩個獨立欄位，但對使用者來說「已核准／已駁回」
// 比「已結案」更有意義，所以這裡合併成單一篩選維度顯示。
const filteredReviews = computed(() => {
  if (!statusFilter.value) return reviews.value
  return reviews.value.filter((item) => {
    if (statusFilter.value === 'approved' || statusFilter.value === 'rejected') {
      return item.status === 'resolved' && item.decision === statusFilter.value
    }
    return item.status === statusFilter.value
  })
})

async function load() {
  try { reviews.value = (await api.get<Paginated<ManualReview>>('/manual-review-queue/')).data.results }
  catch { error.value = '無法載入人工複核案件' }
}

async function claim(item: ManualReview) {
  try { await api.post(`/manual-review-queue/${item.id}/claim/`); await load() }
  catch (reason) { error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '認領失敗') : '認領失敗' }
}

async function decide(item: ManualReview, decision: 'approved' | 'rejected', reason?: string) {
  let supplierId: number | undefined
  if (decision === 'approved' && item.review_type === 'supplier_fuzzy_match' && !item.supplier) {
    const input = window.prompt('請輸入確認後的 supplier_id')
    if (!input) return
    supplierId = Number(input)
  }
  try {
    const response = await api.post(`/manual-review-queue/${item.id}/decide/`, { decision, supplier_id: supplierId, reason })
    if (response.data.resume_status === 'failed') error.value = '案件已核准，但自動建立採購需求草稿失敗，可點擊「重試續傳」再試一次。'
    await load()
  } catch (reason) { error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '決議失敗') : '決議失敗' }
}

async function retryResume(item: ManualReview) {
  try {
    const response = await api.post(`/manual-review-queue/${item.id}/retry-resume/`)
    if (response.data.resume_status === 'failed') error.value = '重試續傳仍然失敗，請確認採購需求資料或聯絡系統管理員。'
    await load()
  } catch (reason) { error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '重試續傳失敗') : '重試續傳失敗' }
}

// ---- 駁回原因彈窗：一定要填原因才能送出（Robin 2026-09-03 決策），
// 但仍保留「取消」讓管理員可以放棄這次駁回動作，不強迫一定要駁回。
const rejectTarget = ref<ManualReview | null>(null)
const rejectReason = ref('')
const rejectSaving = ref(false)
const rejectError = ref('')

function openReject(item: ManualReview) {
  rejectTarget.value = item
  rejectReason.value = ''
  rejectError.value = ''
}

function cancelReject() {
  rejectTarget.value = null
}

async function confirmReject() {
  if (!rejectReason.value.trim()) {
    rejectError.value = '請填寫駁回原因'
    return
  }
  if (!rejectTarget.value) return
  rejectSaving.value = true
  try {
    await decide(rejectTarget.value, 'rejected', rejectReason.value.trim())
    rejectTarget.value = null
  } finally {
    rejectSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="AI 安全" title="人工複核">
    <template #actions>
      <select aria-label="狀態篩選" v-model="statusFilter">
        <option value="">全部狀態</option>
        <option value="unclaimed">未認領</option>
        <option value="claimed">處理中</option>
        <option value="approved">已核准</option>
        <option value="rejected">已駁回</option>
      </select>
      <button class="secondary-button" @click="load">重新整理</button>
    </template>
  </PageHeader>
  <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  <p v-if="filteredReviews.length === 0" class="surface empty-state">目前沒有符合條件的人工複核案件。</p>
  <div v-else class="card-grid">
    <article v-for="item in filteredReviews" :key="item.id" class="surface approval-card" :class="{ rejected: item.decision === 'rejected' }">
      <header><div><small>複核案件 #{{ item.id }}</small><h2>{{ item.review_type === 'hallucination_mismatch' ? 'AI 摘要數字不一致' : '供應商名稱模糊' }}</h2></div><StatusBadge :status="item.status" /></header>
      <section v-if="item.review_type === 'hallucination_mismatch'" class="comparison"><div><strong>AI 生成內容</strong><p>{{ item.ai_generated_text }}</p></div><div><strong>原始真實值</strong><pre>{{ item.expected_value }}</pre></div></section>
      <section v-else class="comparison"><div><strong>使用者原文</strong><p>{{ item.raw_input_text }}</p></div><div><strong>系統候選</strong><p>{{ item.supplier_name || '需人工指定 supplier_id' }}</p></div></section>
      <p v-if="item.decision === 'rejected'" class="rejection-reason"><strong>駁回原因：</strong>{{ item.rejection_reason || '（未填寫）' }}</p>
      <footer><span v-if="item.claimant_name">已由 {{ item.claimant_name }} 認領</span><button v-if="item.status === 'unclaimed'" class="primary-button" @click="claim(item)">認領案件</button><template v-if="item.status === 'claimed' && item.user === auth.user?.id"><button class="secondary-button danger" @click="openReject(item)">駁回</button><button class="primary-button" @click="decide(item, 'approved')">核准</button></template><button v-if="item.resume_status === 'failed'" class="secondary-button" @click="retryResume(item)">重試續傳</button></footer>
    </article>
  </div>

  <div v-if="rejectTarget" class="modal-backdrop">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="reject-reason-title">
      <header class="modal-header">
        <div><span class="eyebrow">人工複核</span><h2 id="reject-reason-title">駁回案件 #{{ rejectTarget.id }}</h2></div>
      </header>
      <div class="modal-body">
        <form @submit.prevent="confirmReject">
          <label for="reject-reason">駁回原因</label>
          <textarea id="reject-reason" v-model="rejectReason" rows="4" required placeholder="請說明駁回原因，申請人會收到這則說明"></textarea>
          <p v-if="rejectError" class="error-message" role="alert">{{ rejectError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="cancelReject">取消</button>
            <button type="submit" class="primary-button" :disabled="rejectSaving || !rejectReason.trim()">{{ rejectSaving ? '儲存中…' : '儲存' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>
