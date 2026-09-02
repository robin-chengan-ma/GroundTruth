<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { GoodsReceipt, InspectionVarianceActionType, InspectionVarianceCase } from '../types/api'
import { formatDateTime, formatQuantity } from '../utils/formatters'

interface CandidateInspection {
  quality_inspection_id: number
  label: string
  variance_quantity: string
}
interface LineForm {
  action_type: InspectionVarianceActionType
  quantity: string
  reason: string
}

const ACTION_LABELS: Record<InspectionVarianceActionType, string> = {
  replacement: '補交', return: '退貨', credit: '折讓', waive: '免計較',
}

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('purchase_order.manage'))

const cases = ref<InspectionVarianceCase[]>([])
const loading = ref(true)
const error = ref('')

const candidates = ref<CandidateInspection[]>([])
const candidatesError = ref('')

async function loadCandidates() {
  candidatesError.value = ''
  try {
    const receipts = (await api.get<GoodsReceipt[]>('/goods-receipts/')).data
    const cased = new Set(cases.value.map((item) => item.quality_inspection_id))
    const found: CandidateInspection[] = []
    for (const receipt of receipts) {
      for (const item of receipt.items) {
        if (!item.inspection) continue
        const varianceQty = Number(item.inspection.defective_quantity) + Number(item.inspection.rejected_quantity)
        if (varianceQty <= 0 || cased.has(item.inspection.id)) continue
        found.push({
          quality_inspection_id: item.inspection.id,
          label: `${receipt.receipt_no} · ${item.product_name}`,
          variance_quantity: varianceQty.toFixed(3),
        })
      }
    }
    candidates.value = found
  } catch (reason) {
    candidatesError.value = apiErrorMessage(reason, '無法載入待處理驗收差異清單，可改用手動輸入品質驗收編號')
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    cases.value = (await api.get<InspectionVarianceCase[]>('/inspection-variances/')).data
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法載入驗收差異案件清單')
  } finally {
    loading.value = false
  }
  await loadCandidates()
}

const showDetail = ref(false)
const detail = ref<InspectionVarianceCase | null>(null)
function openDetail(item: InspectionVarianceCase) {
  detail.value = item
  showDetail.value = true
}

// ---- 新增／編輯差異案件 ----
const showForm = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingCase = ref<InspectionVarianceCase | null>(null)
const formError = ref('')
const saving = ref(false)
const form = reactive({ quality_inspection_id: '' as number | '', manual_inspection_id: '' })
const lines = ref<LineForm[]>([])

function addLine() {
  lines.value.push({ action_type: 'replacement', quantity: '', reason: '' })
}

function removeLine(index: number) {
  lines.value.splice(index, 1)
}

function openCreate() {
  formMode.value = 'create'
  editingCase.value = null
  Object.assign(form, { quality_inspection_id: '', manual_inspection_id: '' })
  lines.value = [{ action_type: 'replacement', quantity: '', reason: '' }]
  formError.value = ''
  showForm.value = true
}

function openEdit(item: InspectionVarianceCase) {
  formMode.value = 'edit'
  editingCase.value = item
  lines.value = item.lines
    .filter((line) => line.status === 'pending')
    .map((line) => ({ action_type: line.action_type, quantity: line.quantity, reason: line.reason }))
  if (lines.value.length === 0) lines.value.push({ action_type: 'replacement', quantity: '', reason: '' })
  formError.value = ''
  showForm.value = true
}

function closeForm() {
  showForm.value = false
}

async function submitForm() {
  const payloadLines = lines.value
    .filter((line) => line.quantity && line.reason)
    .map((line) => ({ action_type: line.action_type, quantity: line.quantity, reason: line.reason }))
  if (payloadLines.length === 0) {
    formError.value = '請至少填寫一筆處理明細（數量與理由皆為必填）'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    if (formMode.value === 'create') {
      const inspectionId = form.quality_inspection_id || Number(form.manual_inspection_id)
      if (!inspectionId) {
        formError.value = '請選擇或輸入品質驗收編號'
        saving.value = false
        return
      }
      await api.post('/inspection-variances/', { quality_inspection_id: inspectionId, lines: payloadLines })
    } else if (editingCase.value) {
      await api.put(`/inspection-variances/${editingCase.value.id}/`, {
        version: editingCase.value.version, lines: payloadLines,
      })
    }
    showForm.value = false
    await load()
  } catch (reason) {
    formError.value = apiErrorMessage(reason, '儲存差異案件失敗，請確認處理數量總和未超過差異數量')
  } finally {
    saving.value = false
  }
}

async function submitCase(item: InspectionVarianceCase) {
  error.value = ''
  try {
    await api.post(`/inspection-variances/${item.id}/submit/`, { version: item.version })
    await load()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '送出差異案件失敗')
  }
}

async function completeLine(item: InspectionVarianceCase, lineId: number) {
  error.value = ''
  try {
    await api.post(`/inspection-variances/${item.id}/complete-line/`, { line_id: lineId, version: item.version })
    await load()
    if (detail.value?.id === item.id) detail.value = cases.value.find((c) => c.id === item.id) ?? null
  } catch (reason) {
    error.value = apiErrorMessage(reason, '結案處理明細失敗')
  }
}

