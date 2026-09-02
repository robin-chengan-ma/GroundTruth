<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import ListPagination from '../components/ListPagination.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useListQuery } from '../composables/useListQuery'
import { useAuthStore } from '../stores/auth'
import type { AwardDecision, PaginatedList, Rfq } from '../types/api'
import { formatDateTime, formatMoney, formatQuantity } from '../utils/formatters'
import { fetchAllPages } from '../utils/pagination'

const AWARD_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'submitted', label: '已提交' },
  { value: 'approved', label: '已核准' },
  { value: 'rejected', label: '已駁回' },
  { value: 'cancelled', label: '已取消' },
]

interface EvaluationQuoteRow {
  quote_id: number
  quote_item_id: number
  supplier_id: number
  supplier_name: string
  unit_price: string
  currency: string
  allocated_unit_cost_twd: string
  eligible: boolean
  eligibility_reason: string
  total_score: string
}
interface EvaluationItemSection {
  request_item_id: number
  line_no: number
  description: string
  requested_quantity: string
  unit_of_measure: string
  quotes: EvaluationQuoteRow[]
  recommended_quote_ids: number[]
}
interface EvaluationResult {
  items: EvaluationItemSection[]
}

interface LineForm {
  request_item_id: number
  description: string
  requested_quantity: string
  unit_of_measure: string
  options: EvaluationQuoteRow[]
  supplier_quote_item_id: number | ''
  quantity: string
  reason: string
}

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('award.recommend'))

const {
  items: awards, loading, error, count, totalPages, page, pageSize, search, filters,
  load: loadAwards, applySearch, applyFilter, resetFilters, changePage, changePageSize,
} = useListQuery<AwardDecision>(
  (params) => api.get<PaginatedList<AwardDecision>>('/award-decisions/', { params }).then((res) => res.data),
  ['status'],
)

const rfqs = ref<Rfq[]>([])
const rfqNameById = computed(() => Object.fromEntries(rfqs.value.map((rfq) => [rfq.id, rfq.rfq_no])))

async function loadRfqs() {
  try {
    rfqs.value = await fetchAllPages<Rfq>('/rfqs/')
  } catch {
    rfqs.value = []
  }
}

async function load() {
  await Promise.all([loadAwards(), loadRfqs()])
}

const availableRfqs = computed(() => {
  const activeRfqIds = new Set(
    awards.value.filter((award) => ['draft', 'submitted', 'approved'].includes(award.status)).map((a) => a.rfq_id),
  )
  return rfqs.value.filter((rfq) => rfq.status === 'evaluating' && !activeRfqIds.has(rfq.id))
})

const showDetail = ref(false)
const detailAward = ref<AwardDecision | null>(null)
function openDetail(award: AwardDecision) {
  detailAward.value = award
  showDetail.value = true
}

// ---- 新增／編輯得標方案 ----
const showForm = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingAward = ref<AwardDecision | null>(null)
const formError = ref('')
const saving = ref(false)
const loadingCandidates = ref(false)

const form = reactive({ rfq_id: '' as number | '', selection_reason: '' })
const lines = ref<LineForm[]>([])

async function loadCandidates(rfqId: number, existing?: AwardDecision) {
  loadingCandidates.value = true
  formError.value = ''
  try {
    const result = (await api.post<EvaluationResult>(`/rfqs/${rfqId}/evaluate/`)).data
    lines.value = result.items.map((section) => {
      const existingLine = existing?.lines.find((line) => line.request_item_id === section.request_item_id)
      return {
        request_item_id: section.request_item_id,
        description: section.description,
        requested_quantity: section.requested_quantity,
        unit_of_measure: section.unit_of_measure,
        options: section.quotes,
        supplier_quote_item_id: existingLine?.supplier_quote_item_id ?? '',
        quantity: existingLine?.quantity ?? section.requested_quantity,
        reason: existingLine?.reason ?? '',
      }
    })
  } catch (reason) {
    formError.value = apiErrorMessage(reason, '無法載入評選結果，請先至 RFQ 頁面執行評選')
  } finally {
    loadingCandidates.value = false
  }
}

