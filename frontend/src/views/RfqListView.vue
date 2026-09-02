<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import ListPagination from '../components/ListPagination.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useListQuery } from '../composables/useListQuery'
import { useAuthStore } from '../stores/auth'
import type { PaginatedList, Rfq } from '../types/api'
import { formatDateTime, formatMoney, formatQuantity } from '../utils/formatters'

const RFQ_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'issued', label: '已發出' },
  { value: 'collecting', label: '收件中' },
  { value: 'evaluating', label: '評選中' },
  { value: 'closed', label: '已結案' },
  { value: 'cancelled', label: '已取消' },
]

interface EvaluationQuoteRow {
  quote_id: number
  quote_item_id: number
  supplier_id: number
  supplier_name: string
  quoted_quantity: string
  unit_price: string
  currency: string
  allocated_unit_cost_twd: string
  eligible: boolean
  eligibility_reason: string
  total_score: string
  data_completeness_pct: string
}
interface EvaluationItemSection {
  request_item_id: number
  line_no: number
  description: string
  requested_quantity: string
  unit_of_measure: string
  quotes: EvaluationQuoteRow[]
  recommended_supplier_names: string[]
}
interface EvaluationQuoteSummary {
  quote_id: number
  supplier_id: number
  supplier_name: string
  covers_all_items: boolean
  eligible_for_whole_request: boolean
  whole_request_recommended: boolean
  total_score: string
  data_completeness_pct: string
}
interface EvaluationResult {
  rfq_id: number
  rfq_no: string
  status: string
  comparison_basis: string
  items: EvaluationItemSection[]
  quote_summaries: EvaluationQuoteSummary[]
}

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('rfq.manage'))

const {
  items: rfqs, loading, error, count, totalPages, page, pageSize, search, filters,
  load, applySearch, applyFilter, resetFilters, changePage, changePageSize,
} = useListQuery<Rfq>(
  (params) => api.get<PaginatedList<Rfq>>('/rfqs/', { params }).then((res) => res.data),
  ['status'],
)

const detail = ref<Rfq | null>(null)
const showDetail = ref(false)
const detailError = ref('')

const issuing = ref(false)
const issueError = ref('')
const issueForm = reactive({ response_due_at: '' })

const evaluating = ref(false)
const evaluateError = ref('')
const evaluation = ref<EvaluationResult | null>(null)

function openDetail(rfq: Rfq) {
  detail.value = rfq
  showDetail.value = true
  detailError.value = ''
  issueError.value = ''
  evaluateError.value = ''
  evaluation.value = null
  issueForm.response_due_at = ''
}

function closeDetail() {
  showDetail.value = false
  detail.value = null
}

async function submitIssue() {
  if (!detail.value || !issueForm.response_due_at) {
    issueError.value = '請選擇報價截止時間'
    return
  }
  issuing.value = true
  issueError.value = ''
  try {
    const response = await api.post<Rfq>(`/rfqs/${detail.value.id}/issue/`, {
      version: detail.value.version,
      response_due_at: new Date(issueForm.response_due_at).toISOString(),
    })
    detail.value = response.data
    await load()
  } catch (reason) {
    issueError.value = apiErrorMessage(reason, '發出 RFQ 失敗')
  } finally {
    issuing.value = false
  }
}

