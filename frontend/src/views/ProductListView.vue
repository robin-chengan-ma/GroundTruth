<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import ListPagination from '../components/ListPagination.vue'
import PageHeader from '../components/PageHeader.vue'
import { useListQuery } from '../composables/useListQuery'
import { useAuthStore } from '../stores/auth'
import type { PaginatedList, Product, ProductCategory } from '../types/api'
import { formatMoney } from '../utils/formatters'
import { fetchAllPages } from '../utils/pagination'

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('master_data.manage'))

// 品項分類是小型參考主檔，不比照品項套用完整的搜尋／篩選／分頁 UI（範圍縮減，待 Robin 核准，
// 見 docs/ADR/discuss/phase6.md）；但仍必須用 fetchAllPages() 逐頁抓完整清單，不可只取單頁，
// 否則分類筆數超過一頁時，分類清單本身、品項的分類下拉選單都會靜默漏資料且沒有任何提示。
const categories = ref<ProductCategory[]>([])
const categoriesLoading = ref(true)
const categoriesError = ref('')

async function loadCategories() {
  categoriesLoading.value = true
  categoriesError.value = ''
  try {
    categories.value = await fetchAllPages<ProductCategory>('/product-categories/')
  } catch {
    categoriesError.value = '無法載入品項分類'
  } finally {
    categoriesLoading.value = false
  }
}

const {
  items: products, loading, error, count, totalPages, page, pageSize, search, filters,
  load: loadProducts, applySearch, applyFilter, resetFilters, changePage, changePageSize,
} = useListQuery<Product>(
  (params) => api.get<PaginatedList<Product>>('/products/', { params }).then((res) => res.data),
  ['category', 'is_active'],
)

async function load() {
  await Promise.all([loadCategories(), loadProducts()])
}

// ---- 品項分類 ----
const showCategoryForm = ref(false)
const editingCategoryId = ref<number | null>(null)
const categorySaving = ref(false)
const categoryFormError = ref('')
const categoryForm = reactive({ code: '', name: '', is_active: true })

function openCreateCategory() {
  editingCategoryId.value = null
  Object.assign(categoryForm, { code: '', name: '', is_active: true })
  categoryFormError.value = ''
  showCategoryForm.value = true
}

function openEditCategory(category: ProductCategory) {
  editingCategoryId.value = category.id
  Object.assign(categoryForm, { code: category.code, name: category.name, is_active: category.is_active })
  categoryFormError.value = ''
  showCategoryForm.value = true
}

async function submitCategory() {
  if (!categoryForm.code.trim() || !categoryForm.name.trim()) {
    categoryFormError.value = '請輸入分類代碼與名稱'
    return
  }
  categorySaving.value = true
  categoryFormError.value = ''
  const payload = { code: categoryForm.code, name: categoryForm.name, is_active: categoryForm.is_active }
  try {
    if (editingCategoryId.value) await api.patch(`/product-categories/${editingCategoryId.value}/`, payload)
    else await api.post('/product-categories/', payload)
    showCategoryForm.value = false
    await loadCategories()
  } catch (reason) {
    categoryFormError.value = apiErrorMessage(reason, '儲存分類失敗，請確認欄位內容')
  } finally {
    categorySaving.value = false
  }
}

async function toggleCategoryActive(category: ProductCategory) {
  try {
    await api.patch(`/product-categories/${category.id}/`, { is_active: !category.is_active })
    await loadCategories()
  } catch (reason) {
    categoriesError.value = apiErrorMessage(reason, '更新分類狀態失敗')
  }
}

// ---- 品項 ----
const showProductForm = ref(false)
const editingProductId = ref<number | null>(null)
const productSaving = ref(false)
const productFormError = ref('')
const productForm = reactive({
  name: '', category: '' as number | '', sku: '', description: '',
  unit_of_measure: 'EA', price: '', currency: 'TWD', is_active: true,
})

function openCreateProduct() {
  editingProductId.value = null
  Object.assign(productForm, {
    name: '', category: '', sku: '', description: '', unit_of_measure: 'EA', price: '', currency: 'TWD', is_active: true,
  })
  productFormError.value = ''
  showProductForm.value = true
}

function openEditProduct(product: Product) {
  editingProductId.value = product.id
  Object.assign(productForm, {
    name: product.name,
    category: product.category ?? '',
    sku: product.sku ?? '',
    description: product.description,
    unit_of_measure: product.unit_of_measure,
    price: product.price,
    currency: product.currency,
    is_active: product.is_active,
  })
  productFormError.value = ''
  showProductForm.value = true
}

async function submitProduct() {
  if (!productForm.name.trim() || !productForm.price) {
    productFormError.value = '請輸入品項名稱與單價'
    return
  }
  productSaving.value = true
  productFormError.value = ''
  const payload = {
    name: productForm.name,
    category: productForm.category || null,
    sku: productForm.sku || null,
    description: productForm.description,
    unit_of_measure: productForm.unit_of_measure,
    price: productForm.price,
    currency: productForm.currency,
    is_active: productForm.is_active,
  }
  try {
    if (editingProductId.value) await api.patch(`/products/${editingProductId.value}/`, payload)
    else await api.post('/products/', payload)
    showProductForm.value = false
    await loadProducts()
  } catch (reason) {
    productFormError.value = apiErrorMessage(reason, '儲存品項失敗，請確認欄位內容')
  } finally {
    productSaving.value = false
  }
}

