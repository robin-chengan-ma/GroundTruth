<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { Rfq, RfqInvitedSupplier, RfqRequestItem, SupplierQuote } from '../types/api'
import { formatDateTime, formatMoney, formatQuantity } from '../utils/formatters'

interface ItemLineForm {
  request_item_id: number
  description: string
  requested_quantity: string
  unit_of_measure: string
  include: boolean
  quantity: string
  unit_price: string
  lead_time_days: string
  warranty_months: string
}

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('supplier_quote.manage'))

const quotes = ref<SupplierQuote[]>([])
const rfqs = ref<Rfq[]>([])
const rfqNameById = computed(() => Object.fromEntries(rfqs.value.map((rfq) => [rfq.id, rfq.rfq_no])))
const loading = ref(true)
const error = ref('')

const showDetail = ref(false)
const detailQuote = ref<SupplierQuote | null>(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [quoteResponse, rfqResponse] = await Promise.all([
      api.get<SupplierQuote[]>('/supplier-quotes/'),
      api.get<Rfq[]>('/rfqs/').catch(() => ({ data: [] as Rfq[] })),
    ])
    quotes.value = quoteResponse.data
    rfqs.value = rfqResponse.data
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法載入供應商報價清單（僅採購管理與稽核角色可查）')
  } finally {
    loading.value = false
  }
}

function openDetail(quote: SupplierQuote) {
  detailQuote.value = quote
  showDetail.value = true
}

// ---- 新增／改版報價 ----
const showForm = ref(false)
const formMode = ref<'create' | 'revise'>('create')
const revisingQuote = ref<SupplierQuote | null>(null)
const formError = ref('')
const saving = ref(false)

const availableRfqs = computed(() => rfqs.value.filter((rfq) => ['issued', 'collecting'].includes(rfq.status)))
const selectedRfq = ref<Rfq | null>(null)
const selectableSuppliers = computed<RfqInvitedSupplier[]>(() =>
  (selectedRfq.value?.invited_suppliers ?? []).filter((invitation) =>
    ['invited', 'responded'].includes(invitation.status),
  ),
)

const form = reactive({
  rfq_id: '' as number | '',
  rfq_supplier_id: '' as number | '',
  currency: 'TWD',
  exchange_rate_to_twd: '1',
  tax_amount: '0',
  shipping_amount: '0',
  discount_amount: '0',
  payment_terms: '',
  valid_until: '',
})
const lines = ref<ItemLineForm[]>([])

function buildLinesFromRequestItems(items: RfqRequestItem[], existing?: SupplierQuote) {
  lines.value = items.map((item) => {
    const existingItem = existing?.items.find((line) => line.request_item_id === item.id)
    return {
      request_item_id: item.id,
      description: item.product_name || item.description_snapshot,
      requested_quantity: item.quantity,
      unit_of_measure: item.unit_of_measure,
      include: Boolean(existingItem),
      quantity: existingItem?.quantity ?? item.quantity,
      unit_price: existingItem?.unit_price ?? '',
      lead_time_days: existingItem?.lead_time_days != null ? String(existingItem.lead_time_days) : '',
      warranty_months: existingItem?.warranty_months != null ? String(existingItem.warranty_months) : '',
    }
  })
}

function onSelectRfq() {
  selectedRfq.value = rfqs.value.find((rfq) => rfq.id === form.rfq_id) ?? null
  form.rfq_supplier_id = ''
  if (selectedRfq.value) buildLinesFromRequestItems(selectedRfq.value.request_items)
  else lines.value = []
}

async function openCreate() {
  formMode.value = 'create'
  revisingQuote.value = null
  Object.assign(form, {
    rfq_id: '', rfq_supplier_id: '', currency: 'TWD', exchange_rate_to_twd: '1',
    tax_amount: '0', shipping_amount: '0', discount_amount: '0', payment_terms: '', valid_until: '',
  })
  selectedRfq.value = null
  lines.value = []
  formError.value = ''
  showForm.value = true
}

async function openRevise(quote: SupplierQuote) {
  formMode.value = 'revise'
  revisingQuote.value = quote
  formError.value = ''
  Object.assign(form, {
    rfq_id: quote.rfq_id, rfq_supplier_id: '', currency: quote.currency,
    exchange_rate_to_twd: quote.exchange_rate_to_twd, tax_amount: quote.tax_amount,
    shipping_amount: quote.shipping_amount, discount_amount: quote.discount_amount,
    payment_terms: quote.payment_terms_snapshot, valid_until: quote.valid_until ? quote.valid_until.slice(0, 16) : '',
  })
  showForm.value = true
  try {
    const rfq = (await api.get<Rfq>(`/rfqs/${quote.rfq_id}/`)).data
    selectedRfq.value = rfq
    buildLinesFromRequestItems(rfq.request_items, quote)
  } catch (reason) {
    formError.value = apiErrorMessage(reason, '無法載入原始 RFQ 需求明細')
  }
}

