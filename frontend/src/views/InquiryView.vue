<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import type { DraftEstimate, Paginated, ProductOption, PurchaseCandidate, PurchaseCandidateItem, PurchaseDraft, SupplierOption } from '../types/api'
import { formatMoney, formatQuantity } from '../utils/formatters'

const rawText = ref('')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const candidate = ref<PurchaseCandidate | null>(null)
const suppliers = ref<SupplierOption[]>([])
const products = ref<ProductOption[]>([])
const selectedSupplierIds = ref<number[]>([])
const draft = ref<PurchaseDraft | null>(null)
const estimate = ref<DraftEstimate | null>(null)
const successToast = ref('')
let successTimer: ReturnType<typeof setTimeout> | null = null

const canEstimate = computed(() => Boolean(candidate.value?.items.length
  && candidate.value.items.every((item) => item.product_id && Number(item.quantity) > 0)
  && selectedSupplierIds.value.length))
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
    notice.value = response.data.assistant_message
  } catch (reason) {
    error.value = apiErrorMessage(reason, '需求解析失敗')
  } finally { loading.value = false }
}

function addItem() {
  candidate.value?.items.push({ product_id: null, product_name: '', quantity: '1', unit_of_measure: 'EA', specifications: {} })
  estimate.value = null
}
function removeItem(index: number) { candidate.value?.items.splice(index, 1); estimate.value = null }
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
onBeforeUnmount(() => { if (successTimer) clearTimeout(successTimer) })
</script>

<template>
  <PageHeader eyebrow="採購流程" title="新增採購需求" description="先解析、再人工確認；試算不等於正式送出。" />
  <div v-if="successToast" class="success-toast" role="status"><span>{{ successToast }}</span><a href="/quotes">查看申請</a><button type="button" aria-label="關閉成功提示" @click="dismissSuccess">×</button></div>
  <section class="surface inquiry-card inquiry-workspace">
    <div>
      <h2>用一句話描述需求</h2>
      <p>可以包含多個品項與多間候選供應商。</p>
      <form @submit.prevent="parseRequirement">
        <label for="inquiry">採購需求</label>
        <textarea id="inquiry" v-model.trim="rawText" rows="5" required placeholder="例如：跟優品科技、大和物產詢價，採購網布辦公椅 5 張和升降桌 3 張" />
        <div class="form-actions"><button class="primary-button" :disabled="loading || !rawText" type="submit">{{ loading ? '處理中…' : '解析需求' }}</button></div>
      </form>
    </div>
    <p v-if="notice" class="success-panel" role="status">{{ notice }}</p>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>

    <div v-if="candidate" class="candidate-editor">
      <header><div><small>步驟 2</small><h2>確認與修正需求</h2></div><span class="status-badge">AI 候選／尚未建單</span></header>
      <div class="editor-grid">
        <div><label for="purpose">採購用途</label><input id="purpose" v-model="candidate.purpose" /></div>
        <div><label for="needed-by">需求日期（選填）</label><input id="needed-by" v-model="candidate.needed_by" type="date" /></div>
      </div>
      <fieldset><legend>候選供應商</legend><div class="choice-grid"><label v-for="supplier in suppliers" :key="supplier.id" class="choice-card"><input v-model="selectedSupplierIds" type="checkbox" :value="supplier.id" /><span>{{ supplier.name }}</span></label></div></fieldset>
      <div class="section-heading"><div><h3>明細品項</h3><p>數量與規格都可在試算前修正。</p></div><button class="secondary-button" type="button" @click="addItem">＋ 新增品項</button></div>
      <article v-for="(item, index) in candidate.items" :key="index" class="line-editor">
        <div class="line-editor-heading"><strong>品項 {{ index + 1 }}</strong><button class="text-button danger" type="button" @click="removeItem(index)">移除</button></div>
        <div class="editor-grid three-columns">
          <div><label :for="`product-${index}`">品項</label><select :id="`product-${index}`" v-model="item.product_id"><option :value="null">請選擇</option><option v-for="product in products" :key="product.id" :value="product.id">{{ product.name }}</option></select></div>
          <div><label :for="`quantity-${index}`">數量</label><input :id="`quantity-${index}`" v-model="item.quantity" min="0.001" step="0.001" type="number" /></div>
          <div><label :for="`unit-${index}`">單位</label><input :id="`unit-${index}`" v-model="item.unit_of_measure" /></div>
        </div>
        <div class="editor-grid three-columns specification-fields"><div><label>材質</label><input v-model="item.specifications.material" /></div><div><label>尺寸</label><input v-model="item.specifications.size" /></div><div><label>特色／必要條件</label><input v-model="item.specifications.features" /></div></div>
      </article>
      <div class="form-actions"><button class="primary-button" :disabled="loading || !canEstimate" type="button" @click="saveAndEstimate">儲存草稿並試算</button></div>
    </div>

    <div v-if="estimate" class="estimate-section">
      <header><div><small>步驟 3</small><h2>試算結果</h2></div><span class="status-badge">僅供參考／尚未送出</span></header>
      <div class="estimate-grid"><article v-for="supplier in estimate.suppliers" :key="supplier.supplier_id" class="estimate-card"><header><h3>{{ supplier.supplier_name }}</h3><strong>{{ supplierHasPrice(supplier) ? formatMoney(supplier.estimated_total, supplier.currency) : '尚無報價' }}</strong></header><div v-for="item in supplier.items" :key="item.product_id" class="estimate-line"><div><strong>{{ item.product_name }}</strong><small>{{ formatQuantity(item.quantity, item.unit_of_measure) }}</small></div><template v-if="item.available"><div class="price-detail"><span>單價 {{ formatMoney(item.unit_price ?? 0, item.currency) }}</span><strong>{{ formatMoney(item.total_amount ?? 0, item.currency) }}</strong></div><p :class="{ 'warning-text': item.price_comparison?.status === 'warning' }">{{ item.price_comparison?.label }}<template v-if="item.price_comparison?.deviation_pct"> · {{ item.price_comparison.deviation_pct }}%</template></p></template><p v-else class="warning-text">{{ item.message }}</p></div></article></div>
      <div class="submit-confirmation"><p>請確認品項、數量、供應商與試算資訊。送出後將進入正式採購流程。</p><button class="primary-button" :disabled="loading" type="button" @click="submitDraft">提交採購申請</button></div>
    </div>
  </section>
</template>
