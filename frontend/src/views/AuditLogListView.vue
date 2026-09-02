<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import type { AuditLog, Paginated } from '../types/api'
import { formatDateTime } from '../utils/formatters'

const logs = ref<AuditLog[]>([])
const next = ref<string | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = (await api.get<Paginated<AuditLog>>('/audit-logs/')).data
    logs.value = response.results
    next.value = response.next
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法載入稽核紀錄（需 audit.read 權限）')
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!next.value) return
  try {
    const response = (await api.get<Paginated<AuditLog>>(next.value)).data
    logs.value.push(...response.results)
    next.value = response.next
  } catch (reason) {
    error.value = apiErrorMessage(reason, '載入更多稽核紀錄失敗')
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="稽核" title="稽核紀錄">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>
  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="logs.length === 0" class="empty-state">目前沒有稽核紀錄。</p>
    <template v-else>
      <div class="table-scroll">
        <table>
          <thead><tr><th>時間</th><th>類型</th><th>驗證結果</th><th>對應報價</th><th>查詢摘要</th></tr></thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td>{{ formatDateTime(log.created_at) }}</td>
              <td>{{ log.action_type }}</td>
              <td>{{ log.verification_result ?? '—' }}</td>
              <td>{{ log.quote ?? '—' }}</td>
              <td>{{ log.real_query_summary || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer v-if="next" class="pagination-bar">
        <button type="button" class="secondary-button" @click="loadMore">載入更多</button>
      </footer>
    </template>
  </section>
</template>