async function runEvaluate() {
  if (!detail.value) return
  evaluating.value = true
  evaluateError.value = ''
  try {
    evaluation.value = (await api.post<EvaluationResult>(`/rfqs/${detail.value.id}/evaluate/`)).data
    await load()
  } catch (reason) {
    evaluateError.value = apiErrorMessage(reason, '執行評選失敗，需至少一筆已提交且有效的報價')
  } finally {
    evaluating.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="詢價與評選" title="RFQ">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>
  <section class="surface table-surface">
    <form class="filter-bar" @submit.prevent="applySearch">
      <input v-model="search" type="search" aria-label="搜尋 RFQ" placeholder="搜尋 RFQ 編號、需求編號或受邀供應商…" />
      <select aria-label="狀態篩選" :value="filters.status" @change="applyFilter('status', ($event.target as HTMLSelectElement).value)">
        <option value="">全部狀態</option>
        <option v-for="option in RFQ_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
      <button type="submit" class="secondary-button">搜尋</button>
      <button type="button" class="secondary-button" @click="resetFilters">清除條件</button>
    </form>
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="rfqs.length === 0" class="empty-state">目前沒有符合條件的 RFQ 資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>RFQ 編號</th><th>需求編號</th><th>用途</th><th>狀態</th><th>回覆截止</th><th>受邀供應商</th><th></th></tr></thead>
        <tbody>
          <tr v-for="rfq in rfqs" :key="rfq.id">
            <td>{{ rfq.rfq_no }}</td>
            <td>{{ rfq.request_no }}</td>
            <td>{{ rfq.request_purpose || '—' }}</td>
            <td><StatusBadge :status="rfq.status" /></td>
            <td>{{ formatDateTime(rfq.response_due_at) }}</td>
            <td>{{ rfq.invited_suppliers.length }} 間</td>
            <td><button class="secondary-button" @click="openDetail(rfq)">查看詳情</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <ListPagination
      v-if="!loading && !error"
      :page="page" :page-size="pageSize" :total-pages="totalPages" :count="count"
      label="RFQ 分頁" @change-page="changePage" @change-page-size="changePageSize"
    />
  </section>

  <div v-if="showDetail && detail" class="modal-backdrop" @click.self="closeDetail">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="rfq-detail-title">
      <header class="modal-header">
        <div><span class="eyebrow">詢價與評選</span><h2 id="rfq-detail-title">{{ detail.rfq_no }}</h2><p>{{ detail.request_no }} · {{ detail.request_purpose || '—' }}</p></div>
        <button type="button" class="modal-close" aria-label="關閉" @click="closeDetail">×</button>
      </header>
      <div class="modal-body">
        <p v-if="detailError" class="error-message" role="alert">{{ detailError }}</p>

        <section class="detail-section">
          <header class="detail-heading"><h2>基本資訊</h2><StatusBadge :status="detail.status" /></header>
          <dl class="detail-grid">
            <div><dt>回覆截止</dt><dd>{{ formatDateTime(detail.response_due_at) }}</dd></div>
            <div><dt>版本</dt><dd>{{ detail.version }}</dd></div>
            <div><dt>修訂次數</dt><dd>{{ detail.revision }}</dd></div>
          </dl>
        </section>

        <section class="detail-section">
          <h2>需求明細</h2>
          <div class="table-scroll">
            <table>
              <thead><tr><th>行號</th><th>品項</th><th>需求數量</th></tr></thead>
              <tbody>
                <tr v-for="item in detail.request_items" :key="item.id">
                  <td>{{ item.line_no }}</td>
                  <td>{{ item.product_name || item.description_snapshot }}</td>
                  <td>{{ formatQuantity(item.quantity, item.unit_of_measure) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="detail-section">
          <h2>受邀供應商</h2>
          <div class="table-scroll">
            <table>
              <thead><tr><th>供應商</th><th>狀態</th><th>邀請時間</th><th>回覆時間</th></tr></thead>
              <tbody>
                <tr v-for="invitation in detail.invited_suppliers" :key="invitation.rfq_supplier_id">
                  <td>{{ invitation.supplier_name }}</td>
                  <td><StatusBadge :status="invitation.status" /></td>
                  <td>{{ formatDateTime(invitation.invited_at) }}</td>
                  <td>{{ invitation.responded_at ? formatDateTime(invitation.responded_at) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="detail-section">
          <h2>評選標準快照</h2>
          <p v-if="detail.criteria.length === 0" class="empty-state">尚未發出，無評選標準快照。</p>
          <div v-else class="table-scroll">
            <table>
              <thead><tr><th>準則</th><th>權重</th><th>計算方式</th></tr></thead>
              <tbody>
                <tr v-for="criterion in detail.criteria" :key="criterion.code">
                  <td>{{ criterion.label }}</td>
                  <td>{{ criterion.weight }}%</td>
                  <td>{{ criterion.calculation_method }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="canManage && detail.status === 'draft'" class="detail-section">
          <h2>發出 RFQ</h2>
          <form @submit.prevent="submitIssue">
            <label for="rfq-due-at">報價回覆截止時間</label>
            <input id="rfq-due-at" v-model="issueForm.response_due_at" type="datetime-local" required />
            <p v-if="issueError" class="error-message" role="alert">{{ issueError }}</p>
            <div class="form-actions">
              <button type="submit" class="primary-button" :disabled="issuing">{{ issuing ? '發出中…' : '發出 RFQ' }}</button>
            </div>
          </form>
        </section>

        <section v-if="canManage && ['issued', 'collecting', 'evaluating'].includes(detail.status)" class="detail-section">
          <header class="section-heading"><div><span class="eyebrow">比較評選</span><h3>逐項比較與整單建議</h3></div><button class="primary-button" @click="runEvaluate">{{ evaluating ? '評選中…' : '執行評選' }}</button></header>
          <p v-if="evaluateError" class="error-message" role="alert">{{ evaluateError }}</p>
          <template v-if="evaluation">
            <p class="muted-text" style="margin-top: 12px;">{{ evaluation.comparison_basis }}</p>
            <div v-for="section in evaluation.items" :key="section.request_item_id" class="detail-item">
              <header><div><span class="eyebrow">品項 {{ section.line_no }}</span><h3>{{ section.description }}</h3></div><strong>{{ formatQuantity(section.requested_quantity, section.unit_of_measure) }}</strong></header>
              <p v-if="section.recommended_supplier_names.length" class="muted-text">系統建議：{{ section.recommended_supplier_names.join('、') }}</p>
              <div class="table-scroll">
                <table>
                  <thead><tr><th>供應商</th><th>單價</th><th>換算單位成本(TWD)</th><th>總分</th><th>資料完整度</th><th>資格</th></tr></thead>
                  <tbody>
                    <tr v-for="row in section.quotes" :key="row.quote_item_id">
                      <td>{{ row.supplier_name }}</td>
                      <td>{{ formatMoney(row.unit_price, row.currency) }}</td>
                      <td>{{ formatMoney(row.allocated_unit_cost_twd, 'TWD') }}</td>
                      <td>{{ row.total_score }}</td>
                      <td>{{ row.data_completeness_pct }}%</td>
                      <td>{{ row.eligible ? '合格' : row.eligibility_reason }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <h3 style="margin-top: 20px;">整單彙總</h3>
            <div class="table-scroll">
              <table>
                <thead><tr><th>供應商</th><th>覆蓋全部品項</th><th>整單合格</th><th>整單建議</th><th>總分</th><th>資料完整度</th></tr></thead>
                <tbody>
                  <tr v-for="summary in evaluation.quote_summaries" :key="summary.quote_id">
                    <td>{{ summary.supplier_name }}</td>
                    <td>{{ summary.covers_all_items ? '是' : '否' }}</td>
                    <td>{{ summary.eligible_for_whole_request ? '是' : '否' }}</td>
                    <td>{{ summary.whole_request_recommended ? '★ 建議' : '—' }}</td>
                    <td>{{ summary.total_score }}</td>
                    <td>{{ summary.data_completeness_pct }}%</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="muted-text" style="margin-top: 12px;">評選結果已存檔；請至「得標方案」頁面依此建立得標分配。</p>
          </template>
        </section>
      </div>
    </section>
  </div>
</template>
