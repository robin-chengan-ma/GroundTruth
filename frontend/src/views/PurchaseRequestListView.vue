<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import PurchaseRequestDetailView from './PurchaseRequestDetailView.vue'
import StatusBadge from '../components/StatusBadge.vue'
import type { PaginatedPurchaseRequests, PurchaseRequestSummary } from '../types/api'
import { formatDateTime } from '../utils/formatters'

const STATUS_OPTIONS: Array<[string, string]> = [
  ['', '全部狀態'],
  ['draft', '草稿'],
  ['submitted', '已送出'],
  ['sourcing', '詢價中'],
  ['awarding', '評選中'],
  ['approval', '簽核中'],
  ['rejected', '已駁回'],
  ['ordered', '已下單'],
  ['partially_received', '部分收貨'],
  ['completed', '已完成'],
  ['withdrawn', '已撤回'],
  ['cancelled', '已取消'],
]

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
const statusFilter = ref(typeof route.query.status === 'string' ? route.query.status : '')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = (await api.get<PaginatedPurchaseRequests>('/purchase-requests/', {
      params: { page: page.value, page_size: pageSize.value, status: statusFilter.value || undefined },
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

function updateQuery(nextPage: number, nextPageSize = pageSize.value, nextStatus = statusFilter.value) {
  const query: Record<string, string> = { page: String(nextPage), page_size: String(nextPageSize) }
  if (nextStatus) query.status = nextStatus
  router.replace({ query })
}

function changePageSize(event: Event) {
  updateQuery(1, allowedPageSize((event.target as HTMLSelectElement).value))
}

function changeStatusFilter(event: Event) {
  updateQuery(1, pageSize.value, (event.target as HTMLSelectElement).value)
}

function closeDetail() {
  router.replace({
    path: '/purchase-requests',
    query: { page: String(page.value), page_size: String(pageSize.value), status: statusFilter.value || undefined },
  })
}

watch(
  () => [route.query.page, route.query.page_size, route.query.status],
  () => {
    page.value = positivePage(route.query.page)
    pageSize.value = allowedPageSize(route.query.page_size)
    statusFilter.value = typeof route.query.status === 'string' ? route.query.status : ''
    void load()
  },
)

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="採購流程" title="採購清單">
    <template #actions>
      <select aria-label="狀態篩選" :value="statusFilter" @change="changeStatusFilter">
        <option v-for="[value, label] in STATUS_OPTIONS" :key="value" :value="value">{{ label }}</option>
      </select>
      <button class="secondary-button" @click="load">重新整理</button>
    </template>
  </PageHeader>

  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="requests.length === 0" class="empty-state">目前沒有採購需求。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>申請編號</th><th>採購用途</th><th>品項摘要</th><th>候選供應商</th><th>申請人</th><th>建立時間</th><th>狀態</th><th>備註</th></tr></thead>
        <tbody>
          <tr v-for="request in requests" :key="request.id">
            <td><RouterLink class="request-link" :to="`/purchase-requests/${request.id}?page=${page}&page_size=${pageSize}`">{{ request.request_no }}</RouterLink></td><td>{{ request.purpose || '—' }}</td><td>{{ request.item_summary }}</td><td>{{ request.supplier_summary }}</td><td>{{ request.requester_name }}</td><td>{{ formatDateTime(request.created_at) }}</td><td><StatusBadge :status="request.status" /></td><td>{{ request.rejection_reason || '—' }}</td>
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
