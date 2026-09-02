import { reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { PaginatedList } from '../types/api'

function allowedPageSize(value: unknown): 10 | 20 | 50 {
  const parsed = Number(value)
  return parsed === 10 || parsed === 50 ? parsed : 20
}

function positivePage(value: unknown) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1
}

function queryString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/**
 * Phase 6 清單頁共用的搜尋／篩選／分頁狀態管理（URL 同步），沿用
 * `PurchaseRequestListView.vue`（Phase 5，已核准）的 page／page_size／URL 同步慣例，
 * 並補上該頁本身也缺少的搜尋框與篩選下拉狀態，供 10 個 Phase 6 清單頁共用一份實作，
 * 避免同一段分頁／查詢參數同步邏輯重複貼 10 次。
 *
 * filterKeys：本頁支援的篩選查詢參數名稱（例如 ['status']、['status', 'tier']）。
 */
export function useListQuery<T>(
  fetcher: (params: Record<string, string | number>) => Promise<PaginatedList<T>>,
  filterKeys: string[] = [],
) {
  const route = useRoute()
  const router = useRouter()

  const items = ref<T[]>([])
  const loading = ref(true)
  const error = ref('')
  const count = ref(0)
  const totalPages = ref(1)

  const page = ref(positivePage(route.query.page))
  const pageSize = ref<10 | 20 | 50>(allowedPageSize(route.query.page_size))
  const search = ref(queryString(route.query.search))
  const filters = reactive<Record<string, string>>({})
  for (const key of filterKeys) filters[key] = queryString(route.query[key])

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const params: Record<string, string | number> = { page: page.value, page_size: pageSize.value }
      if (search.value) params.search = search.value
      for (const key of filterKeys) {
        if (filters[key]) params[key] = filters[key]
      }
      const response = await fetcher(params)
      items.value = response.results
      count.value = response.count
      totalPages.value = response.total_pages
      page.value = response.page
    } catch {
      error.value = '無法載入清單'
    } finally {
      loading.value = false
    }
  }

  function currentQuery(): Record<string, string> {
    const query: Record<string, string> = { page: String(page.value), page_size: String(pageSize.value) }
    if (search.value) query.search = search.value
    for (const key of filterKeys) {
      if (filters[key]) query[key] = filters[key]
    }
    return query
  }

  function pushQuery(overrides: Record<string, string | undefined>) {
    const query = currentQuery()
    for (const [key, value] of Object.entries(overrides)) {
      if (value) query[key] = value
      else delete query[key]
    }
    router.replace({ query })
  }

  function changePage(nextPage: number) {
    pushQuery({ page: String(nextPage) })
  }

  function changePageSize(event: Event) {
    pushQuery({ page: '1', page_size: String(allowedPageSize((event.target as HTMLSelectElement).value)) })
  }

  function applySearch() {
    pushQuery({ page: '1', search: search.value || undefined })
  }

  function applyFilter(key: string, value: string) {
    filters[key] = value
    pushQuery({ page: '1', [key]: value || undefined })
  }

  function resetFilters() {
    search.value = ''
    for (const key of filterKeys) filters[key] = ''
    const overrides: Record<string, string | undefined> = { page: '1', search: undefined }
    for (const key of filterKeys) overrides[key] = undefined
    pushQuery(overrides)
  }

  watch(
    () => [route.query.page, route.query.page_size, route.query.search, ...filterKeys.map((key) => route.query[key])],
    () => {
      page.value = positivePage(route.query.page)
      pageSize.value = allowedPageSize(route.query.page_size)
      search.value = queryString(route.query.search)
      for (const key of filterKeys) filters[key] = queryString(route.query[key])
      void load()
    },
  )

  return {
    items,
    loading,
    error,
    count,
    totalPages,
    page,
    pageSize,
    search,
    filters,
    load,
    applySearch,
    applyFilter,
    resetFilters,
    changePage,
    changePageSize,
  }
}
