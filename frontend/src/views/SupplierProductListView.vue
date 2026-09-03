<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import ListPagination from '../components/ListPagination.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useListQuery } from '../composables/useListQuery'
import { useAuthStore } from '../stores/auth'
import type { PaginatedList, Product, Supplier, SupplierProduct } from '../types/api'
import { formatDateTime, formatMoney, formatQuantity } from '../utils/formatters'
import { fetchAllPages } from '../utils/pagination'

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('master_data.manage'))

const suppliers = ref<Supplier[]>([])
const products = ref<Product[]>([])
const optionsError = ref('')
const expandedId = ref<number | null>(null)

const {
  items, loading, error, count, totalPages, page, pageSize, search, filters,
  load: loadItems, applySearch, applyFilter, resetFilters, changePage, changePageSize,
} = useListQuery<SupplierProduct>(
  (params) => api.get<PaginatedList<SupplierProduct>>('/supplier-products/', { params }).then((res) => res.data),
  ['quality_status', 'is_active'],
)

function currentPrice(item: SupplierProduct) {
  if (item.price_versions.length === 0) return null
  const now = Date.now()
  const active = item.price_versions.find((version) => {
    const validFrom = new Date(version.valid_from).getTime()
    const validUntil = version.valid_until ? new Date(version.valid_until).getTime() : Infinity
    return validFrom <= now && now < validUntil
  })
  if (active) return active
  return [...item.price_versions].sort(
    (a, b) => new Date(b.valid_from).getTime() - new Date(a.valid_from).getTime(),
  )[0] ?? null
}

async function loadOptions() {
  optionsError.value = ''
  try {
    const [supplierList, productList] = await Promise.all([
      fetchAllPages<Supplier>('/suppliers/'),
      fetchAllPages<Product>('/products/'),
    ])
    suppliers.value = supplierList
    products.value = productList
  } catch (reason) {
    optionsError.value = apiErrorMessage(reason, '無法載入供應商與品項下拉選單')
  }
}

async function load() {
  await Promise.all([loadItems(), loadOptions()])
}

function toggleExpand(item: SupplierProduct) {
  expandedId.value = expandedId.value === item.id ? null : item.id
}

// ---- 新增／編輯供應商品項 ----
const showMappingForm = ref(false)
const editingId = ref<number | null>(null)
const mappingSaving = ref(false)
const mappingFormError = ref('')
const mappingForm = reactive({
  supplier: '' as number | '', product: '' as number | '', supplier_sku: '',
  lead_time_days: '0', minimum_order_quantity: '1', quality_status: 'qualified', is_active: true,
})

function openCreateMapping() {
  editingId.value = null
  Object.assign(mappingForm, {
    supplier: '', product: '', supplier_sku: '', lead_time_days: '0',
    minimum_order_quantity: '1', quality_status: 'qualified', is_active: true,
  })
  mappingFormError.value = ''
  showMappingForm.value = true
}

function openEditMapping(item: SupplierProduct) {
  editingId.value = item.id
  Object.assign(mappingForm, {
    supplier: item.supplier, product: item.product, supplier_sku: item.supplier_sku ?? '',
    lead_time_days: String(item.lead_time_days), minimum_order_quantity: item.minimum_order_quantity,
    quality_status: item.quality_status, is_active: item.is_active,
  })
  mappingFormError.value = ''
  showMappingForm.value = true
}

async function submitMapping() {
  if (!editingId.value && (!mappingForm.supplier || !mappingForm.product)) {
    mappingFormError.value = '請選擇供應商與品項'
    return
  }
  mappingSaving.value = true
  mappingFormError.value = ''
  try {
    if (editingId.value) {
      await api.patch(`/supplier-products/${editingId.value}/`, {
        supplier_sku: mappingForm.supplier_sku,
        lead_time_days: Number(mappingForm.lead_time_days),
        minimum_order_quantity: mappingForm.minimum_order_quantity,
        quality_status: mappingForm.quality_status,
        is_active: mappingForm.is_active,
      })
    } else {
      await api.post('/supplier-products/', {
        supplier: mappingForm.supplier,
        product: mappingForm.product,
        supplier_sku: mappingForm.supplier_sku,
        lead_time_days: Number(mappingForm.lead_time_days),
        minimum_order_quantity: mappingForm.minimum_order_quantity,
        quality_status: mappingForm.quality_status,
      })
    }
    showMappingForm.value = false
    await loadItems()
  } catch (reason) {
    mappingFormError.value = apiErrorMessage(reason, '儲存失敗，請確認欄位內容')
  } finally {
    mappingSaving.value = false
  }
}

