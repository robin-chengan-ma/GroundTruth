import { api } from '../api/client'
import type { PaginatedList } from '../types/api'

/**
 * Phase 6 主檔管理／詢價評選頁面的下拉選單（供應商／品項／分類等）需要完整清單。
 * 這批清單端點統一改用 `backend/lib/pagination.py` 的 `{count, page, page_size,
 * total_pages, results}` 分頁格式（見 `docs/ADR/discuss/phase6.md`），這裡固定用
 * 單頁上限（page_size=50）逐頁讀到 total_pages 為止，避免筆數超過 50 時選單缺漏選項。
 */
export async function fetchAllPages<T>(url: string, params: Record<string, unknown> = {}): Promise<T[]> {
  const results: T[] = []
  let page = 1
  let totalPages = 1
  do {
    const response = await api.get<PaginatedList<T>>(url, { params: { ...params, page, page_size: 50 } })
    results.push(...response.data.results)
    totalPages = response.data.total_pages
    page += 1
  } while (page <= totalPages)
  return results
}
