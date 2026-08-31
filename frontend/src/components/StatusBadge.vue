<script setup lang="ts">
defineProps<{ status: string }>()

const labels: Record<string, string> = {
  pending_verification: '驗證中',
  pending_review: '待人工複核',
  pending_approval: '待簽核',
  pending: '待處理',
  unclaimed: '未認領',
  claimed: '處理中',
  resolved: '已處理',
  approved: '已核准',
  rejected: '已駁回',
  cancelled: '已取消',
  draft: '草稿',
  submitted: '已送出',
  sourcing: '詢價中',
  awarding: '評選中',
  approval: '簽核中',
  ordered: '已下單',
  partially_received: '部分收貨',
  completed: '已完成',
  withdrawn: '已撤回',
}
</script>

<template><span class="status-badge" :data-status="status">{{ labels[status] ?? status }}</span></template>
