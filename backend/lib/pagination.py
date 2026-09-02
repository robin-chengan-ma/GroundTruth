"""共用清單分頁工具。

沿用 `PurchaseRequestViewSet.list()`（Phase 5，已由 Robin 核准）建立的分頁慣例：
手動 `Paginator`、`page`／`page_size` 查詢參數（`page_size` 限定 10／20／50，預設 20），
回應格式固定為 `{count, page, page_size, total_pages, results}`，錯誤格式固定為
`{"detail": ..., "code": "invalid_pagination"}`（HTTP 400）。

Phase 6 補齊清單頁搜尋／篩選／分頁缺口時，所有清單端點一律呼叫本模組，
避免同一段 Paginator 邊界判斷邏輯在 11 個 ViewSet 各自重複一份。
"""

from django.core.paginator import EmptyPage, Paginator
from rest_framework import status
from rest_framework.response import Response

PAGE_SIZES = {10, 20, 50}
DEFAULT_PAGE_SIZE = 20

_TRUE_VALUES = {"1", "true", "yes"}
_FALSE_VALUES = {"0", "false", "no"}


def parse_optional_bool(raw):
    """把 `?is_active=true/false` 這類查詢參數轉成 True／False／None（未帶參數或無法辨識時）。"""
    if raw is None:
        return None
    lowered = raw.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    return None


def parse_optional_int(raw, *, field_name):
    """解析 `?category=<id>` 這類會直接拿去比對外鍵 id 的整數查詢參數。

    回傳 (value, error_response)：未帶參數時 value 為 None、error_response 為 None（不套用篩選）；
    帶了無法轉成整數的值時 value 為 None、error_response 為 400 Response，呼叫端必須直接回傳
    error_response，不可以把原始字串繼續往下傳——Django 的 `.filter(<fk>_id=<非數字字串>)`
    不會在 filter() 當下拋錯，而是等 queryset 真正被求值時才拋出未經處理的 `ValueError`，
    導致回應變成 500 而非可讀的 400。"""
    if raw is None or raw == "":
        return None, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, pagination_error(f"{field_name} 必須是整數")


def pagination_error(detail):
    return Response(
        {"detail": detail, "code": "invalid_pagination"},
        status=status.HTTP_400_BAD_REQUEST,
    )


def parse_pagination_params(request):
    """解析 page／page_size 查詢參數。回傳 (page, page_size, error_response)；
    有錯誤時 page／page_size 為 None，呼叫端應直接回傳 error_response。"""
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        return None, None, pagination_error("page 與 page_size 必須是整數")
    if page < 1:
        return None, None, pagination_error("page 必須大於 0")
    if page_size not in PAGE_SIZES:
        return None, None, pagination_error("page_size 只允許 10、20 或 50")
    return page, page_size, None


def paginate_response(request, items, *, serialize):
    """把已篩選／排序好的 queryset 或 list 依查詢參數分頁後包成 Response。

    items：已完成 search／filter／排序的 queryset 或 list。
    serialize：callable，輸入本頁的 list(page_data.object_list)，回傳可被 Response 序列化的資料。
    """
    page, page_size, error = parse_pagination_params(request)
    if error:
        return error
    paginator = Paginator(items, page_size)
    try:
        page_data = paginator.page(page)
    except EmptyPage:
        return pagination_error("page 超出有效範圍")
    return Response({
        "count": paginator.count,
        "page": page_data.number,
        "page_size": page_size,
        "total_pages": max(1, paginator.num_pages),
        "results": serialize(list(page_data.object_list)),
    })
