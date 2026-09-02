<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import { apiErrorMessage } from '../api/errors'
import PageHeader from '../components/PageHeader.vue'
import type { AuditDashboardStats } from '../types/api'
import { formatMoney, formatQuantity } from '../utils/formatters'

const stats = ref<AuditDashboardStats | null>(null)
const loading = ref(true)
const error = ref('')
const filters = reactive({ date_from: '', date_to: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    stats.value = (await api.get<AuditDashboardStats>('/audit-dashboard/stats/', {
      params: { date_from: filters.date_from || undefined, date_to: filters.date_to || undefined },
    })).data
  } catch (reason) {
    error.value = apiErrorMessage(reason, '無法載入採購稽核與流程健康總覽（僅系統管理員可查）')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="稽核" title="採購稽核與流程健康總覽">
    <template #actions><button class="secondary-button" @click="load">重新整理</button></template>
  </PageHeader>

  <section class="surface" style="padding: 20px 22px; margin-bottom: 24px;">
    <form class="editor-grid" style="align-items: end;" @submit.prevent="load">
      <div>
        <label for="dashboard-date-from">統計期間（起）</label>
        <input id="dashboard-date-from" v-model="filters.date_from" type="date" />
      </div>
      <div>
        <label for="dashboard-date-to">統計期間（迄）</label>
        <input id="dashboard-date-to" v-model="filters.date_to" type="date" />
      </div>
      <div class="form-actions" style="margin-top: 0;">
        <button type="submit" class="primary-button">套用篩選</button>
      </div>
    </form>
  </section>

  <p v-if="loading" class="empty-state surface">載入中…</p>
  <p v-else-if="error" class="error-message" role="alert">{{ error }}</p>

  <template v-else-if="stats">
    <div class="card-grid" style="margin-bottom: 24px;">
      <article class="surface approval-card">
        <header><div><small>FR-1</small><h2>AI 候選採用情況</h2></div></header>
        <dl>
          <div><dt>直接採用</dt><dd>{{ stats.candidate_quality.direct_adoption_count }}</dd></div>
          <div><dt>人工修正</dt><dd>{{ stats.candidate_quality.corrected_count }}</dd></div>
          <div><dt>直接採用率</dt><dd>{{ stats.candidate_quality.direct_adoption_rate_pct ? `${stats.candidate_quality.direct_adoption_rate_pct}%` : '—' }}</dd></div>
        </dl>
        <p class="muted-text">只統計 AI 候選第一次存成草稿前，使用者是否修改欄位；不保存原始輸入或欄位內容。</p>
      </article>

      <article class="surface approval-card">
        <header><div><small>FR-5</small><h2>品質驗收</h2></div></header>
        <dl>
          <div><dt>驗收明細</dt><dd>{{ stats.quality.inspection_count }}</dd></div>
          <div><dt>合格數量</dt><dd>{{ formatQuantity(stats.quality.accepted_quantity) }}</dd></div>
          <div><dt>瑕疵／拒收</dt><dd>{{ formatQuantity(stats.quality.exception_quantity) }}</dd></div>
          <div><dt>數量合格率</dt><dd>{{ stats.quality.acceptance_rate_pct ? `${stats.quality.acceptance_rate_pct}%` : '—' }}</dd></div>
        </dl>
      </article>

      <article class="surface approval-card">
        <header><div><small>FR-2</small><h2>主檔媒合健康度</h2></div></header>
        <dl>
          <div><dt>供應商命中</dt><dd>{{ stats.supplier_match.supplier_matched_count }}</dd></div>
          <div><dt>供應商未命中</dt><dd>{{ stats.supplier_match.supplier_unmatched_count }}</dd></div>
          <div><dt>品項命中</dt><dd>{{ stats.supplier_match.product_matched_count }}</dd></div>
          <div><dt>品項未命中</dt><dd>{{ stats.supplier_match.product_unmatched_count }}</dd></div>
          <div><dt>模糊比對總數</dt><dd>{{ stats.supplier_match.fuzzy_match_total }}</dd></div>
          <div><dt>核准</dt><dd>{{ stats.supplier_match.fuzzy_match_approved }}</dd></div>
          <div><dt>駁回</dt><dd>{{ stats.supplier_match.fuzzy_match_rejected }}</dd></div>
          <div><dt>待處理</dt><dd>{{ stats.supplier_match.fuzzy_match_pending }}</dd></div>
        </dl>
      </article>

      <article class="surface approval-card">
        <header><div><small>FR-3</small><h2>複核佇列處理狀況</h2></div></header>
        <dl>
          <div><dt>待處理</dt><dd>{{ stats.manual_review_queue.pending_count }}</dd></div>
          <div><dt>已處理</dt><dd>{{ stats.manual_review_queue.processed_count }}</dd></div>
          <div><dt>核准</dt><dd>{{ stats.manual_review_queue.by_decision.approved }}</dd></div>
          <div><dt>駁回</dt><dd>{{ stats.manual_review_queue.by_decision.rejected }}</dd></div>
        </dl>
      </article>

      <article class="surface approval-card">
        <header><div><small>FR-4</small><h2>價格異常</h2></div></header>
        <dl>
          <div><dt>門檻</dt><dd>{{ stats.price_anomaly.threshold_pct }}%</dd></div>
          <div><dt>已檢查</dt><dd>{{ stats.price_anomaly.checked_count }}</dd></div>
          <div><dt>異常件數</dt><dd>{{ stats.price_anomaly.anomaly_count }}</dd></div>
          <div><dt>異常比例</dt><dd>{{ stats.price_anomaly.anomaly_rate_pct ? `${stats.price_anomaly.anomaly_rate_pct}%` : '—' }}</dd></div>
        </dl>
      </article>
    </div>

    <section class="surface table-surface">
      <header class="section-heading" style="padding: 22px 22px 0;"><div><span class="eyebrow">FR-4</span><h3>價格異常清單</h3></div></header>
      <p v-if="stats.price_anomaly.items.length === 0" class="empty-state">目前沒有超過門檻的價格異常案件。</p>
      <div v-else class="table-scroll">
        <table>
          <thead><tr><th>RFQ</th><th>供應商</th><th>品項</th><th>報價單價</th><th>歷史均價</th><th>偏差</th></tr></thead>
          <tbody>
            <tr v-for="item in stats.price_anomaly.items" :key="item.supplier_quote_item_id">
              <td>{{ item.rfq_no }}</td>
              <td>{{ item.supplier_name }}</td>
              <td>{{ item.product_name }}</td>
              <td>{{ formatMoney(item.unit_price, item.currency) }}</td>
              <td>{{ formatMoney(item.historical_average, item.currency) }}</td>
              <td class="warning-text">{{ formatQuantity(item.deviation_pct) }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>
</template>