async function onSelectRfq() {
  lines.value = []
  if (form.rfq_id) await loadCandidates(Number(form.rfq_id))
}

function openCreate() {
  formMode.value = 'create'
  editingAward.value = null
  Object.assign(form, { rfq_id: '', selection_reason: '' })
  lines.value = []
  formError.value = ''
  showForm.value = true
}

async function openEdit(award: AwardDecision) {
  formMode.value = 'edit'
  editingAward.value = award
  Object.assign(form, { rfq_id: award.rfq_id, selection_reason: award.selection_reason })
  formError.value = ''
  showForm.value = true
  await loadCandidates(award.rfq_id, award)
}

function closeForm() {
  showForm.value = false
}

async function submitForm() {
  const payloadLines = lines.value
    .filter((line) => line.supplier_quote_item_id)
    .map((line) => ({
      request_item_id: line.request_item_id,
      supplier_quote_item_id: line.supplier_quote_item_id,
      quantity: line.quantity,
      reason: line.reason,
    }))
  if (payloadLines.length !== lines.value.length) {
    formError.value = '請為每一項需求品項選擇供應商報價'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    if (formMode.value === 'create') {
      await api.post('/award-decisions/', {
        rfq_id: form.rfq_id, selection_reason: form.selection_reason, lines: payloadLines,
      })
    } else if (editingAward.value) {
      await api.patch(`/award-decisions/${editingAward.value.id}/`, {
        selection_reason: form.selection_reason, lines: payloadLines,
      })
    }
    showForm.value = false
    await load()
  } catch (reason) {
    formError.value = apiErrorMessage(reason, '儲存得標方案失敗，請確認每筆分配數量已加總等於需求數量')
  } finally {
    saving.value = false
  }
}

