<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import PurchaseRequestDetailView from './PurchaseRequestDetailView.vue'
import StatusBadge from '../components/StatusBadge.vue'
import type { PaginatedPurchaseRequests, PurchaseRequestSummary } from '../types/api'
import { formatDateTime } from '../utils/formatters'

const requests = ref<PurchaseRequestSummary[]>([])
const loading = ref(true)
const error = ref('')
const count = ref(0)
const totalPages = ref(1)
const route = useRoute()
const router = useRouter()
const detailId = computed(() => {
  const id = route.params?.id
  return typeof id === 'string' ? id : ''
})

function allowedPageSize(value: unknown): 10 | 20 | 50 {
  const parsed = Number(value)
  return parsed === 10 || parsed === 50 ? parsed : 20
}

function positivePage(value: unknown) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1
}

const page = ref(positivePage(route.query.page))
const pageSize = ref<10 | 20 | 50>(allowedPageSize(route.query.page_size))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = (await api.get<PaginatedPurchaseRequests>('/purchase-requests/', {
      params: { page: page.value, page_size: pageSize.value },
    })).data
    requests.value = response.results
    count.value = response.count
    totalPages.value = response.total_pages
    page.value = response.page
  } catch {
    error.value = '無法載入採購清單'
  } finally {
    loading.value = false
  }
}

function updateQuery(nextPage: number, nextPageSize = pageSize.value) {
  router.replace({ query: { page: String(nextPage), page_size: String(nextPageSize) } })
}

function changePageSize(event: Event) {
  updateQuery(1, allowedPageSize((event.target as HTMLSelectElement).value))
}

function closeDetail() {
  router.replace({
    path: '/purchase-requests',
    query: { page: String(page.value), page_size: String(pageSize.value) },
  })
}

watch(
  () => [route.query.page, route.query.page_size],
  () => {
    page.value = positivePage(route.query.page)
    pageSize.value = allowedPageSize(route.query.page_size)
    void load()
  },
)

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
            <td><RouterLink class="request-link" :to="`/purchase-requests/${request.id}?page=${page}&page_size=${pageSize}`">{{ request.request_no }}</RouterLink></td><td>{{ request.purpose || '—' }}</td><td>{{ request.item_summary }}</td><td>{{ request.supplier_summary }}</td><td>{{ request.requester_name }}</td><td>{{ formatDateTime(request.created_at) }}</td><td><StatusBadge :status="request.status" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <footer v-if="!loading && !error" class="pagination-bar">
      <span>共 {{ count }} 筆</span>
      <label>每頁
        <select aria-label="每頁筆數" :value="pageSize" @change="changePageSize">
          <option :value="10">10 筆</option>
          <option :value="20">20 筆</option>
          <option :value="50">50 筆</option>
        </select>
      </label>
      <nav aria-label="採購需求分頁">
        <button type="button" class="secondary-button" :disabled="page <= 1" @click="updateQuery(page - 1)">上一頁</button>
        <strong>{{ page }} / {{ totalPages }}</strong>
        <button type="button" class="secondary-button" :disabled="page >= totalPages" @click="updateQuery(page + 1)">下一頁</button>
      </nav>
    </footer>
  </section>
  <PurchaseRequestDetailView v-if="detailId" :id="detailId" @close="closeDetail" />
</template>
