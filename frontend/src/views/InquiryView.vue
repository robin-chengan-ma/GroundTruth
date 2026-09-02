<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import type { DraftEstimate, Paginated, ProductOption, PurchaseCandidate, PurchaseCandidateItem, PurchaseDraft, SupplierOption, SupplierProductCoverageRow } from '../types/api'
import { formatMoney, formatQuantity } from '../utils/formatters'

const rawText = ref('')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const candidate = ref<PurchaseCandidate | null>(null)
const suppliers = ref<SupplierOption[]>([])
const products = ref<ProductOption[]>([])
const selectedSupplierIds = ref<number[]>([])
const coverageRows = ref<SupplierProductCoverageRow[]>([])
const draft = ref<PurchaseDraft | null>(null)
const estimate = ref<DraftEstimate | null>(null)
const successToast = ref('')
const resetNotice = ref('')
const inquiryInput = ref<HTMLTextAreaElement | null>(null)
let successTimer: ReturnType<typeof setTimeout> | null = null
let resetTimer: ReturnType<typeof setTimeout> | null = null

const canEstimate = computed(() => Boolean(candidate.value?.items.length
  && candidate.value.items.every((item) => item.product_id && Number(item.quantity) > 0)
  && selectedSupplierIds.value.length))
const estimateDisabledReason = computed(() => {
  if (!candidate.value || canEstimate.value) return ''
  if (!candidate.value.items.length) return '請至少保留一個採購品項。'
  if (candidate.value.items.some((item) => !item.product_id)) return '尚有品項未選擇正式品項，請先手動選擇或移除。'
  if (candidate.value.items.some((item) => Number(item.quantity) <= 0)) return '所有品項都必須填寫大於 0 的數量。'
  if (!selectedSupplierIds.value.length) return '請至少選擇一間候選供應商。'
  return ''
})
const rows = <T,>(data: Paginated<T> | T[]) => Array.isArray(data) ? data : data.results
const supplierHasPrice = (supplier: DraftEstimate['suppliers'][number]) => supplier.items.some((item) => item.available)
function dismissSuccess() {
  successToast.value = ''
  if (successTimer) clearTimeout(successTimer)
  successTimer = null
}

async function loadCatalogs() {
  try {
    const [supplierResponse, productResponse] = await Promise.all([
      api.get<Paginated<SupplierOption> | SupplierOption[]>('/suppliers/'),
      api.get<Paginated<ProductOption> | ProductOption[]>('/products/'),
    ])
    suppliers.value = rows(supplierResponse.data)
    products.value = rows(productResponse.data)
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法載入供應商與品項主檔')
  }
}

async function parseRequirement() {
  loading.value = true
  error.value = ''
  notice.value = ''
  draft.value = null
  estimate.value = null
  try {
    const response = await api.post<PurchaseCandidate>('/inquiries/parse/', { raw_text: rawText.value })
    candidate.value = response.data
    selectedSupplierIds.value = response.data.supplier_candidates.map((row) => row.supplier_id).filter((id): id is number => id !== null)
    coverageRows.value = response.data.supplier_product_coverage ?? []
    notice.value = response.data.assistant_message
  } catch (reason) {
    error.value = apiErrorMessage(reason, '需求解析失敗')
  } finally { loading.value = false }
}

