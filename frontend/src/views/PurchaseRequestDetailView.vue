<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge.vue'
import type { PurchaseRequestDetail } from '../types/api'
import { formatDateTime, formatQuantity } from '../utils/formatters'

const props = defineProps<{ id: string }>()
const emit = defineEmits<{ close: [] }>()
const purchaseRequest = ref<PurchaseRequestDetail | null>(null)
const loading = ref(true)
const error = ref('')
let previousBodyOverflow = ''

const specificationLabels: Record<string, string> = {
  material: '材質',
  size: '尺寸',
  feature: '特色／必要條件',
}

function specificationLabel(key: string) {
  return specificationLabels[key] ?? key
}

function specificationValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  return Array.isArray(value) ? value.join('、') : String(value)
}

async function load() {
  try {
    purchaseRequest.value = (await api.get<PurchaseRequestDetail>(`/purchase-requests/${props.id}/`)).data
  } catch {
    error.value = '找不到這筆採購需求，或你沒有查看權限。'
  } finally {
    loading.value = false
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => {
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', handleKeydown)
  void load()
})

onBeforeUnmount(() => {
  document.body.style.overflow = previousBodyOverflow
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="purchase-request-detail-title">
      <header class="modal-header">
        <div><span class="eyebrow">採購流程</span><h2 id="purchase-request-detail-title">採購需求詳情</h2><p>唯讀內容，不會在此變更單據。</p></div>
        <button type="button" class="modal-close" aria-label="關閉採購需求詳情" @click="emit('close')">×</button>
      </header>

      <div class="modal-body">
        <p v-if="loading" class="empty-state">載入中…</p>
        <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
        <template v-else-if="purchaseRequest">
          <section class="detail-section">
            <header class="detail-heading">
              <div><span class="eyebrow">申請編號</span><h2>{{ purchaseRequest.request_no }}</h2></div>
              <StatusBadge :status="purchaseRequest.status" />
            </header>
            <dl class="detail-grid">
              <div><dt>採購用途</dt><dd>{{ purchaseRequest.purpose || '—' }}</dd></div>
              <div><dt>需求日期</dt><dd>{{ purchaseRequest.needed_by || '—' }}</dd></div>
              <div><dt>幣別</dt><dd>{{ purchaseRequest.currency }}</dd></div>
              <div><dt>申請人</dt><dd>{{ purchaseRequest.requester_name }}</dd></div>
              <div><dt>建立時間</dt><dd>{{ formatDateTime(purchaseRequest.created_at) }}</dd></div>
              <div><dt>最後更新</dt><dd>{{ formatDateTime(purchaseRequest.updated_at) }}</dd></div>
            </dl>
          </section>

          <section class="detail-section">
            <h2>候選供應商</h2>
            <div class="tag-list">
              <span v-for="supplier in purchaseRequest.candidate_suppliers" :key="supplier.supplier_id" class="tag">{{ supplier.supplier_name }}</span>
              <span v-if="purchaseRequest.candidate_suppliers.length === 0">—</span>
            </div>
          </section>

          <section class="detail-section">
            <h2>明細品項</h2>
            <article v-for="item in purchaseRequest.items" :key="item.id" class="detail-item">
              <header><div><span class="eyebrow">品項 {{ item.line_no }}</span><h3>{{ item.product_name || item.description_snapshot }}</h3></div><strong>{{ formatQuantity(item.quantity, item.unit_of_measure) }}</strong></header>
              <dl v-if="Object.keys(item.specifications).length" class="detail-grid specification-grid">
                <div v-for="(value, key) in item.specifications" :key="key"><dt>{{ specificationLabel(String(key)) }}</dt><dd>{{ specificationValue(value) }}</dd></div>
              </dl>
              <p v-else class="muted-text">未設定其他規格。</p>
            </article>
          </section>
        </template>
      </div>
    </section>
  </div>
</template>
