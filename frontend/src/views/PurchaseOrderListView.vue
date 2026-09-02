<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { PurchaseOrder } from '../types/api'
import { formatDateTime, formatMoney, formatQuantity } from '../utils/formatters'

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('purchase_order.manage'))

const orders = ref<PurchaseOrder[]>([])
const loading = ref(true)
const error = ref('')

const showDetail = ref(false)
const detail = ref<PurchaseOrder | null>(null)
const issuing = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    orders.value = (await api.get<PurchaseOrder[]>('/purchase-orders/')).data
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法載入採購單清單')
  } finally {
    loading.value = false
  }
}

function openDetail(order: PurchaseOrder) {
  detail.value = order
  showDetail.value = true
}

async function issueOrder(order: PurchaseOrder) {
  issuing.value = true
  error.value = ''
  try {
    await api.post(`/purchase-orders/${order.id}/issue/`, { version: order.version })
    await load()
    if (detail.value?.id === order.id) {
      detail.value = orders.value.find((item) => item.id === order.id) ?? detail.value
    }
  } catch (reason) {
    error.value = apiErrorMessage(reason, '發出採購單失敗')
  } finally {
    issuing.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="訂單與到貨" title="採購單">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>
  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="orders.length === 0" class="empty-state">目前沒有採購單資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>採購單號</th><th>需求編號</th><th>供應商</th><th>狀態</th><th>總金額</th><th>發出時間</th><th></th></tr></thead>
        <tbody>
          <tr v-for="order in orders" :key="order.id">
            <td>{{ order.po_no }}</td>
            <td>{{ order.request_no }}</td>
            <td>{{ order.supplier.name }}</td>
            <td><StatusBadge :status="order.status" /></td>
            <td>{{ formatMoney(order.total_amount, order.currency) }}</td>
            <td>{{ order.issued_at ? formatDateTime(order.issued_at) : '—' }}</td>
            <td>
              <button class="secondary-button" @click="openDetail(order)">詳情</button>
              <button v-if="canManage && order.status === 'draft'" class="secondary-button" :disabled="issuing" @click="issueOrder(order)">發出</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <div v-if="showDetail && detail" class="modal-backdrop" @click.self="showDetail = false">
    <section class="detail-modal" role="dialog" aria-modal="true" aria-labelledby="po-detail-title">
      <header class="modal-header">
        <div><span class="eyebrow">{{ detail.supplier.name }}</span><h2 id="po-detail-title">{{ detail.po_no }}</h2></div>
        <button type="button" class="modal-close" aria-label="關閉" @click="showDetail = false">×</button>
      </header>
      <div class="modal-body">
        <dl class="detail-grid">
          <div><dt>狀態</dt><dd><StatusBadge :status="detail.status" /></dd></div>
          <div><dt>需求編號</dt><dd>{{ detail.request_no }}</dd></div>
          <div><dt>總金額</dt><dd>{{ formatMoney(detail.total_amount, detail.currency) }}</dd></div>
          <div><dt>發出時間</dt><dd>{{ detail.issued_at ? formatDateTime(detail.issued_at) : '尚未發出' }}</dd></div>
        </dl>
        <h2 style="margin-top: 20px;">明細</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>行號</th><th>品項</th><th>訂購數量</th><th>單價</th><th>金額</th></tr></thead>
            <tbody>
              <tr v-for="item in detail.items" :key="item.id">
                <td>{{ item.line_no }}</td>
                <td>{{ item.product_name }}</td>
                <td>{{ formatQuantity(item.quantity) }}</td>
                <td>{{ formatMoney(item.unit_price, detail.currency) }}</td>
                <td>{{ formatMoney(item.amount, detail.currency) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="canManage && detail.status === 'draft'" class="form-actions">
          <button class="primary-button" :disabled="issuing" @click="issueOrder(detail)">{{ issuing ? '發出中…' : '發出採購單' }}</button>
        </div>
      </div>
    </section>
  </div>
</template>