function addItem() {
  candidate.value?.items.push({ product_id: null, product_name: '', quantity: '1', unit_of_measure: 'EA', specifications: {} })
  estimate.value = null
}
async function refreshCoverage() {
  if (!candidate.value) return
  const items = candidate.value.items
    .filter((item) => item.product_id && Number(item.quantity) > 0)
    .map((item) => ({ product_id: item.product_id, quantity: item.quantity }))
  if (!selectedSupplierIds.value.length || !items.length) {
    coverageRows.value = []
    return
  }
  try {
    const response = await api.post<{ rows: SupplierProductCoverageRow[] }>(
      '/supplier-product-coverage/',
      { currency: candidate.value.currency, supplier_ids: selectedSupplierIds.value, items },
    )
    coverageRows.value = response.data.rows
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法更新供應能力對照')
  }
}
const coverageProducts = computed(() => {
  const grouped = new Map<number, { product_name: string; rows: SupplierProductCoverageRow[] }>()
  for (const row of coverageRows.value) {
    const group = grouped.get(row.product_id) ?? { product_name: row.product_name, rows: [] }
    group.rows.push(row)
    grouped.set(row.product_id, group)
  }
  return [...grouped.entries()].map(([product_id, value]) => ({ product_id, ...value }))
})
function itemSummary(item: PurchaseCandidateItem) {
  return `${item.product_name || '未命名品項'}／數量 ${item.quantity ?? '未填'} ${item.unit_of_measure || ''}`.trim()
}
function recognizedItemSummary(item: PurchaseCandidateItem) {
  const parts = [itemSummary(item)]
  if (item.specifications.material) parts.push(`材質：${item.specifications.material}`)
  if (item.specifications.size) parts.push(`尺寸：${item.specifications.size}`)
  if (item.specifications.features) parts.push(`特色：${item.specifications.features}`)
  return parts.join('／')
}
async function resetToNaturalInput(message: string) {
  rawText.value = ''
  candidate.value = null
  selectedSupplierIds.value = []
  coverageRows.value = []
  draft.value = null
  estimate.value = null
  notice.value = ''
  error.value = ''
  resetNotice.value = message
  if (resetTimer) clearTimeout(resetTimer)
  resetTimer = setTimeout(() => { resetNotice.value = '' }, 5000)
  await nextTick()
  inquiryInput.value?.focus()
}
async function removeItem(index: number) {
  if (!candidate.value) return
  const item = candidate.value.items[index]
  if (!item || !window.confirm(`確定要移除「${itemSummary(item)}」嗎？`)) return
  if (candidate.value.items.length > 1) {
    candidate.value.items.splice(index, 1)
    estimate.value = null
    await refreshCoverage()
    return
  }
  loading.value = true
  try {
    if (draft.value) await api.delete(`/purchase-request-drafts/${draft.value.id}/`)
    await resetToNaturalInput('已移除最後一個品項，請重新輸入採購需求。')
  } catch (reason) {
    error.value = apiErrorMessage(reason, '最後一個品項移除失敗')
  } finally {
    loading.value = false
  }
}
function itemPayload(item: PurchaseCandidateItem) {
  return { product_id: item.product_id, quantity: item.quantity, unit_of_measure: item.unit_of_measure, specifications: item.specifications }
}

async function saveAndEstimate() {
  if (!candidate.value || !canEstimate.value) return
  loading.value = true
  error.value = ''
  estimate.value = null
  const payload = { purpose: candidate.value.purpose, needed_by: candidate.value.needed_by || null, currency: candidate.value.currency, supplier_ids: selectedSupplierIds.value, items: candidate.value.items.map(itemPayload) }
  try {
    if (draft.value) {
      const response = await api.patch<PurchaseDraft>(`/purchase-request-drafts/${draft.value.id}/`, { ...payload, version: draft.value.version })
      draft.value = response.data
    } else {
      const response = await api.post<PurchaseDraft>('/purchase-request-drafts/', payload)
      draft.value = response.data
    }
    const response = await api.post<DraftEstimate>(`/purchase-request-drafts/${draft.value.id}/preview/`, { version: draft.value.version })
    estimate.value = response.data
    notice.value = response.data.message
  } catch (reason) {
    error.value = apiErrorMessage(reason, '草稿儲存或試算失敗')
  } finally { loading.value = false }
}