async function toggleMappingActive(item: SupplierProduct) {
  try {
    await api.patch(`/supplier-products/${item.id}/`, { is_active: !item.is_active })
    await loadItems()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '更新狀態失敗')
  }
}

// ---- 新增價格版本 ----
const showPriceForm = ref(false)
const priceFormTarget = ref<SupplierProduct | null>(null)
const priceSaving = ref(false)
const priceFormError = ref('')
const priceForm = reactive({ unit_price: '', currency: 'TWD', minimum_quantity: '1', valid_from: '', valid_until: '' })

function openPriceForm(item: SupplierProduct) {
  priceFormTarget.value = item
  Object.assign(priceForm, {
    unit_price: '', currency: 'TWD', minimum_quantity: '1',
    valid_from: new Date().toISOString().slice(0, 16), valid_until: '',
  })
  priceFormError.value = ''
  showPriceForm.value = true
}

async function submitPrice() {
  if (!priceFormTarget.value || !priceForm.unit_price || !priceForm.valid_from) {
    priceFormError.value = '請輸入單價與生效時間'
    return
  }
  priceSaving.value = true
  priceFormError.value = ''
  try {
    await api.post(`/supplier-products/${priceFormTarget.value.id}/price-versions/`, {
      unit_price: priceForm.unit_price,
      currency: priceForm.currency,
      minimum_quantity: priceForm.minimum_quantity,
      valid_from: new Date(priceForm.valid_from).toISOString(),
      valid_until: priceForm.valid_until ? new Date(priceForm.valid_until).toISOString() : null,
    })
    showPriceForm.value = false
    await loadItems()
  } catch (reason) {
    priceFormError.value = apiErrorMessage(reason, '新增價格版本失敗，請確認欄位內容')
  } finally {
    priceSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="主檔管理" title="供應商品項與價格">
    <template #actions>
      <button class="secondary-button" @click="load">重新整理</button>
      <button v-if="canManage" class="primary-button" @click="openCreateMapping">新增供應商品項</button>
    </template>
  </PageHeader>
  <p v-if="optionsError" class="error-message" role="alert">{{ optionsError }}</p>
  <section class="surface table-surface">
    <form class="filter-bar" @submit.prevent="applySearch">
      <input v-model="search" type="search" aria-label="搜尋供應商品項" placeholder="搜尋供應商、品項或供應商料號…" />
      <select aria-label="品質狀態篩選" :value="filters.quality_status" @change="applyFilter('quality_status', ($event.target as HTMLSelectElement).value)">
        <option value="">全部品質狀態</option>
        <option value="qualified">合格</option>
        <option value="conditional">有條件合格</option>
        <option value="blocked">已封鎖</option>
      </select>
      <select aria-label="啟用狀態篩選" :value="filters.is_active" @change="applyFilter('is_active', ($event.target as HTMLSelectElement).value)">
        <option value="">全部啟用狀態</option>
        <option value="true">啟用中</option>
        <option value="false">已停用</option>
      </select>
      <button type="submit" class="secondary-button">搜尋</button>
      <button type="button" class="secondary-button" @click="resetFilters">清除條件</button>
    </form>
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="items.length === 0" class="empty-state">目前沒有符合條件的供應商品項對應資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>供應商</th><th>品項</th><th>供應商料號</th><th>交期(天)</th><th>最小訂購量</th>
            <th>品質狀態</th><th>現行單價</th><th>啟用</th><th v-if="canManage">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in items" :key="item.id">
            <tr>
              <td>{{ item.supplier_name }}</td>
              <td>{{ item.product_name }}</td>
              <td>{{ item.supplier_sku || '—' }}</td>
              <td>{{ item.lead_time_days }}</td>
              <td>{{ formatQuantity(item.minimum_order_quantity) }}</td>
              <td><StatusBadge :status="item.quality_status" /></td>
              <td>
                <span v-if="currentPrice(item)">{{ formatMoney(currentPrice(item)!.unit_price, currentPrice(item)!.currency) }}</span>
                <span v-else>—</span>
                <button v-if="item.price_versions.length" class="secondary-button" style="margin-left: 8px;" @click="toggleExpand(item)">
                  {{ expandedId === item.id ? '收合歷史' : `價格歷史(${item.price_versions.length})` }}
                </button>
              </td>
              <td>{{ item.is_active ? '啟用中' : '已停用' }}</td>
              <td v-if="canManage">
                <button class="secondary-button" @click="openEditMapping(item)">編輯</button>
                <button class="secondary-button" @click="toggleMappingActive(item)">{{ item.is_active ? '停用' : '啟用' }}</button>
                <button class="secondary-button" @click="openPriceForm(item)">新增價格版本</button>
              </td>
            </tr>
            <tr v-if="expandedId === item.id">
              <td :colspan="canManage ? 9 : 8">
                <table>
                  <thead><tr><th>單價</th><th>幣別</th><th>最小數量</th><th>生效</th><th>失效</th><th>建立者</th></tr></thead>
                  <tbody>
                    <tr v-for="version in item.price_versions" :key="version.id">
                      <td>{{ version.unit_price }}</td>
                      <td>{{ version.currency }}</td>
                      <td>{{ formatQuantity(version.minimum_quantity) }}</td>
                      <td>{{ formatDateTime(version.valid_from) }}</td>
                      <td>{{ version.valid_until ? formatDateTime(version.valid_until) : '不限' }}</td>
                      <td>{{ version.created_by_name }}</td>
                    </tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <ListPagination
      v-if="!loading && !error"
      :page="page" :page-size="pageSize" :total-pages="totalPages" :count="count"
      label="供應商品項分頁" @change-page="changePage" @change-page-size="changePageSize"
    />
  </section>

  <div v-if="showMappingForm" class="modal-backdrop" @click.self="showMappingForm = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="mapping-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">主檔管理</span><h2 id="mapping-form-title">{{ editingId ? '編輯供應商品項' : '新增供應商品項' }}</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="showMappingForm = false">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitMapping">
          <div class="editor-grid">
            <div>
              <label for="mapping-supplier">供應商</label>
              <select id="mapping-supplier" v-model="mappingForm.supplier" :disabled="Boolean(editingId)" required>
                <option value="" disabled>請選擇供應商</option>
                <option v-for="supplier in suppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option>
              </select>
            </div>
            <div>
              <label for="mapping-product">品項</label>
              <select id="mapping-product" v-model="mappingForm.product" :disabled="Boolean(editingId)" required>
                <option value="" disabled>請選擇品項</option>
                <option v-for="product in products" :key="product.id" :value="product.id">{{ product.name }}</option>
              </select>
            </div>
          </div>

          <label for="mapping-sku">供應商料號</label>
          <input id="mapping-sku" v-model="mappingForm.supplier_sku" />

          <div class="three-columns editor-grid">
            <div>
              <label for="mapping-lead-time">交期(天)</label>
              <input id="mapping-lead-time" v-model="mappingForm.lead_time_days" type="number" min="0" />
            </div>
            <div>
              <label for="mapping-moq">最小訂購量</label>
              <input id="mapping-moq" v-model="mappingForm.minimum_order_quantity" type="number" step="0.001" min="0" />
            </div>
            <div>
              <label for="mapping-quality">品質狀態</label>
              <input id="mapping-quality" v-model="mappingForm.quality_status" />
            </div>
          </div>

          <label v-if="editingId" class="choice-card"><input v-model="mappingForm.is_active" type="checkbox" /> 允許用於新交易</label>

          <p v-if="mappingFormError" class="error-message" role="alert">{{ mappingFormError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="showMappingForm = false">取消</button>
            <button type="submit" class="primary-button" :disabled="mappingSaving">{{ mappingSaving ? '儲存中…' : '儲存' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>

  <div v-if="showPriceForm" class="modal-backdrop" @click.self="showPriceForm = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="price-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">{{ priceFormTarget?.supplier_name }} / {{ priceFormTarget?.product_name }}</span><h2 id="price-form-title">新增價格版本</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="showPriceForm = false">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitPrice">
          <div class="editor-grid">
            <div>
              <label for="price-unit-price">單價</label>
              <input id="price-unit-price" v-model="priceForm.unit_price" type="number" step="0.01" min="0" required />
            </div>
            <div>
              <label for="price-currency">幣別</label>
              <input id="price-currency" v-model="priceForm.currency" required />
            </div>
          </div>
          <label for="price-moq">最小數量</label>
          <input id="price-moq" v-model="priceForm.minimum_quantity" type="number" step="0.001" min="0" />
          <div class="editor-grid">
            <div>
              <label for="price-valid-from">生效時間</label>
              <input id="price-valid-from" v-model="priceForm.valid_from" type="datetime-local" required />
            </div>
            <div>
              <label for="price-valid-until">失效時間（選填）</label>
              <input id="price-valid-until" v-model="priceForm.valid_until" type="datetime-local" />
            </div>
          </div>
          <p v-if="priceFormError" class="error-message" role="alert">{{ priceFormError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="showPriceForm = false">取消</button>
            <button type="submit" class="primary-button" :disabled="priceSaving">{{ priceSaving ? '儲存中…' : '儲存' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>
