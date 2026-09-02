<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import ListPagination from '../components/ListPagination.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useListQuery } from '../composables/useListQuery'
import { useAuthStore } from '../stores/auth'
import type { PaginatedList, Supplier, SupplierStatus, SupplierTier } from '../types/api'

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('master_data.manage'))

const {
  items: suppliers, loading, error, count, totalPages, page, pageSize, search, filters,
  load, applySearch, applyFilter, resetFilters, changePage, changePageSize,
} = useListQuery<Supplier>(
  (params) => api.get<PaginatedList<Supplier>>('/suppliers/', { params }).then((res) => res.data),
  ['status', 'tier'],
)

const showForm = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const formError = ref('')

interface SupplierFormState {
  name: string
  tier: SupplierTier
  code: string
  status: SupplierStatus
  tax_id: string
  phone: string
  email: string
  address: string
  payment_terms: string
  is_active: boolean
}

function emptyForm(): SupplierFormState {
  return {
    name: '', tier: 'normal', code: '', status: 'active', tax_id: '',
    phone: '', email: '', address: '', payment_terms: '', is_active: true,
  }
}

const form = reactive(emptyForm())

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  formError.value = ''
  showForm.value = true
}

function openEdit(supplier: Supplier) {
  editingId.value = supplier.id
  const contact = supplier.contact as Record<string, unknown>
  Object.assign(form, {
    name: supplier.name,
    tier: supplier.tier,
    code: supplier.code ?? '',
    status: supplier.status,
    tax_id: supplier.tax_id ?? '',
    phone: String(contact.phone ?? ''),
    email: String(contact.email ?? ''),
    address: String(contact.address ?? ''),
    payment_terms: supplier.payment_terms,
    is_active: supplier.is_active,
  })
  formError.value = ''
  showForm.value = true
}

function closeForm() {
  showForm.value = false
}

async function submit() {
  if (!form.name.trim()) {
    formError.value = '請輸入供應商名稱'
    return
  }
  saving.value = true
  formError.value = ''
  const payload = {
    name: form.name,
    tier: form.tier,
    code: form.code || null,
    status: form.status,
    tax_id: form.tax_id || null,
    contact: { phone: form.phone, email: form.email, address: form.address },
    payment_terms: form.payment_terms,
    is_active: form.is_active,
  }
  try {
    if (editingId.value) await api.patch(`/suppliers/${editingId.value}/`, payload)
    else await api.post('/suppliers/', payload)
    showForm.value = false
    await load()
  } catch (reason) {
    formError.value = apiErrorMessage(reason, '儲存失敗，請確認欄位內容')
  } finally {
    saving.value = false
  }
}

async function toggleActive(supplier: Supplier) {
  try {
    await api.patch(`/suppliers/${supplier.id}/`, { is_active: !supplier.is_active })
    await load()
  } catch (reason) {
    error.value = apiErrorMessage(reason, '更新狀態失敗')
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="主檔管理" title="供應商">
    <template #actions>
      <button class="secondary-button" @click="load">重新整理</button>
      <button v-if="canManage" class="primary-button" @click="openCreate">新增供應商</button>
    </template>
  </PageHeader>
  <section class="surface table-surface">
    <form class="filter-bar" @submit.prevent="applySearch">
      <input v-model="search" type="search" aria-label="搜尋供應商" placeholder="搜尋名稱或內部代碼…" />
      <select aria-label="狀態篩選" :value="filters.status" @change="applyFilter('status', ($event.target as HTMLSelectElement).value)">
        <option value="">全部狀態</option>
        <option value="active">active</option>
        <option value="on_hold">on_hold</option>
        <option value="blocked">blocked</option>
      </select>
      <select aria-label="等級篩選" :value="filters.tier" @change="applyFilter('tier', ($event.target as HTMLSelectElement).value)">
        <option value="">全部等級</option>
        <option value="priority">priority</option>
        <option value="normal">normal</option>
        <option value="watch">watch</option>
      </select>
      <button type="submit" class="secondary-button">搜尋</button>
      <button type="button" class="secondary-button" @click="resetFilters">清除條件</button>
    </form>
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="suppliers.length === 0" class="empty-state">目前沒有符合條件的供應商主檔資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>名稱</th><th>等級</th><th>內部代碼</th><th>統編</th><th>付款條件</th>
            <th>狀態</th><th>啟用</th><th v-if="canManage">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="supplier in suppliers" :key="supplier.id">
            <td>{{ supplier.name }}</td>
            <td>{{ supplier.tier }}</td>
            <td>{{ supplier.code || '—' }}</td>
            <td>{{ supplier.tax_id || '—' }}</td>
            <td>{{ supplier.payment_terms || '—' }}</td>
            <td><StatusBadge :status="supplier.status" /></td>
            <td>{{ supplier.is_active ? '啟用中' : '已停用' }}</td>
            <td v-if="canManage">
              <button class="secondary-button" @click="openEdit(supplier)">編輯</button>
              <button class="secondary-button" @click="toggleActive(supplier)">{{ supplier.is_active ? '停用' : '啟用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ListPagination
      v-if="!loading && !error"
      :page="page" :page-size="pageSize" :total-pages="totalPages" :count="count"
      label="供應商分頁" @change-page="changePage" @change-page-size="changePageSize"
    />
  </section>

  <div v-if="showForm" class="modal-backdrop" @click.self="closeForm">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="supplier-form-title">
      <header class="modal-header">
        <div><span class="eyebrow">主檔管理</span><h2 id="supplier-form-title">{{ editingId ? '編輯供應商' : '新增供應商' }}</h2></div>
        <button type="button" class="modal-close" aria-label="關閉表單" @click="closeForm">×</button>
      </header>
      <div class="modal-body">
        <form @submit.prevent="submit">
          <label for="supplier-name">供應商名稱</label>
          <input id="supplier-name" v-model="form.name" required />

          <div class="editor-grid">
            <div>
              <label for="supplier-tier">等級</label>
              <select id="supplier-tier" v-model="form.tier">
                <option value="priority">priority</option>
                <option value="normal">normal</option>
                <option value="watch">watch</option>
              </select>
            </div>
            <div>
              <label for="supplier-status">狀態</label>
              <select id="supplier-status" v-model="form.status">
                <option value="active">active</option>
                <option value="on_hold">on_hold</option>
                <option value="blocked">blocked</option>
              </select>
            </div>
          </div>

          <div class="editor-grid">
            <div>
              <label for="supplier-code">內部代碼</label>
              <input id="supplier-code" v-model="form.code" />
            </div>
            <div>
              <label for="supplier-tax-id">統一編號</label>
              <input id="supplier-tax-id" v-model="form.tax_id" />
            </div>
          </div>

          <label for="supplier-phone">聯絡電話</label>
          <input id="supplier-phone" v-model="form.phone" />
          <label for="supplier-email">聯絡信箱</label>
          <input id="supplier-email" v-model="form.email" type="email" />
          <label for="supplier-address">聯絡地址</label>
          <input id="supplier-address" v-model="form.address" />
          <label for="supplier-payment-terms">付款條件</label>
          <input id="supplier-payment-terms" v-model="form.payment_terms" />

          <label class="choice-card"><input v-model="form.is_active" type="checkbox" /> 允許用於新交易</label>

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