function closeForm() {
  showForm.value = false
}

async function submitForm() {
  const items = lines.value
    .filter((line) => line.include)
    .map((line) => ({
      request_item_id: line.request_item_id,
      quantity: line.quantity,
      unit_price: line.unit_price,
      lead_time_days: line.lead_time_days ? Number(line.lead_time_days) : undefined,
      warranty_months: line.warranty_months ? Number(line.warranty_months) : undefined,
    }))
  if (items.length === 0) {
    formError.value = '請至少勾選一筆品項並填寫單價'
    return
  }
  saving.value = true
  formError.value = ''
  const payload = {
    currency: form.currency,
    exchange_rate_to_twd: form.exchange_rate_to_twd,
    tax_amount: form.tax_amount,
    shipping_amount: form.shipping_amount,
    discount_amount: form.discount_amount,
    payment_terms: form.payment_terms,
    valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null,
    items,
  }
  try {
    if (formMode.value === 'create') {
      if (!form.rfq_supplier_id) {
        formError.value = '請選擇 RFQ 與供應商'
        saving.value = false
        return
      }
      await api.post('/supplier-quotes/', { ...payload, rfq_supplier_id: form.rfq_supplier_id })
    } else if (revisingQuote.value) {
      await api.post(`/supplier-quotes/${revisingQuote.value.id}/revise/`, payload)
    }
    showForm.value = false
    await load()
  } catch (reason) {
    formError.value = apiErrorMessage(reason, '儲存報價失敗，請確認欄位內容')
  } finally {
    saving.value = false
  }
}