async function toggleProductActive(product: Product) {
  try {
    await api.patch(`/products/${product.id}/`, { is_active: !product.is_active })
    await loadProducts()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '更新品項狀態失敗')
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="主檔管理" title="品項與分類">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>

  <section class="detail-section surface" style="margin-bottom: 24px;">
    <header class="section-heading">
      <div><span class="eyebrow">品項分類</span><h3>規格定義主檔</h3></div>
      <button v-if="canManage" class="secondary-button" @click="openCreateCategory">新增分類</button>
    </header>
    <p v-if="categoriesLoading" class="empty-state">載入中…</p>
    <p v-else-if="categoriesError" class="error-message" role="alert">{{ categoriesError }}</p>
    <p v-else-if="categories.length === 0" class="empty-state">尚未建立任何品項分類。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>代碼</th><th>名稱</th><th>啟用</th><th v-if="canManage">操作</th></tr></thead>
        <tbody>
          <tr v-for="category in categories" :key="category.id">
            <td>{{ category.code }}</td>
            <td>{{ category.name }}</td>
            <td>{{ category.is_active ? '啟用中' : '已停用' }}</td>
            <td v-if="canManage">
              <button class="secondary-button" @click="openEditCategory(category)">編輯</button>
              <button class="secondary-button" @click="toggleCategoryActive(category)">{{ category.is_active ? '停用' : '啟用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="surface table-surface">
    <header class="section-heading" style="padding: 22px 22px 0;">
      <div><span class="eyebrow">品項</span><h3>品項主檔</h3></div>
      <button v-if="canManage" class="primary-button" @click="openCreateProduct">新增品項</button>
    </header>
    <form class="filter-bar" @submit.prevent="applySearch">
      <input v-model="search" type="search" aria-label="搜尋品項" placeholder="搜尋名稱或內部料號…" />
      <select aria-label="分類篩選" :value="filters.category" @change="applyFilter('category', ($event.target as HTMLSelectElement).value)">
        <option value="">全部分類</option>
        <option v-for="category in categories" :key="category.id" :value="String(category.id)">{{ category.name }}</option>
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
    <p v-else-if="products.length === 0" class="empty-state">目前沒有符合條件的品項主檔資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>名稱</th><th>分類</th><th>內部料號</th><th>單位</th><th>單價</th><th>啟用</th><th v-if="canManage">操作</th></tr></thead>
        <tbody>
          <tr v-for="product in products" :key="product.id">
            <td>{{ product.name }}</td>
            <td>{{ product.category_name || '—' }}</td>
            <td>{{ product.sku || '—' }}</td>
            <td>{{ product.unit_of_measure }}</td>
            <td>{{ formatMoney(product.price, product.currency) }}</td>
            <td>{{ product.is_active ? '啟用中' : '已停用' }}</td>
            <td v-if="canManage">
              <button class="secondary-button" @click="openEditProduct(product)">編輯</button>
              <button class="secondary-button" @click="toggleProductActive(product)">{{ product.is_active ? '停用' : '啟用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ListPagination
      v-if="!loading && !error"
      :page="page" :page-size="pageSize" :total-pages="totalPages" :count="count"
      label="品項分頁" @change-page="changePage" @change-page-size="changePageSize"
    />
  </section>

  <div v-if="showCategoryForm" class="modal-backdrop" @click.self="showCategoryForm = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="category-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">主檔管理</span><h2 id="category-form-title">{{ editingCategoryId ? '編輯品項分類' : '新增品項分類' }}</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="showCategoryForm = false">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitCategory">
          <label for="category-code">分類代碼</label>
          <input id="category-code" v-model="categoryForm.code" required />
          <label for="category-name">分類名稱</label>
          <input id="category-name" v-model="categoryForm.name" required />
          <label class="choice-card"><input v-model="categoryForm.is_active" type="checkbox" /> 允許新品項使用此分類</label>
          <p v-if="categoryFormError" class="error-message" role="alert">{{ categoryFormError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="showCategoryForm = false">取消</button>
            <button type="submit" class="primary-button" :disabled="categorySaving">{{ categorySaving ? '儲存中…' : '儲存' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>

  <div v-if="showProductForm" class="modal-backdrop" @click.self="showProductForm = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="product-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">主檔管理</span><h2 id="product-form-title">{{ editingProductId ? '編輯品項' : '新增品項' }}</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="showProductForm = false">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submitProduct">
          <label for="product-name">品項名稱</label>
          <input id="product-name" v-model="productForm.name" required />

          <div class="editor-grid">
            <div>
              <label for="product-category">分類</label>
              <select id="product-category" v-model="productForm.category">
                <option value="">未分類</option>
                <option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option>
              </select>
            </div>
            <div>
              <label for="product-sku">內部料號</label>
              <input id="product-sku" v-model="productForm.sku" />
            </div>
          </div>

          <label for="product-description">描述</label>
          <textarea id="product-description" v-model="productForm.description" rows="3" />

          <div class="three-columns editor-grid">
            <div>
              <label for="product-unit">計量單位</label>
              <input id="product-unit" v-model="productForm.unit_of_measure" required />
            </div>
            <div>
              <label for="product-price">單價</label>
              <input id="product-price" v-model="productForm.price" type="number" step="0.01" min="0" required />
            </div>
            <div>
              <label for="product-currency">幣別</label>
              <input id="product-currency" v-model="productForm.currency" required />
            </div>
          </div>

          <label class="choice-card"><input v-model="productForm.is_active" type="checkbox" /> 允許用於新交易</label>

          <p v-if="productFormError" class="error-message" role="alert">{{ productFormError }}</p>
          <div class="form-actions">
            <button type="button" class="secondary-button" @click="showProductForm = false">取消</button>
            <button type="submit" class="primary-button" :disabled="productSaving">{{ productSaving ? '儲存中…' : '儲存' }}</button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>
