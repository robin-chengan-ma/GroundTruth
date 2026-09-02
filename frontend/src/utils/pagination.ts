import { api } from '../api/client'
import type { Paginated } from '../types/api'

/**
 * Phase 6 主檔管理／詢價評選頁面的下拉選單（供應商／品項／分類等）需要完整清單，
 * 但後端維持標準 DRF PageNumberPagination（PAGE_SIZE=50，無 page_size query 覆寫）。
 * 這裡沿著 `next` 連結把所有分頁讀完，避免筆數超過 50 時選單缺漏選項。
 */
export async function fetchAllPages<T>(url: string, params: Record<string, unknown> = {}): Promise<T[]> {
  const results: T[] = []
  let nextUrl: string | null = url
  let nextParams: Record<string, unknown> | undefined = params
  while (nextUrl) {
    const response: { data: Paginated<T> } = await api.get<Paginated<T>>(
      nextUrl,
      nextParams ? { params: nextParams } : undefined,
    )
    results.push(...response.data.results)
    nextUrl = response.data.next
    nextParams = undefined
  }
  return results
}
