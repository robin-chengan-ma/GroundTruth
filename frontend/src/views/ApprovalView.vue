<script setup lang="ts">
import axios from 'axios'
import { onMounted, reactive, ref } from 'vue'

import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import type { ApprovalCase, ApprovalStep } from '../types/api'

const cases = ref<ApprovalCase[]>([])
const reasons = reactive<Record<number, string>>({})
const error = ref('')
const loading = ref(true)
const actingStepId = ref<number | null>(null)

const stepTypeLabels: Record<ApprovalStep['step_type'], string> = {
  waiver_exception: '必要條件例外覆核',
  amount_approval: '金額簽核',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    cases.value = (await api.get<ApprovalCase[]>('/approval-cases/')).data
  } catch {
    error.value = '無法載入簽核案件'
  } finally {
    loading.value = false
  }
}

async function claim(step: ApprovalStep) {
  error.value = ''
  actingStepId.value = step.id
  try {
    await api.post(`/approval-steps/${step.id}/claim/`)
    await load()
  } catch (reason) {
    error.value = axios.isAxiosError(reason) ? (reason.response?.data?.detail ?? '認領失敗') : '認領失敗'
  } finally {
    actingStepId.value = null
  }
}

async function decide(step: ApprovalStep, decision: 'approved' | 'rejected') {
  const reason = (reasons[step.id] ?? '').trim()
  if (!reason) {
    error.value = '請先填寫簽核理由'
    return
  }
  error.value = ''
  actingStepId.value = step.id
  try {
    await api.post(`/approval-steps/${step.id}/decide/`, { decision, reason })
    delete reasons[step.id]
    await load()
  } catch (failure) {
    error.value = axios.isAxiosError(failure) ? (failure.response?.data?.detail ?? '決議失敗') : '決議失敗'
  } finally {
    actingStepId.value = null
  }
}

onMounted(load)
</script>

<template>
  <PageHeader eyebrow="待辦工作" title="簽核工作區" subtitle="依關卡認領並保留每次決議理由。">
    <template #actions><button class="secondary-button" type="button" @click="load">重新整理</button></template>
  </PageHeader>
  <p v-if="error" class="error-message" role="alert">{{ error }}</p>
  <p v-if="loading" class="surface empty-state">載入中…</p>
  <p v-else-if="cases.length === 0" class="surface empty-state">目前沒有符合資格的簽核案件。</p>
  <div v-else class="approval-case-list">
    <article v-for="item in cases" :key="item.id" class="surface approval-case-card">
      <header>
        <div><small>{{ item.request_no }}</small><h2>{{ item.purpose }}</h2></div>
        <StatusBadge :status="item.status" />
      </header>
      <dl class="approval-case-summary">
        <div><dt>申請人</dt><dd>{{ item.requester.name }}</dd></div>
        <div><dt>簽核政策</dt><dd>{{ item.policy.name }}</dd></div>
        <div><dt>簽核總額</dt><dd>{{ item.currency }} {{ Number(item.total_amount).toLocaleString() }}</dd></div>
        <div><dt>送簽時間</dt><dd>{{ new Date(item.submitted_at).toLocaleString('zh-TW') }}</dd></div>
      </dl>
      <section class="approval-steps" aria-label="簽核關卡">
        <article v-for="step in item.steps" :key="step.id" class="approval-step">
          <header>
            <div><strong>關卡 {{ step.sequence }}｜{{ stepTypeLabels[step.step_type] }}</strong><small>指定角色：{{ step.role.code }}</small></div>
            <StatusBadge :status="step.status" />
          </header>
          <p v-if="step.claimed_by" class="step-actor">已由 {{ step.claimed_by.name }} 認領</p>
          <p v-if="step.decision_reason" class="step-decision">決議理由：{{ step.decision_reason }}</p>
          <footer v-if="step.can_claim || step.can_decide">
            <button v-if="step.can_claim" class="primary-button" data-action="claim" type="button" :disabled="actingStepId === step.id" @click="claim(step)">認領案件</button>
            <template v-if="step.can_decide">
              <label><span>簽核理由</span><textarea v-model="reasons[step.id]" aria-label="簽核理由" rows="2" placeholder="請輸入核准或駁回理由" /></label>
              <div class="approval-decision-actions">
                <button class="secondary-button danger" data-action="reject" type="button" :disabled="actingStepId === step.id" @click="decide(step, 'rejected')">駁回</button>
                <button class="primary-button" data-action="approve" type="button" :disabled="actingStepId === step.id" @click="decide(step, 'approved')">核准</button>
              </div>
            </template>
          </footer>
        </article>
      </section>
    </article>
  </div>
</template>