async function submitDraft() {
  if (!draft.value || !estimate.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await api.post<{ request_no: string }>(`/purchase-request-drafts/${draft.value.id}/submit/`, { version: draft.value.version, idempotency_key: crypto.randomUUID() })
    rawText.value = ''
    candidate.value = null
    selectedSupplierIds.value = []
    coverageRows.value = []
    draft.value = null
    estimate.value = null
    notice.value = ''
    successToast.value = `採購申請 ${response.data.request_no} 已成功送出`
    if (successTimer) clearTimeout(successTimer)
    successTimer = setTimeout(dismissSuccess, 5000)
  } catch (reason) {
    error.value = apiErrorMessage(reason, '採購申請送出失敗')
  } finally { loading.value = false }
}
onMounted(loadCatalogs)
onBeforeUnmount(() => {
  if (successTimer) clearTimeout(successTimer)
  if (resetTimer) clearTimeout(resetTimer)
})
</script>

<template>
  <PageHeader eyebrow="採購流程" title="新增採購需求" description="先解析、再人工確認；試算不等於正式送出。" />
  <div v-if="successToast" class="success-toast" role="status"><span>{{ successToast }}</span><a href="/purchase-requests">查看申請</a><button type="button" aria-label="關閉成功提示" @click="dismissSuccess">×</button></div>
  <section class="surface inquiry-card inquiry-workspace">
    <div>
      <h2>用一句話描述需求</h2>
      <p>可以包含多個品項與多間候選供應商。</p>
      <form @submit.prevent="parseRequirement">
        <label for="inquiry">採購需求</label>
        <textarea id="inquiry" ref="inquiryInput" v-model.trim="rawText" rows="5" required placeholder="例如：跟優品科技、大和物產詢價，採購網布辦公椅 5 張和升降桌 3 張" />
        <div class="form-actions"><button class="primary-button" :disabled="loading || !rawText" type="submit">{{ loading ? '處理中…' : '解析需求' }}</button></div>
      </form>
    </div>
    <p v-if="resetNotice" class="success-panel" role="status">{{ resetNotice }}</p>
    <p v-if="notice" class="success-panel" role="status">{{ notice }}</p>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>

    <div v-if="candidate" class="candidate-editor">
      <header><div><small>步驟 2</small><h2>確認與修正需求</h2></div><span class="status-badge">AI 候選／尚未建單</span></header>
      <div class="editor-grid">
        <div><label for="purpose">採購用途</label><input id="purpose" v-model="candidate.purpose" /></div>
        <div><label for="needed-by">需求日期（選填）</label><input id="needed-by" v-model="candidate.needed_by" type="date" /></div>
      </div>
      <fieldset :class="{ 'invalid-group': !selectedSupplierIds.length }" :aria-invalid="!selectedSupplierIds.length"><legend>候選供應商</legend><div class="choice-grid"><label v-for="supplier in suppliers" :key="supplier.id" class="choice-card"><input v-model="selectedSupplierIds" type="checkbox" :value="supplier.id" @change="refreshCoverage" /><span>{{ supplier.name }}</span></label></div><small v-if="!selectedSupplierIds.length" class="field-error">請至少選擇一間候選供應商。</small></fieldset>
      <div class="section-heading"><div><h3>明細品項</h3><p>數量與規格都可在試算前修正。</p></div><button class="secondary-button" type="button" @click="addItem">＋ 新增品項</button></div>
      <article v-for="(item, index) in candidate.items" :key="index" class="line-editor">
        <div class="line-editor-heading">
          <div class="line-editor-title"><strong>品項 {{ index + 1 }}</strong><span class="match-status" :class="{ matched: item.product_id }">{{ item.product_id ? '已匹配' : '待選擇' }}</span></div>
          <button class="text-button danger remove-item-button" type="button" @click="removeItem(index)">移除</button>
        </div>
        <div class="recognition-summary"><small>AI 辨識內容</small><span>{{ recognizedItemSummary(item) }}</span></div>
        <p v-if="!item.product_id" class="item-match-warning" role="alert"><strong>尚未找到正式品項</strong><span>請從下方手動選擇其他品項，或移除此品項。</span></p>
        <div class="editor-grid three-columns">
          <div><label :for="`product-${index}`">品項</label><select :id="`product-${index}`" v-model="item.product_id" :class="{ 'invalid-field': !item.product_id }" :aria-invalid="!item.product_id" required @change="refreshCoverage"><option :value="null">請選擇</option><option v-for="product in products" :key="product.id" :value="product.id">{{ product.name }}</option></select><small v-if="!item.product_id" class="field-error">請選擇正式品項。</small></div>
          <div><label :for="`quantity-${index}`">數量</label><input :id="`quantity-${index}`" v-model="item.quantity" :class="{ 'invalid-field': Number(item.quantity) <= 0 }" :aria-invalid="Number(item.quantity) <= 0" min="0.001" step="0.001" type="number" required @change="refreshCoverage" /><small v-if="Number(item.quantity) <= 0" class="field-error">請填寫大於 0 的數量。</small></div>
          <div><label :for="`unit-${index}`">單位</label><input :id="`unit-${index}`" v-model="item.unit_of_measure" /></div>
        </div>
        <div class="editor-grid three-columns specification-fields"><div><label>材質</label><input v-model="item.specifications.material" /></div><div><label>尺寸</label><input v-model="item.specifications.size" /></div><div><label>特色／必要條件</label><input v-model="item.specifications.features" /></div></div>
      </article>
      <section v-if="coverageProducts.length" class="coverage-section" aria-labelledby="coverage-heading">
        <div class="coverage-heading"><div><small>供應能力對照</small><h3 id="coverage-heading">每個品項由哪些供應商供應</h3></div><span>僅供確認，不等於正式報價</span></div>
        <div class="coverage-grid">
          <article v-for="product in coverageProducts" :key="product.product_id" class="coverage-card">
            <h4>{{ product.product_name }}</h4>
            <div v-for="row in product.rows" :key="row.supplier_id" class="coverage-row">
              <strong>{{ row.supplier_name }}</strong>
              <span class="coverage-status" :class="`coverage-${row.status}`">{{ row.label }}</span>
              <small v-if="row.unit_price">參考單價 {{ formatMoney(row.unit_price, row.currency) }}</small>
            </div>
          </article>
        </div>
      </section>
      <div class="estimate-action-row"><small v-if="estimateDisabledReason" role="status">{{ estimateDisabledReason }}</small><button class="primary-button" :disabled="loading || !canEstimate" :title="estimateDisabledReason" type="button" @click="saveAndEstimate">儲存草稿並試算</button></div>
    </div>

    <div v-if="estimate" class="estimate-section">
      <header><div><small>步驟 3</small><h2>試算結果</h2></div><span class="status-badge">僅供參考／尚未送出</span></header>
      <div class="estimate-grid"><article v-for="supplier in estimate.suppliers" :key="supplier.supplier_id" class="estimate-card"><header><h3>{{ supplier.supplier_name }}</h3><strong>{{ supplierHasPrice(supplier) ? formatMoney(supplier.estimated_total, supplier.currency) : '尚無報價' }}</strong></header><div v-for="item in supplier.items" :key="item.product_id" class="estimate-line"><div><strong>{{ item.product_name }}</strong><small>{{ formatQuantity(item.quantity, item.unit_of_measure) }}</small></div><template v-if="item.available"><div class="price-detail"><span>單價 {{ formatMoney(item.unit_price ?? 0, item.currency) }}</span><strong>{{ formatMoney(item.total_amount ?? 0, item.currency) }}</strong></div><p :class="{ 'warning-text': item.price_comparison?.status === 'warning' }">{{ item.price_comparison?.label }}<template v-if="item.price_comparison?.deviation_pct"> · {{ item.price_comparison.deviation_pct }}%</template></p></template><p v-else class="warning-text">{{ item.message }}</p></div></article></div>
      <div class="submit-confirmation"><p>請確認品項、數量、供應商與試算資訊。送出後將進入正式採購流程。</p><button class="primary-button" :disabled="loading" type="button" @click="submitDraft">提交採購申請</button></div>
    </div>
  </section>
</template>
