<script setup lang="ts">
defineProps<{
  eyebrow: string
  title: string
  description?: string
}>()
</script>

<template>
  <header class="page-header">
    <div>
      <p>{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <small v-if="description" class="page-description">{{ description }}</small>
    </div>
    <div v-if="$slots.actions" class="page-actions"><slot name="actions" /></div>
  </header>
</template>
