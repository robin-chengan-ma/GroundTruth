<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import type { PurchaseRequestSummary } from '../types/api'
import { formatDateTime } from '../utils/formatters'

const requests = ref<PurchaseRequestSummary[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  try {
    requests.value = (await api.get<PurchaseRequestSummary[]>('/purchase-requests/')).data
  } catch {
    error.value = '無法載入採購清單'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="採購流程" title="採購清單">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>
  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="requests.length === 0" class="empty-state">目前沒有採購需求。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>申請編號</th><th>採購用途</th><th>品項摘要</th><th>候選供應商</th><th>申請人</th><th>建立時間</th><th>狀態</th></tr></thead>
        <tbody>
          <tr v-for="request in requests" :key="request.id">
            <td>{{ request.request_no }}</td><td>{{ request.purpose || '—' }}</td><td>{{ request.item_summary }}</td><td>{{ request.supplier_summary }}</td><td>{{ request.requester_name }}</td><td>{{ formatDateTime(request.created_at) }}</td><td><StatusBadge :status="request.status" /></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
