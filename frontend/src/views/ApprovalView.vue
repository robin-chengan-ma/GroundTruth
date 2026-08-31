<script setup lang="ts">
import axios from 'axios'
import { onMounted, ref } from 'vue'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { Approval, Paginated } from '../types/api'

const auth = useAuthStore()
const approvals = ref<Approval[]>([])
const error = ref('')
const loading = ref(true)

async function load() {
  loading.value = true
  try { approvals.value = (await api.get<Paginated<Approval>>('/approvals/')).data.results }
  catch { error.value = '無法載入簽核案件' }
  finally { loading.value = false }
}

async function action(item: Approval, actionName: 'claim' | 'decide', decision?: 'approved' | 'rejected') {
  error.value = ''
  try {
    await api.post(`/approvals/${item.id}/${actionName}/`, decision ? { decision } : undefined)
    await load()
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '操作失敗') : '操作失敗'
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="待辦工作" title="簽核工作區">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>
  <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  <p v-if="loading" class="surface empty-state">載入中…</p>
  <p v-else-if="approvals.length === 0" class="surface empty-state">目前沒有符合資格的簽核案件。</p>
  <div v-else class="card-grid">
    <article v-for="item in approvals" :key="item.id" class="surface approval-card">
      <header><div><small>採購單 #{{ item.quote }}</small><h2>{{ item.quote_detail.product_name }}</h2></div><StatusBadge :status="item.status" /></header>
      <dl><div><dt>供應商</dt><dd>{{ item.quote_detail.supplier_name }}</dd></div><div><dt>數量</dt><dd>{{ item.quote_detail.quantity }}</dd></div><div><dt>總金額</dt><dd>{{ item.quote_detail.currency }} {{ Number(item.quote_detail.total_amount).toLocaleString() }}</dd></div><div><dt>簽核層級</dt><dd>{{ item.approval_level }}</dd></div></dl>
      <div v-if="item.quote_detail.price_deviation_pct && Math.abs(Number(item.quote_detail.price_deviation_pct)) > 20" class="warning-panel">價格偏離歷史均價 {{ item.quote_detail.price_deviation_pct }}%，僅供判斷，不阻擋簽核。</div>
      <section class="summary-panel"><strong>AI 摘要</strong><p>{{ item.quote_detail.ai_summary_text || '尚無摘要' }}</p></section>
      <footer>
        <span v-if="item.approver_name">已由 {{ item.approver_name }} 認領</span>
        <button v-if="!item.approver && item.status === 'pending' && item.role_code === auth.user?.role" class="primary-button" @click="action(item, 'claim')">認領案件</button>
        <template v-if="item.approver === auth.user?.id && item.status === 'pending'">
          <button class="secondary-button danger" @click="action(item, 'decide', 'rejected')">駁回</button>
          <button class="primary-button" @click="action(item, 'decide', 'approved')">核准</button>
        </template>
      </footer>
    </article>
  </div>
</template>
