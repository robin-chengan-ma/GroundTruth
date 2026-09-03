<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import type { ManualReview, PaginatedList } from '../types/api'
import { formatDateTime } from '../utils/formatters'

// 詢價階段（人工複核 supplier_fuzzy_match）被駁回、當下尚未建立正式 PurchaseRequest 的案件，
// 獨立成專屬頁面，不再塞在「我的採購需求」最上方（Robin 2026-09-03 決策：該區塊會隨駁回案件
// 增加持續往上堆，見「詢價已駁回清單獨立頁」ADR）。單一用途清單，不提供狀態篩選。
const reviews = ref<ManualReview[]>([])
const loading = ref(true)
const error = ref('')
const count = ref(0)
const totalPages = ref(1)
const page = ref(1)
const pageSize = ref<10 | 20 | 50>(20)

async function load(nextPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const response = (await api.get<PaginatedList<ManualReview>>('/manual-review-queue/mine/', {
      params: { page: nextPage, page_size: pageSize.value },
    })).data
    reviews.value = response.results
    count.value = response.count
    totalPages.value = response.total_pages
    page.value = response.page
  } catch {
    error.value = '無法載入詢價已駁回清單'
  } finally {
    loading.value = false
  }
}

function changePageSize(event: Event) {
  pageSize.value = Number((event.target as HTMLSelectElement).value) as 10 | 20 | 50
  void load(1)
}

onMounted(() => load())
</script>

<template>
  <PageHeader eyebrow="採購流程" title="詢價已駁回清單">
    <template #actions>
      <button class="secondary-button" @click="load(page)">重新整理</button>
    </template>
  </PageHeader>

  <section class="surface table-surface">
    <p class="muted-text" style="margin: 20px 20px 12px;">這些詢價在管理員複核時被駁回，系統依設計尚未建立正式採購需求，請依駁回原因調整後重新送出；每筆只能複製一次，避免變成通用的複製功能。</p>
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="reviews.length === 0" class="empty-state">目前沒有已駁回的詢價案件。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>原始輸入內容</th><th>駁回原因</th><th>駁回時間</th><th></th></tr></thead>
        <tbody>
          <tr v-for="item in reviews" :key="item.id">
            <td>{{ item.raw_input_text || '—' }}</td>
            <td>{{ item.rejection_reason || '（未填寫）' }}</td>
            <td>{{ formatDateTime(item.updated_at) }}</td>
            <td>
              <span v-if="item.copied_to_request_no" class="muted-text">已複製為 {{ item.copied_to_request_no }}</span>
              <RouterLink
                v-else
                class="secondary-button"
                :to="{ path: '/inquiry', query: { copied_from_review: String(item.id), text: item.raw_input_text || '' } }"
              >複製並重新編輯</RouterLink>
            </td>
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
      <nav aria-label="詢價已駁回清單分頁">
        <button type="button" class="secondary-button" :disabled="page <= 1" @click="load(page - 1)">上一頁</button>
        <strong>{{ page }} / {{ totalPages }}</strong>
        <button type="button" class="secondary-button" :disabled="page >= totalPages" @click="load(page + 1)">下一頁</button>
      </nav>
    </footer>
  </section>
</template>
