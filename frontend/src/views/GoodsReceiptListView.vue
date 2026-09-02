<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { GoodsReceipt, PurchaseOrder } from '../types/api'
import { formatDateTime, formatQuantity } from '../utils/formatters'

interface ReceiptLineForm {
  purchase_order_item_id: number
  description: string
  ordered_quantity: string
  include: boolean
  received_quantity: string
  lot_no: string
}
interface InspectionLineForm {
  receipt_item_id: number
  description: string
  received_quantity: string
  accepted_quantity: string
  defective_quantity: string
  rejected_quantity: string
  defect_details: string
  notes: string
}

const auth = useAuthStore()
const canRecord = computed(() => auth.hasPermission('receipt.record'))
const canInspect = computed(() => auth.hasPermission('inspection.decide'))

const receipts = ref<GoodsReceipt[]>([])
const purchaseOrders = ref<PurchaseOrder[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [receiptResponse, orderResponse] = await Promise.all([
      api.get<GoodsReceipt[]>('/goods-receipts/'),
      api.get<PurchaseOrder[]>('/purchase-orders/').catch(() => ({ data: [] as PurchaseOrder[] })),
    ])
    receipts.value = receiptResponse.data
    purchaseOrders.value = orderResponse.data
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法載入收貨單清單')
  } finally {
    loading.value = false
  }
}

const showDetail = ref(false)
const detail = ref<GoodsReceipt | null>(null)
function openDetail(receipt: GoodsReceipt) {
  detail.value = receipt
  showDetail.value = true
}

// ---- 新增收貨單 ----
const availableOrders = computed(() =>
  purchaseOrders.value.filter((order) => ['issued', 'partially_received'].includes(order.status)),
)
const showCreateForm = ref(false)
const createSaving = ref(false)
const createError = ref('')
const createForm = reactive({ purchase_order_id: '' as number | '' })
const receiptLines = ref<ReceiptLineForm[]>([])

function onSelectOrder() {
  const order = purchaseOrders.value.find((item) => item.id === createForm.purchase_order_id)
  receiptLines.value = order
    ? order.items.map((item) => ({
        purchase_order_item_id: item.id,
        description: item.product_name,
        ordered_quantity: item.quantity,
        include: false,
        received_quantity: item.quantity,
        lot_no: '',
      }))
    : []
}

function openCreate() {
  Object.assign(createForm, { purchase_order_id: '' })
  receiptLines.value = []
  createError.value = ''
  showCreateForm.value = true
}

async function submitCreate() {
  const items = receiptLines.value
    .filter((line) => line.include)
    .map((line) => ({
      purchase_order_item_id: line.purchase_order_item_id,
      received_quantity: line.received_quantity,
      lot_no: line.lot_no,
    }))
  if (!createForm.purchase_order_id || items.length === 0) {
    createError.value = '請選擇採購單並至少勾選一筆實收明細'
    return
  }
  createSaving.value = true
  createError.value = ''
  try {
    await api.post('/goods-receipts/', { purchase_order_id: createForm.purchase_order_id, items })
    showCreateForm.value = false
    await load()
  } catch (reason) {
    createError.value = apiErrorMessage(reason, '建立收貨單失敗')
  } finally {
    createSaving.value = false
  }
}

async function submitReceipt(receipt: GoodsReceipt) {
  error.value = ''
  try {
    await api.post(`/goods-receipts/${receipt.id}/submit/`, { version: receipt.version })
    await load()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '送驗失敗')
  }
}

// ---- 品質驗收 ----
const showInspectForm = ref(false)
const inspectingReceipt = ref<GoodsReceipt | null>(null)
const inspectSaving = ref(false)
const inspectError = ref('')
const inspectLines = ref<InspectionLineForm[]>([])

function openInspect(receipt: GoodsReceipt) {
  inspectingReceipt.value = receipt
  inspectLines.value = receipt.items.map((item) => ({
    receipt_item_id: item.id,
    description: item.product_name,
    received_quantity: item.received_quantity,
    accepted_quantity: item.received_quantity,
    defective_quantity: '0',
    rejected_quantity: '0',
    defect_details: '',
    notes: '',
  }))
  inspectError.value = ''
  showInspectForm.value = true
}

