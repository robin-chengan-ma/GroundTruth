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
}
</script>

<template><span class="status-badge" :data-status="status">{{ labels[status] ?? status }}</span></template>
