<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import type { InventoryBalance, InventoryMovement, Paginated } from '../types/api'
import { formatDateTime, formatQuantity } from '../utils/formatters'

const balances = ref<InventoryBalance[]>([])
const loadingBalances = ref(true)
const balanceError = ref('')

const movements = ref<InventoryMovement[]>([])
const movementsNext = ref<string | null>(null)
const loadingMovements = ref(true)
const movementError = ref('')

const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  receipt_accept: '驗收入庫',
  return_out: '退貨出庫',
  issue_out: '領用出庫',
  adjustment_in: '調整增加',
  adjustment_out: '調整減少',
  reversal: '沖銷',
  migration_assumed_receipt: '歷史資料轉入',
}

async function loadBalances() {
  loadingBalances.value = true
  balanceError.value = ''
  try {
    balances.value = (await api.get<Paginated<InventoryBalance>>('/inventory-balances/')).data.results
  } catch (reason) {
    balanceError.value = apiErrorMessage(reason, '無法載入庫存餘額（需 inventory.read 權限）')
  } finally {
    loadingBalances.value = false
  }
}

async function loadMovements() {
  loadingMovements.value = true
  movementError.value = ''
  try {
    const response = (await api.get<Paginated<InventoryMovement>>('/inventory-movements/')).data
    movements.value = response.results
    movementsNext.value = response.next
  } catch (reason) {
    movementError.value = apiErrorMessage(reason, '無法載入庫存流水帳（需 inventory.read 權限）')
  } finally {
    loadingMovements.value = false
  }
}

async function loadMoreMovements() {
  if (!movementsNext.value) return
  try {
    const response = (await api.get<Paginated<InventoryMovement>>(movementsNext.value)).data
    movements.value.push(...response.results)
    movementsNext.value = response.next
  } catch (reason) {
    movementError.value = apiErrorMessage(reason, '載入更多流水帳失敗')
  }
}

function load() {
  void loadBalances()
  void loadMovements()
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="庫存與建議" title="庫存">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>

  <section class="detail-section surface" style="margin-bottom: 24px;">
    <header class="section-heading"><div><span class="eyebrow">庫存餘額</span><h3>可用量查詢快照</h3></div></header>
    <p v-if="loadingBalances" class="empty-state">載入中…</p>
    <p v-else-if="balanceError" class="error-message" role="alert">{{ balanceError }}</p>
    <p v-else-if="balances.length === 0" class="empty-state">目前沒有庫存餘額資料。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>品項</th><th>在庫</th><th>已保留</th><th>在途</th><th>可用量</th><th>低量門檻</th><th>更新時間</th></tr></thead>
        <tbody>
          <tr v-for="balance in balances" :key="balance.product">
            <td>{{ balance.product_name }}</td>
            <td>{{ formatQuantity(balance.on_hand_quantity) }}</td>
            <td>{{ formatQuantity(balance.reserved_quantity) }}</td>
            <td>{{ formatQuantity(balance.in_transit_quantity) }}</td>
            <td><strong>{{ formatQuantity(balance.available_quantity) }}</strong></td>
            <td>
              <span v-if="balance.threshold === null">—</span>
              <span v-else-if="Number(balance.on_hand_quantity) < balance.threshold" class="warning-text">{{ balance.threshold }}（低於門檻）</span>
              <span v-else>{{ balance.threshold }}</span>
            </td>
            <td>{{ formatDateTime(balance.updated_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="surface table-surface">
    <header class="section-heading" style="padding: 22px 22px 0;">
      <div><span class="eyebrow">庫存流水帳</span><h3>不可覆寫異動紀錄</h3></div>
    </header>
    <p v-if="loadingMovements" class="empty-state">載入中…</p>
    <p v-else-if="movementError" class="error-message" role="alert">{{ movementError }}</p>
    <p v-else-if="movements.length === 0" class="empty-state">目前沒有庫存異動紀錄。</p>
    <template v-else>
      <div class="table-scroll">
        <table>
          <thead><tr><th>品項</th><th>異動類型</th><th>數量增減</th><th>來源</th><th>影響餘額</th><th>過帳者</th><th>過帳時間</th></tr></thead>
          <tbody>
            <tr v-for="movement in movements" :key="movement.id">
              <td>{{ movement.product_name }}</td>
              <td>{{ MOVEMENT_TYPE_LABELS[movement.movement_type] ?? movement.movement_type }}</td>
              <td>{{ Number(movement.quantity_delta) > 0 ? '+' : '' }}{{ formatQuantity(movement.quantity_delta) }}</td>
              <td>{{ movement.reference_type }} #{{ movement.reference_id }}</td>
              <td>{{ movement.affects_balance ? '是' : '否' }}</td>
              <td>{{ movement.posted_by_name || '系統' }}</td>
              <td>{{ formatDateTime(movement.posted_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer v-if="movementsNext" class="pagination-bar">
        <button type="button" class="secondary-button" @click="loadMoreMovements">載入更多</button>
      </footer>
    </template>
  </section>
</template>
