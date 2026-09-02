<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { Paginated, Product, PurchaseSuggestion, Supplier } from '../types/api'
import { formatDateTime, formatQuantity } from '../utils/formatters'
import { fetchAllPages } from '../utils/pagination'

const auth = useAuthStore()
const canConvert = computed(() => auth.hasPermission('purchase_request.create'))
const canDismiss = computed(() => auth.isAdmin)

const suggestions = ref<PurchaseSuggestion[]>([])
const products = ref<Product[]>([])
const suppliers = ref<Supplier[]>([])
const productNameById = computed(() => Object.fromEntries(products.value.map((product) => [product.id, product.name])))
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [suggestionResponse, productList, supplierList] = await Promise.all([
      api.get<Paginated<PurchaseSuggestion>>('/purchase-suggestions/'),
      fetchAllPages<Product>('/products/'),
      fetchAllPages<Supplier>('/suppliers/'),
    ])
    suggestions.value = suggestionResponse.data.results
    products.value = productList
    suppliers.value = supplierList.filter((supplier) => supplier.is_active)
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法載入採購建議清單（需 purchase_suggestion.read 權限）')
  } finally {
    loading.value = false
  }
}

// ---- 轉單 ----
const showConvertForm = ref(false)
const convertingSuggestion = ref<PurchaseSuggestion | null>(null)
const convertSaving = ref(false)
const convertError = ref('')
const convertForm = reactive({ purpose: '', needed_by: '', currency: 'TWD', supplier_ids: [] as number[] })

function openConvert(suggestion: PurchaseSuggestion) {
  convertingSuggestion.value = suggestion
  Object.assign(convertForm, {
    purpose: `低庫存自動補貨：${productNameById.value[suggestion.product] ?? ''}`,
    needed_by: '', currency: 'TWD', supplier_ids: [],
  })
  convertError.value = ''
  showConvertForm.value = true
}

async function submitConvert() {
  if (!convertingSuggestion.value || convertForm.supplier_ids.length === 0) {
    convertError.value = '請至少選擇一間候選供應商'
    return
  }
  convertSaving.value = true
  convertError.value = ''
  try {
    await api.post(`/purchase-suggestions/${convertingSuggestion.value.id}/convert/`, {
      supplier_ids: convertForm.supplier_ids,
      purpose: convertForm.purpose,
      needed_by: convertForm.needed_by || null,
      currency: convertForm.currency,
    })
    showConvertForm.value = false
    await load()
  } catch (reason) {
    convertError.value = apiErrorMessage(reason, '轉單失敗')
  } finally {
    convertSaving.value = false
  }
}

async function dismissSuggestion(suggestion: PurchaseSuggestion) {
  error.value = ''
  try {
    await api.post(`/purchase-suggestions/${suggestion.id}/dismiss/`)
    await load()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '忽略採購建議失敗')
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="庫存與建議" title="採購建議">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>
  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="suggestions.length === 0" class="empty-state">目前沒有待處理的採購建議。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>品項</th><th>建議數量</th><th>狀態</th><th>建立時間</th><th></th></tr></thead>
        <tbody>
          <tr v-for="suggestion in suggestions" :key="suggestion.id">
            <td>{{ productNameById[suggestion.product] ?? `#${suggestion.product}` }}</td>
            <td>{{ formatQuantity(suggestion.suggested_qty) }}</td>
            <td><StatusBadge :status="suggestion.status" /></td>
            <td>{{ formatDateTime(suggestion.created_at) }}</td>
            <td v-if="suggestion.status === 'pending'">
              <button v-if="canConvert" class="primary-button" @click="openConvert(suggestion)">轉為採購需求</button>
              <button v-if="canDismiss" class="secondary-button" @click="dismissSuggestion(suggestion)">忽略</button>
            </td>
            <td v-else>{{ suggestion.purchase_request ? `已轉單 #${suggestion.purchase_request}` : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <div v-if="showConvertForm && convertingSuggestion" class="modal-backdrop" @click.self="showConvertForm = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="convert-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">庫存與建議</span><h2 id="convert-form-title">轉為採購需求</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="showConvertForm = false">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitConvert">
          <label for="convert-purpose">採購用途</label>
          <input id="convert-purpose" v-model="convertForm.purpose" required />
          <div class="editor-grid">
            <div>
              <label for="convert-needed-by">需求日期（選填）</label>
              <input id="convert-needed-by" v-model="convertForm.needed_by" type="date" />
            </div>
            <div>
              <label for="convert-currency">幣別</label>
              <input id="convert-currency" v-model="convertForm.currency" required />
            </div>
          </div>
          <label>候選供應商</label>
          <div class="choice-grid">
            <label v-for="supplier in suppliers" :key="supplier.id" class="choice-card">
              <input v-model="convertForm.supplier_ids" type="checkbox" :value="supplier.id" /> {{ supplier.name }}
            </label>
          </div>
          <p v-if="convertError" class="error-message" role="alert">{{ convertError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="showConvertForm = false">取消</button>
            <button type="submit" class="primary-button" :disabled="convertSaving">{{ convertSaving ? '建立中…' : '建立採購需求' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>