async function submitInspect() {
  if (!inspectingReceipt.value) return
  inspectSaving.value = true
  inspectError.value = ''
  try {
    await api.post(`/goods-receipts/${inspectingReceipt.value.id}/inspect/`, {
      version: inspectingReceipt.value.version,
      items: inspectLines.value.map((line) => ({
        receipt_item_id: line.receipt_item_id,
        accepted_quantity: line.accepted_quantity,
        defective_quantity: line.defective_quantity,
        rejected_quantity: line.rejected_quantity,
        defect_details: line.defect_details,
        notes: line.notes,
      })),
    })
    showInspectForm.value = false
    await load()
  } catch (reason) {
    inspectError.value = apiErrorMessage(reason, '驗收失敗，請確認合格＋瑕疵＋拒收數量等於實收數量')
  } finally {
    inspectSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="訂單與到貨" title="收貨與驗收">
    <template #actions>
      <button class="secondary-button" @click="load">重新整理</button>
      <button v-if="canRecord" class="primary-button" @click="openCreate">新增收貨單</button>
    </template>
  </PageHeader>
  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="receipts.length === 0" class="empty-state">目前沒有收貨單資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>收貨單號</th><th>採購單</th><th>供應商</th><th>狀態</th><th>收貨人</th><th>收貨時間</th><th></th></tr></thead>
        <tbody>
          <tr v-for="receipt in receipts" :key="receipt.id">
            <td>{{ receipt.receipt_no }}</td>
            <td>{{ receipt.po_no }}</td>
            <td>{{ receipt.supplier.name }}</td>
            <td><StatusBadge :status="receipt.status" /></td>
            <td>{{ receipt.received_by?.name || '—' }}</td>
            <td>{{ receipt.received_at ? formatDateTime(receipt.received_at) : '—' }}</td>
            <td>
              <button class="secondary-button" @click="openDetail(receipt)">詳情</button>
              <button v-if="canRecord && receipt.status === 'draft'" class="secondary-button" @click="submitReceipt(receipt)">送驗</button>
              <button v-if="canInspect && receipt.status === 'inspecting'" class="secondary-button" @click="openInspect(receipt)">品質驗收</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <div v-if="showDetail && detail" class="modal-backdrop" @click.self="showDetail = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="receipt-detail-title">
      <header class="modal-header">
        <div><span class="eyebrow">{{ detail.supplier.name }}</span><h2 id="receipt-detail-title">{{ detail.receipt_no }}</h2></div>
        <button type="button" class="modal-close" aria-label="關閉" @click="showDetail = false">×</button>
      </header>
      <div class="modal-body">
        <dl class="detail-grid">
          <div><dt>狀態</dt><dd><StatusBadge :status="detail.status" /></dd></div>
          <div><dt>採購單</dt><dd>{{ detail.po_no }}</dd></div>
          <div><dt>收貨時間</dt><dd>{{ detail.received_at ? formatDateTime(detail.received_at) : '—' }}</dd></div>
        </dl>
        <h2 style="margin-top: 20px;">收貨與驗收明細</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>品項</th><th>實收數量</th><th>批號</th><th>驗收狀態</th><th>合格</th><th>瑕疵</th><th>拒收</th></tr></thead>
            <tbody>
              <tr v-for="item in detail.items" :key="item.id">
                <td>{{ item.product_name }}</td>
                <td>{{ formatQuantity(item.received_quantity) }}</td>
                <td>{{ item.lot_no || '—' }}</td>
                <td><StatusBadge v-if="item.inspection" :status="item.inspection.status" /><span v-else>尚未驗收</span></td>
                <td>{{ item.inspection ? formatQuantity(item.inspection.accepted_quantity) : '—' }}</td>
                <td>{{ item.inspection ? formatQuantity(item.inspection.defective_quantity) : '—' }}</td>
                <td>{{ item.inspection ? formatQuantity(item.inspection.rejected_quantity) : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>

  <div v-if="showCreateForm" class="modal-backdrop" @click.self="showCreateForm = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="receipt-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">訂單與到貨</span><h2 id="receipt-form-title">新增收貨單</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="showCreateForm = false">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitCreate">
          <label for="receipt-po">採購單</label>
          <select id="receipt-po" v-model="createForm.purchase_order_id" required @change="onSelectOrder">
            <option value="" disabled>請選擇已發出的採購單</option>
            <option v-for="order in availableOrders" :key="order.id" :value="order.id">{{ order.po_no }}（{{ order.supplier.name }}）</option>
          </select>

          <div v-for="line in receiptLines" :key="line.purchase_order_item_id" class="line-editor">
            <div class="line-editor-heading">
              <label class="line-editor-title"><input v-model="line.include" type="checkbox" /> {{ line.description }}（訂購 {{ formatQuantity(line.ordered_quantity) }}）</label>
            </div>
            <div v-if="line.include" class="editor-grid">
              <div>
                <label :for="`receipt-qty-${line.purchase_order_item_id}`">實收數量</label>
                <input :id="`receipt-qty-${line.purchase_order_item_id}`" v-model="line.received_quantity" type="number" step="0.001" min="0" required />
              </div>
              <div>
                <label :for="`receipt-lot-${line.purchase_order_item_id}`">批號（選填）</label>
                <input :id="`receipt-lot-${line.purchase_order_item_id}`" v-model="line.lot_no" />
              </div>
            </div>
          </div>

          <p v-if="createError" class="error-message" role="alert">{{ createError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="showCreateForm = false">取消</button>
            <button type="submit" class="primary-button" :disabled="createSaving">{{ createSaving ? '儲存中…' : '建立' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>

  <div v-if="showInspectForm && inspectingReceipt" class="modal-backdrop" @click.self="showInspectForm = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="inspect-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">{{ inspectingReceipt.receipt_no }}</span><h2 id="inspect-form-title">品質驗收</h2><p>合格＋瑕疵＋拒收數量必須等於實收數量；有瑕疵數量時必須填寫瑕疵內容。</p></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="showInspectForm = false">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitInspect">
          <div v-for="line in inspectLines" :key="line.receipt_item_id" class="line-editor">
            <div class="line-editor-heading"><strong>{{ line.description }}</strong><small>實收 {{ formatQuantity(line.received_quantity) }}</small></div>
            <div class="three-columns editor-grid">
              <div>
                <label :for="`inspect-accepted-${line.receipt_item_id}`">合格數量</label>
                <input :id="`inspect-accepted-${line.receipt_item_id}`" v-model="line.accepted_quantity" type="number" step="0.001" min="0" required />
              </div>
              <div>
                <label :for="`inspect-defective-${line.receipt_item_id}`">瑕疵數量</label>
                <input :id="`inspect-defective-${line.receipt_item_id}`" v-model="line.defective_quantity" type="number" step="0.001" min="0" required />
              </div>
              <div>
                <label :for="`inspect-rejected-${line.receipt_item_id}`">拒收數量</label>
                <input :id="`inspect-rejected-${line.receipt_item_id}`" v-model="line.rejected_quantity" type="number" step="0.001" min="0" required />
              </div>
            </div>
            <label :for="`inspect-defect-details-${line.receipt_item_id}`">瑕疵內容（有瑕疵數量時必填）</label>
            <input :id="`inspect-defect-details-${line.receipt_item_id}`" v-model="line.defect_details" />
            <label :for="`inspect-notes-${line.receipt_item_id}`">備註（選填）</label>
            <input :id="`inspect-notes-${line.receipt_item_id}`" v-model="line.notes" />
          </div>
          <p v-if="inspectError" class="error-message" role="alert">{{ inspectError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="showInspectForm = false">取消</button>
            <button type="submit" class="primary-button" :disabled="inspectSaving">{{ inspectSaving ? '送出中…' : '送出驗收結果' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>