async function submitQuote(quote: SupplierQuote) {
  error.value = ''
  try {
    await api.post(`/supplier-quotes/${quote.id}/submit/`)
    await load()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '提交報價失敗')
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="詢價與評選" title="供應商報價">
    <template #actions>
      <button class="secondary-button" @click="load">重新整理</button>
      <button v-if="canManage" class="primary-button" @click="openCreate">新增報價</button>
    </template>
  </PageHeader>
  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="quotes.length === 0" class="empty-state">目前沒有供應商報價資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>報價單號</th><th>RFQ</th><th>供應商</th><th>狀態</th><th>版次</th><th>總金額(TWD)</th><th>提交時間</th><th></th></tr></thead>
        <tbody>
          <tr v-for="quote in quotes" :key="quote.id">
            <td>{{ quote.quote_no }}</td>
            <td>{{ rfqNameById[quote.rfq_id] || `#${quote.rfq_id}` }}</td>
            <td>{{ quote.supplier_name }}</td>
            <td><StatusBadge :status="quote.status" /></td>
            <td>{{ quote.revision }}</td>
            <td>{{ formatMoney(quote.landed_total_twd, 'TWD') }}</td>
            <td>{{ quote.submitted_at ? formatDateTime(quote.submitted_at) : '—' }}</td>
            <td>
              <button class="secondary-button" @click="openDetail(quote)">詳情</button>
              <button v-if="canManage && quote.status === 'draft'" class="secondary-button" @click="submitQuote(quote)">提交</button>
              <button v-if="canManage && ['submitted', 'accepted_for_evaluation'].includes(quote.status)" class="secondary-button" @click="openRevise(quote)">改版</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <div v-if="showDetail && detailQuote" class="modal-backdrop" @click.self="showDetail = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="quote-detail-title">
      <header class="modal-header">
        <div><span class="eyebrow">{{ detailQuote.supplier_name }}</span><h2 id="quote-detail-title">{{ detailQuote.quote_no }}（第 {{ detailQuote.revision }} 版）</h2></div>
        <button type="button" class="modal-close" aria-label="關閉" @click="showDetail = false">×</button>
      </header>
      <div class="modal-body">
        <dl class="detail-grid">
          <div><dt>幣別</dt><dd>{{ detailQuote.currency }}</dd></div>
          <div><dt>匯率</dt><dd>{{ detailQuote.exchange_rate_to_twd }}</dd></div>
          <div><dt>品項小計</dt><dd>{{ formatMoney(detailQuote.items_subtotal, detailQuote.currency) }}</dd></div>
          <div><dt>稅額</dt><dd>{{ formatMoney(detailQuote.tax_amount, detailQuote.currency) }}</dd></div>
          <div><dt>運費</dt><dd>{{ formatMoney(detailQuote.shipping_amount, detailQuote.currency) }}</dd></div>
          <div><dt>折扣</dt><dd>{{ formatMoney(detailQuote.discount_amount, detailQuote.currency) }}</dd></div>
          <div><dt>換算總額(TWD)</dt><dd>{{ formatMoney(detailQuote.landed_total_twd, 'TWD') }}</dd></div>
          <div><dt>付款條件</dt><dd>{{ detailQuote.payment_terms_snapshot || '—' }}</dd></div>
          <div><dt>報價有效期限</dt><dd>{{ detailQuote.valid_until ? formatDateTime(detailQuote.valid_until) : '不限' }}</dd></div>
        </dl>
        <h2 style="margin-top: 20px;">報價明細</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>數量</th><th>單價</th><th>小計</th><th>交期(天)</th><th>保固(月)</th></tr></thead>
            <tbody>
              <tr v-for="item in detailQuote.items" :key="item.id">
                <td>{{ formatQuantity(item.quantity) }}</td>
                <td>{{ formatMoney(item.unit_price, detailQuote.currency) }}</td>
                <td>{{ formatMoney(item.subtotal, detailQuote.currency) }}</td>
                <td>{{ item.lead_time_days ?? '—' }}</td>
                <td>{{ item.warranty_months ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>

  <div v-if="showForm" class="modal-backdrop" @click.self="closeForm">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="quote-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">詢價與評選</span><h2 id="quote-form-title">{{ formMode === 'create' ? '新增供應商報價' : `改版報價：${revisingQuote?.quote_no}` }}</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="closeForm">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitForm">
          <template v-if="formMode === 'create'">
            <div class="editor-grid">
              <div>
                <label for="quote-rfq">RFQ</label>
                <select id="quote-rfq" v-model="form.rfq_id" required @change="onSelectRfq">
                  <option value="" disabled>請選擇收件中的 RFQ</option>
                  <option v-for="rfq in availableRfqs" :key="rfq.id" :value="rfq.id">{{ rfq.rfq_no }}（{{ rfq.request_no }}）</option>
                </select>
              </div>
              <div>
                <label for="quote-supplier">供應商</label>
                <select id="quote-supplier" v-model="form.rfq_supplier_id" :disabled="!selectedRfq" required>
                  <option value="" disabled>請選擇供應商</option>
                  <option v-for="invitation in selectableSuppliers" :key="invitation.rfq_supplier_id" :value="invitation.rfq_supplier_id">{{ invitation.supplier_name }}</option>
                </select>
              </div>
            </div>
          </template>

          <div class="three-columns editor-grid">
            <div>
              <label for="quote-currency">幣別</label>
              <input id="quote-currency" v-model="form.currency" required />
            </div>
            <div>
              <label for="quote-exchange-rate">匯率(對 TWD)</label>
              <input id="quote-exchange-rate" v-model="form.exchange_rate_to_twd" type="number" step="0.000001" min="0" required />
            </div>
            <div>
              <label for="quote-valid-until">報價有效期限（選填）</label>
              <input id="quote-valid-until" v-model="form.valid_until" type="datetime-local" />
            </div>
          </div>
          <div class="three-columns editor-grid">
            <div>
              <label for="quote-tax">稅額</label>
              <input id="quote-tax" v-model="form.tax_amount" type="number" step="0.01" min="0" />
            </div>
            <div>
              <label for="quote-shipping">運費</label>
              <input id="quote-shipping" v-model="form.shipping_amount" type="number" step="0.01" min="0" />
            </div>
            <div>
              <label for="quote-discount">折扣</label>
              <input id="quote-discount" v-model="form.discount_amount" type="number" step="0.01" min="0" />
            </div>
          </div>
          <label for="quote-payment-terms">付款條件</label>
          <input id="quote-payment-terms" v-model="form.payment_terms" />

          <h3 style="margin-top: 20px;">報價明細（勾選要回覆的品項）</h3>
          <p v-if="lines.length === 0" class="empty-state">請先選擇 RFQ 以載入需求明細。</p>
          <div v-for="line in lines" v-else :key="line.request_item_id" class="line-editor">
            <div class="line-editor-heading">
              <label class="line-editor-title"><input v-model="line.include" type="checkbox" /> {{ line.description }}（需求 {{ formatQuantity(line.requested_quantity, line.unit_of_measure) }}）</label>
            </div>
            <div v-if="line.include" class="three-columns editor-grid">
              <div>
                <label :for="`line-qty-${line.request_item_id}`">報價數量</label>
                <input :id="`line-qty-${line.request_item_id}`" v-model="line.quantity" type="number" step="0.001" min="0" required />
              </div>
              <div>
                <label :for="`line-price-${line.request_item_id}`">單價</label>
                <input :id="`line-price-${line.request_item_id}`" v-model="line.unit_price" type="number" step="0.01" min="0" required />
              </div>
              <div>
                <label :for="`line-lead-${line.request_item_id}`">交期(天)</label>
                <input :id="`line-lead-${line.request_item_id}`" v-model="line.lead_time_days" type="number" min="0" />
              </div>
            </div>
          </div>

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
