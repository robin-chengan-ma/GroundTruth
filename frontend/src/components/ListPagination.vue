<script setup lang="ts">
defineProps<{
  page: number
  pageSize: 10 | 20 | 50
  totalPages: number
  count: number
  label: string
}>()

const emit = defineEmits<{
  (event: 'change-page', page: number): void
  (event: 'change-page-size', domEvent: Event): void
}>()
</script>

<template>
  <footer class="pagination-bar">
    <span>共 {{ count }} 筆</span>
    <label>每頁
      <select aria-label="每頁筆數" :value="pageSize" @change="emit('change-page-size', $event)">
        <option :value="10">10 筆</option>
        <option :value="20">20 筆</option>
        <option :value="50">50 筆</option>
      </select>
    </label>
    <nav :aria-label="label">
      <button type="button" class="secondary-button" :disabled="page <= 1" @click="emit('change-page', page - 1)">上一頁</button>
      <strong>{{ page }} / {{ totalPages }}</strong>
      <button type="button" class="secondary-button" :disabled="page >= totalPages" @click="emit('change-page', page + 1)">下一頁</button>
    </nav>
  </footer>
</template>
