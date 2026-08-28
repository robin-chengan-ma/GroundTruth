<script setup lang="ts">
import axios from 'axios'
import { onMounted, ref } from 'vue'

import { api } from '../api/client'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import type { Paginated, Quote } from '../types/api'

const auth = useAuthStore()
const quotes = ref<Quote[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  try {
    quotes.value = (await api.get<Paginated<Quote>>('/quotes/')).data.results
  } catch {
    error.value = '無法載入採購清單'
  } finally {
    loading.value = false
  }
}

async function withdraw(quote: Quote) {
  if (!window.confirm(`確定撤回採購單 #${quote.id}？撤回後需重新提出詢價。`)) return
  try {
    await api.post(`/quotes/${quote.id}/withdraw/`)
    await load()
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '撤回失敗') : '撤回失敗'
  }
}

onMounted(load)
</script>

<template>
  <header class="page-header"><div><p>採購流程</p><h1>採購清單</h1></div><button class="secondary-button" @click="load">重新整理</button></header>
  <section class="surface table-surface">
    <p v-if="loading" class="empty-state">載入中…</p>
    <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-else-if="quotes.length === 0" class="empty-state">目前沒有採購單。</p>
    <div v-else class="table-scroll">
      <table>
        <thead><tr><th>單號</th><th>品項</th><th>供應商</th><th>申請人</th><th>數量</th><th>總金額</th><th>狀態</th><th>價格提示</th><th></th></tr></thead>
        <tbody>
          <tr v-for="quote in quotes" :key="quote.id">
            <td>#{{ quote.id }}</td><td>{{ quote.product_name }}</td><td>{{ quote.supplier_name }}</td><td>{{ quote.user_name }}</td>
            <td>{{ quote.quantity }}</td><td>{{ quote.currency }} {{ Number(quote.total_amount).toLocaleString() }}</td><td><StatusBadge :status="quote.status" /></td>
            <td><span v-if="quote.price_deviation_pct && Math.abs(Number(quote.price_deviation_pct)) > 20" class="warning-text">偏離 {{ quote.price_deviation_pct }}%</span><span v-else>—</span></td>
            <td><button v-if="quote.user === auth.user?.id && quote.status === 'pending_approval'" class="text-button danger" @click="withdraw(quote)">撤回</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