async function submitAward(award: AwardDecision) {
  error.value = ''
  try {
    await api.post(`/award-decisions/${award.id}/submit/`)
    await load()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '提交得標方案失敗')
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="詢價與評選" title="得標方案">
    <template #actions>
      <button class="secondary-button" @click="load">重新整理</button>
      <button v-if="canManage" class="primary-button" @click="openCreate">新增得標方案</button>
    </template>
  </PageHeader>
  <section class="surface table-surface">
    <form class="filter-bar" @submit.prevent="applySearch">
      <input v-model="search" type="search" aria-label="搜尋得標方案" placeholder="搜尋 RFQ 編號或需求編號…" />
      <select aria-label="狀態篩選" :value="filters.status" @change="applyFilter('status', ($event.target as HTMLSelectElement).value)">
        <option value="">全部狀態</option>
        <option v-for="option in AWARD_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
      <button type="submit" class="secondary-button">搜尋</button>
      <button type="button" class="secondary-button" @click="resetFilters">清除條件</button>
    </form>
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="awards.length === 0" class="empty-state">目前沒有符合條件的得標方案資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>RFQ</th><th>版次</th><th>狀態</th><th>選商人</th><th>總金額(TWD)</th><th>提交時間</th><th></th></tr></thead>
        <tbody>
          <tr v-for="award in awards" :key="award.id">
            <td>{{ rfqNameById[award.rfq_id] || `#${award.rfq_id}` }}</td>
            <td>{{ award.revision }}</td>
            <td><StatusBadge :status="award.status" /></td>
            <td>{{ award.selected_by.name }}</td>
            <td>{{ formatMoney(award.total_amount_twd, 'TWD') }}</td>
            <td>{{ award.submitted_at ? formatDateTime(award.submitted_at) : '—' }}</td>
            <td>
              <button class="secondary-button" @click="openDetail(award)">詳情</button>
              <button v-if="canManage && award.status === 'draft'" class="secondary-button" @click="openEdit(award)">編輯</button>
              <button v-if="canManage && award.status === 'draft'" class="secondary-button" @click="submitAward(award)">提交</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ListPagination
      v-if="!loading && !error"
      :page="page" :page-size="pageSize" :total-pages="totalPages" :count="count"
      label="得標方案分頁" @change-page="changePage" @change-page-size="changePageSize"
    />
  </section>

  <div v-if="showDetail && detailAward" class="modal-backdrop" @click.self="showDetail = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="award-detail-title">
      <header class="modal-header">
        <div><span class="eyebrow">{{ rfqNameById[detailAward.rfq_id] || `#${detailAward.rfq_id}` }}</span><h2 id="award-detail-title">得標方案（第 {{ detailAward.revision }} 版）</h2></div>
        <button type="button" class="modal-close" aria-label="關閉" @click="showDetail = false">×</button>
      </header>
      <div class="modal-body">
        <dl class="detail-grid">
          <div><dt>狀態</dt><dd><StatusBadge :status="detailAward.status" /></dd></div>
          <div><dt>選商理由</dt><dd>{{ detailAward.selection_reason || '—' }}</dd></div>
          <div><dt>簽核案件</dt><dd>{{ detailAward.approval_case_id ?? '尚未建立' }}</dd></div>
        </dl>
        <h2 style="margin-top: 20px;">分配明細</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>供應商</th><th>數量</th><th>單位成本(TWD)</th><th>金額(TWD)</th><th>理由</th></tr></thead>
            <tbody>
              <tr v-for="line in detailAward.lines" :key="line.id">
                <td>{{ line.supplier_name }}</td>
                <td>{{ formatQuantity(line.quantity) }}</td>
                <td>{{ formatMoney(line.unit_cost_twd, 'TWD') }}</td>
                <td>{{ formatMoney(line.amount_twd, 'TWD') }}</td>
                <td>{{ line.reason || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>

  <div v-if="showForm" class="modal-backdrop" @click.self="closeForm">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="award-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">詢價與評選</span><h2 id="award-form-title">{{ formMode === 'create' ? '新增得標方案' : '編輯得標方案' }}</h2><p>依評選結果逐項選擇得標供應商；選擇非系統建議報價時須填寫選商理由。</p></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="closeForm">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitForm">
          <template v-if="formMode === 'create'">
            <label for="award-rfq">RFQ</label>
            <select id="award-rfq" v-model="form.rfq_id" required @change="onSelectRfq">
              <option value="" disabled>請選擇評選中的 RFQ</option>
              <option v-for="rfq in availableRfqs" :key="rfq.id" :value="rfq.id">{{ rfq.rfq_no }}（{{ rfq.request_no }}）</option>
            </select>
          </template>

          <label for="award-reason">選商理由（選擇非系統建議報價時必填）</label>
          <textarea id="award-reason" v-model="form.selection_reason" rows="2" />

          <p v-if="loadingCandidates" class="empty-state">載入評選結果中…</p>
          <template v-else>
            <div v-for="line in lines" :key="line.request_item_id" class="line-editor">
              <div class="line-editor-heading">
                <div class="line-editor-title"><strong>{{ line.description }}</strong><small>需求 {{ formatQuantity(line.requested_quantity, line.unit_of_measure) }}</small></div>
              </div>
              <div class="editor-grid">
                <div>
                  <label :for="`award-line-supplier-${line.request_item_id}`">得標供應商</label>
                  <select :id="`award-line-supplier-${line.request_item_id}`" v-model="line.supplier_quote_item_id" required>
                    <option value="" disabled>請選擇供應商報價</option>
                    <option v-for="option in line.options" :key="option.quote_item_id" :value="option.quote_item_id" :disabled="!option.eligible">
                      {{ option.supplier_name }} · {{ formatMoney(option.unit_price, option.currency) }}（總分 {{ option.total_score }}）{{ option.eligible ? '' : `（不合格：${option.eligibility_reason}）` }}
                    </option>
                  </select>
                </div>
                <div>
                  <label :for="`award-line-qty-${line.request_item_id}`">得標數量</label>
                  <input :id="`award-line-qty-${line.request_item_id}`" v-model="line.quantity" type="number" step="0.001" min="0" required />
                </div>
              </div>
            </div>
            <p v-if="lines.length === 0 && form.rfq_id" class="empty-state">此 RFQ 目前沒有可評選的有效報價。</p>
          </template>

          <p v-if="formError" class="error-message" role="alert">{{ formError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="closeForm">取消</button>
            <button type="submit" class="primary-button" :disabled="saving || lines.length === 0">{{ saving ? '儲存中…' : '儲存' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>