async function closeCase(item: InspectionVarianceCase) {
  error.value = ''
  try {
    await api.post(`/inspection-variances/${item.id}/close/`, { version: item.version })
    await load()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '結案差異案件失敗')
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="訂單與到貨" title="驗收差異">
    <template #actions>
      <button class="secondary-button" @click="load">重新整理</button>
      <button v-if="canManage" class="primary-button" @click="openCreate">新增差異案件</button>
    </template>
  </PageHeader>
  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="cases.length === 0" class="empty-state">目前沒有驗收差異案件。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>品項</th><th>供應商</th><th>差異數量</th><th>狀態</th><th>建立人</th><th></th></tr></thead>
        <tbody>
          <tr v-for="item in cases" :key="item.id">
            <td>{{ item.product.name }}</td>
            <td>{{ item.supplier.name }}</td>
            <td>{{ formatQuantity(item.variance_quantity) }}</td>
            <td><StatusBadge :status="item.status" /></td>
            <td>{{ item.created_by.name }}</td>
            <td>
              <button class="secondary-button" @click="openDetail(item)">詳情</button>
              <button v-if="canManage && item.status === 'draft'" class="secondary-button" @click="openEdit(item)">編輯</button>
              <button v-if="canManage && item.status === 'draft'" class="secondary-button" @click="submitCase(item)">送出</button>
              <button v-if="canManage && item.status === 'open'" class="secondary-button" @click="closeCase(item)">結案</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <div v-if="showDetail && detail" class="modal-backdrop" @click.self="showDetail = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="variance-detail-title">
      <header class="modal-header">
        <div><span class="eyebrow">{{ detail.supplier.name }}</span><h2 id="variance-detail-title">{{ detail.product.name }} 驗收差異</h2></div>
        <button type="button" class="modal-close" aria-label="關閉" @click="showDetail = false">×</button>
      </header>
      <div class="modal-body">
        <dl class="detail-grid">
          <div><dt>狀態</dt><dd><StatusBadge :status="detail.status" /></dd></div>
          <div><dt>差異數量</dt><dd>{{ formatQuantity(detail.variance_quantity) }}</dd></div>
          <div><dt>送出時間</dt><dd>{{ detail.submitted_at ? formatDateTime(detail.submitted_at) : '—' }}</dd></div>
        </dl>
        <h2 style="margin-top: 20px;">處理明細</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>類型</th><th>數量</th><th>理由</th><th>狀態</th><th></th></tr></thead>
            <tbody>
              <tr v-for="line in detail.lines" :key="line.id">
                <td>{{ ACTION_LABELS[line.action_type] }}</td>
                <td>{{ formatQuantity(line.quantity) }}</td>
                <td>{{ line.reason }}</td>
                <td><StatusBadge :status="line.status" /></td>
                <td><button v-if="canManage && detail.status === 'open' && line.status === 'pending'" class="secondary-button" @click="completeLine(detail, line.id)">標記結案</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>

  <div v-if="showForm" class="modal-backdrop" @click.self="closeForm">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="variance-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">訂單與到貨</span><h2 id="variance-form-title">{{ formMode === 'create' ? '新增驗收差異案件' : '編輯差異案件' }}</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="closeForm">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitForm">
          <template v-if="formMode === 'create'">
            <p v-if="candidatesError" class="warning-panel">{{ candidatesError }}</p>
            <template v-if="candidates.length">
              <label for="variance-inspection">品質驗收（來源收貨批次 · 品項）</label>
              <select id="variance-inspection" v-model="form.quality_inspection_id">
                <option value="">請選擇</option>
                <option v-for="candidate in candidates" :key="candidate.quality_inspection_id" :value="candidate.quality_inspection_id">
                  {{ candidate.label }}（差異 {{ candidate.variance_quantity }}）
                </option>
              </select>
            </template>
            <label for="variance-manual-id">或手動輸入品質驗收編號</label>
            <input id="variance-manual-id" v-model="form.manual_inspection_id" type="number" min="1" />
          </template>

          <h3 style="margin-top: 20px;">處理明細</h3>
          <div v-for="(line, index) in lines" :key="index" class="line-editor">
            <div class="line-editor-heading">
              <span>處理明細 {{ index + 1 }}</span>
              <button v-if="lines.length > 1" type="button" class="secondary-button remove-item-button" @click="removeLine(index)">移除</button>
            </div>
            <div class="three-columns editor-grid">
              <div>
                <label :for="`variance-action-${index}`">處理類型</label>
                <select :id="`variance-action-${index}`" v-model="line.action_type">
                  <option value="replacement">補交</option>
                  <option value="return">退貨</option>
                  <option value="credit">折讓</option>
                  <option value="waive">免計較</option>
                </select>
              </div>
              <div>
                <label :for="`variance-qty-${index}`">數量</label>
                <input :id="`variance-qty-${index}`" v-model="line.quantity" type="number" step="0.001" min="0" required />
              </div>
              <div>
                <label :for="`variance-reason-${index}`">理由</label>
                <input :id="`variance-reason-${index}`" v-model="line.reason" required />
              </div>
            </div>
          </div>
          <button type="button" class="secondary-button" @click="addLine">新增一筆處理明細</button>

          <p v-if="formError" class="error-message" role="alert">{{ formError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="closeForm">取消</button>
            <button type="submit" class="primary-button" :disabled="saving">{{ saving ? '儲存中…' : '儲存' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>
