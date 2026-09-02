<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { canAccess, navigationGroups } from '../navigation'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const mobileOpen = ref(false)
const collapsedGroups = ref(new Set<string>())

const visibleGroups = computed(() =>
  navigationGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        canAccess(auth.user?.permissions ?? [], item.permissions, item.anyPermissions),
      ),
    }))
    .filter((group) => group.items.length > 0),
)

function toggleGroup(label: string) {
  const next = new Set(collapsedGroups.value)
  if (next.has(label)) next.delete(label)
  else next.add(label)
  collapsedGroups.value = next
}

function closeMobileNavigation() {
  mobileOpen.value = false
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') closeMobileNavigation()
}

async function logout() {
  await auth.logout()
  await router.push('/login')
}

onMounted(() => window.addEventListener('keydown', handleEscape))
onBeforeUnmount(() => window.removeEventListener('keydown', handleEscape))
</script>

<template>
  <div class="app-shell" :class="{ 'navigation-open': mobileOpen }">
    <header class="mobile-header">
      <button class="menu-button" type="button" aria-label="開啟導覽" :aria-expanded="mobileOpen" @click="mobileOpen = true">
        <span></span><span></span><span></span>
      </button>
      <RouterLink class="mobile-brand" to="/"><span>G</span> GroundTruth</RouterLink>
    </header>

    <button v-if="mobileOpen" class="navigation-backdrop" type="button" aria-label="關閉導覽" @click="closeMobileNavigation"></button>

    <aside class="sidebar">
      <div class="sidebar-heading">
        <RouterLink class="brand" to="/" @click="closeMobileNavigation"><span>G</span> GroundTruth</RouterLink>
        <button class="sidebar-close" type="button" aria-label="關閉導覽" @click="closeMobileNavigation">×</button>
      </div>
      <nav aria-label="主要導覽">
        <section v-for="group in visibleGroups" :key="group.label" class="nav-group">
          <button class="nav-group-button" type="button" :aria-expanded="!collapsedGroups.has(group.label)" @click="toggleGroup(group.label)">
            <span>{{ group.label }}</span><span aria-hidden="true">{{ collapsedGroups.has(group.label) ? '＋' : '−' }}</span>
          </button>
          <div v-show="!collapsedGroups.has(group.label)" class="nav-items">
            <RouterLink v-for="item in group.items" :key="item.to" :to="item.to" @click="closeMobileNavigation">{{ item.label }}</RouterLink>
          </div>
        </section>
      </nav>
      <div class="account-panel">
        <strong>{{ auth.user?.name }}</strong>
        <small>{{ auth.user?.role }}</small>
        <button class="text-button" type="button" @click="logout">登出</button>
      </div>
    </aside>
    <main class="workspace"><slot /></main>
  </div>
</template>
