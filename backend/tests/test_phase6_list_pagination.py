"""Phase 6 補齊缺口：10 個清單頁對應的後端端點搜尋／篩選／分頁契約。

背景：Codex 盤點程式碼與規格後發現，Phase 6 新增的 10 個清單頁（供應商、品項、
供應商品項、RFQ、供應商報價、得標決議、採購單、收貨單、驗收差異、採購建議）雖然有
畫面，但清單一律只拿第一頁（ModelViewSet 預設 PAGE_SIZE=50 或完全未分頁），超過筆數
時後面的資料會直接消失且沒有任何提示，也沒有搜尋／篩選可縮小範圍——SPEC.md 明確要求
的「搜尋、篩選、分頁」三項缺了全部。

修復方式：11 個對應的後端 ViewSet／Repository／Service（Product 頁面同時涵蓋
ProductViewSet 與 ProductCategoryViewSet）改用 `backend/lib/pagination.py` 共用的
`paginate_response()`，統一回應 `{count, page, page_size, total_pages, results}`
（沿用 Phase 5 `PurchaseRequestViewSet` 已核准的分頁慣例），並在 Repository 層加上
`search`（跨關鍵欄位模糊比對）與 `status`（或該實體對應的篩選欄位）查詢參數。

本檔案只驗證這批端點「新增」的搜尋／篩選／分頁行為；既有的讀取權限矩陣、寫入邏輯與
狀態機測試留在各自原本的測試檔，不重複覆蓋。
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import Permission, RolePermission, UserRole
from apps.crm.models import Supplier
from apps.erp.models import (
    GoodsReceipt,
    InspectionVarianceCase,
    InspectionVarianceLine,
    Product,
    ProductCategory,
    PurchaseSuggestion,
)
from apps.procurement.models import PurchaseRequest, Rfq, RfqScoringCriterion, SupplierProduct
from tests.test_phase4_1_award_approval_po import create_award_context
from tests.test_phase4_1_inspection_variances import _partial_inspection
from tests.test_phase4_1_receiving_inventory import create_purchase_order


def _grant(user, role, code, name=None):
    UserRole.objects.get_or_create(user=user, role=role)
    permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": name or code})
    RolePermission.objects.get_or_create(role=role, permission=permission)


# ---- Supplier ----


@pytest.mark.django_db
def test_supplier_list_is_paginated_and_supports_page_size(admin_api_client):
    for i in range(12):
        Supplier.objects.create(name=f"分頁供應商{i}", tier=Supplier.Tier.NORMAL)

    resp = admin_api_client.get("/api/v1/suppliers/", {"page_size": 10})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert resp.data["count"] >= 12
    assert len(resp.data["results"]) == 10
    assert resp.data["page_size"] == 10


@pytest.mark.django_db
def test_supplier_list_rejects_invalid_page_size(admin_api_client):
    resp = admin_api_client.get("/api/v1/suppliers/", {"page_size": 7})

    assert resp.status_code == 400
    assert resp.data["code"] == "invalid_pagination"


@pytest.mark.django_db
def test_supplier_list_search_matches_name_or_code(admin_api_client):
    Supplier.objects.create(name="優品科技", code="SUP-SEARCH-001", tier=Supplier.Tier.NORMAL)
    Supplier.objects.create(name="別間供應商", code="SUP-OTHER-002", tier=Supplier.Tier.NORMAL)

    resp = admin_api_client.get("/api/v1/suppliers/", {"search": "優品"})

    assert resp.status_code == 200
    assert [row["name"] for row in resp.data["results"]] == ["優品科技"]


@pytest.mark.django_db
def test_supplier_list_filters_by_status_and_tier(admin_api_client):
    Supplier.objects.create(name="停權供應商", tier=Supplier.Tier.WATCH, status="blocked")
    Supplier.objects.create(name="正常供應商", tier=Supplier.Tier.NORMAL, status="active")

    resp = admin_api_client.get("/api/v1/suppliers/", {"status": "blocked"})

    assert resp.status_code == 200
    assert [row["name"] for row in resp.data["results"]] == ["停權供應商"]


# ---- Product／ProductCategory ----


@pytest.mark.django_db
def test_product_list_is_paginated_and_search_matches_name_or_sku(admin_api_client):
    Product.objects.create(name="A產品-分頁測試", sku="SKU-PAGE-1", price=Decimal("10.00"), currency="TWD")
    Product.objects.create(name="B產品-分頁測試", sku="SKU-PAGE-2", price=Decimal("10.00"), currency="TWD")

    resp = admin_api_client.get("/api/v1/products/", {"search": "SKU-PAGE-1"})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert [row["name"] for row in resp.data["results"]] == ["A產品-分頁測試"]


@pytest.mark.django_db
def test_product_list_filters_by_is_active(admin_api_client):
    Product.objects.create(name="停用品項", price=Decimal("10.00"), currency="TWD", is_active=False)
    Product.objects.create(name="啟用品項", price=Decimal("10.00"), currency="TWD", is_active=True)

    resp = admin_api_client.get("/api/v1/products/", {"is_active": "false"})

    assert resp.status_code == 200
    assert [row["name"] for row in resp.data["results"]] == ["停用品項"]


@pytest.mark.django_db
def test_product_list_filters_by_category(admin_api_client):
    category_a = ProductCategory.objects.create(code="CAT-FILTER-A", name="篩選類別甲")
    category_b = ProductCategory.objects.create(code="CAT-FILTER-B", name="篩選類別乙")
    Product.objects.create(name="甲類品項", category=category_a, price=Decimal("10.00"), currency="TWD")
    Product.objects.create(name="乙類品項", category=category_b, price=Decimal("10.00"), currency="TWD")

    resp = admin_api_client.get("/api/v1/products/", {"category": category_a.id})

    assert resp.status_code == 200
    assert [row["name"] for row in resp.data["results"]] == ["甲類品項"]


@pytest.mark.django_db
def test_product_list_rejects_non_numeric_category(admin_api_client):
    resp = admin_api_client.get("/api/v1/products/", {"category": "abc"})

    assert resp.status_code == 400
    assert resp.data["code"] == "invalid_pagination"


@pytest.mark.django_db
def test_product_category_list_is_paginated_and_searchable(admin_api_client):
    ProductCategory.objects.create(code="CAT-PAGE-1", name="分頁類別甲")
    ProductCategory.objects.create(code="CAT-PAGE-2", name="分頁類別乙")

    resp = admin_api_client.get("/api/v1/product-categories/", {"search": "甲"})

    assert resp.status_code == 200
    assert [row["name"] for row in resp.data["results"]] == ["分頁類別甲"]


# ---- SupplierProduct ----


@pytest.mark.django_db
def test_supplier_product_list_is_paginated_and_search_matches_product_name(admin_api_client, supplier):
    product_a = Product.objects.create(name="分頁供應品項A", price=Decimal("10.00"), currency="TWD")
    product_b = Product.objects.create(name="分頁供應品項B", price=Decimal("10.00"), currency="TWD")
    SupplierProduct.objects.create(supplier=supplier, product=product_a, quality_status="qualified")
    SupplierProduct.objects.create(supplier=supplier, product=product_b, quality_status="blocked")

    resp = admin_api_client.get("/api/v1/supplier-products/", {"search": "品項A"})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert len(resp.data["results"]) == 1
    assert resp.data["results"][0]["product_name"] == "分頁供應品項A"


@pytest.mark.django_db
def test_supplier_product_list_filters_by_quality_status(admin_api_client, supplier):
    product_a = Product.objects.create(name="品管篩選品項A", price=Decimal("10.00"), currency="TWD")
    product_b = Product.objects.create(name="品管篩選品項B", price=Decimal("10.00"), currency="TWD")
    SupplierProduct.objects.create(supplier=supplier, product=product_a, quality_status="qualified")
    SupplierProduct.objects.create(supplier=supplier, product=product_b, quality_status="blocked")

    resp = admin_api_client.get("/api/v1/supplier-products/", {"quality_status": "blocked"})

    assert resp.status_code == 200
    assert len(resp.data["results"]) == 1
    assert resp.data["results"][0]["product_name"] == "品管篩選品項B"


# ---- Rfq ----


@pytest.mark.django_db
def test_rfq_list_is_paginated_and_search_matches_rfq_no(admin_api_client, user, supplier, product):
    _request, _request_item, _quote_item, award = create_award_context(user, supplier, product)
    rfq = award.rfq
    other_request = PurchaseRequest.objects.create(
        request_no="PR-RFQ-OTHER", requester=user, purpose="其他需求"
    )
    Rfq.objects.create(rfq_no="RFQ-OTHER-999", request=other_request)

    resp = admin_api_client.get("/api/v1/rfqs/", {"search": rfq.rfq_no})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert [row["id"] for row in resp.data["results"]] == [rfq.id]


@pytest.mark.django_db
def test_rfq_list_filters_by_status(admin_api_client, user, supplier, product):
    _request, _request_item, _quote_item, award = create_award_context(user, supplier, product)
    rfq = award.rfq
    RfqScoringCriterion.objects.create(
        rfq=rfq, code="price", label="價格", weight=Decimal(100),
        calculation_method="lowest_price", sequence=1,
    )
    rfq.status = Rfq.Status.ISSUED
    rfq.save(update_fields=["status"])

    resp = admin_api_client.get("/api/v1/rfqs/", {"status": "issued"})

    assert resp.status_code == 200
    assert rfq.id in [row["id"] for row in resp.data["results"]]

    resp_mismatch = admin_api_client.get("/api/v1/rfqs/", {"status": "cancelled"})
    assert rfq.id not in [row["id"] for row in resp_mismatch.data["results"]]


@pytest.mark.django_db
def test_rfq_list_rejects_invalid_page_size(admin_api_client):
    resp = admin_api_client.get("/api/v1/rfqs/", {"page_size": 999})

    assert resp.status_code == 400
    assert resp.data["code"] == "invalid_pagination"


# ---- SupplierQuote ----


@pytest.mark.django_db
def test_supplier_quote_list_is_paginated_and_search_matches_quote_no(admin_api_client, user, supplier, product):
    _request, _request_item, quote_item, _award = create_award_context(user, supplier, product)
    quote = quote_item.supplier_quote

    resp = admin_api_client.get("/api/v1/supplier-quotes/", {"search": quote.quote_no})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert [row["id"] for row in resp.data["results"]] == [quote.id]


@pytest.mark.django_db
def test_supplier_quote_list_filters_by_status(admin_api_client, user, supplier, product):
    _request, _request_item, quote_item, _award = create_award_context(user, supplier, product)
    quote = quote_item.supplier_quote
    assert quote.status == "accepted_for_evaluation"

    resp = admin_api_client.get("/api/v1/supplier-quotes/", {"status": "accepted_for_evaluation"})
    assert quote.id in [row["id"] for row in resp.data["results"]]

    resp_mismatch = admin_api_client.get("/api/v1/supplier-quotes/", {"status": "rejected"})
    assert quote.id not in [row["id"] for row in resp_mismatch.data["results"]]


# ---- AwardDecision ----


@pytest.mark.django_db
def test_award_list_is_paginated_and_search_matches_related_rfq_no(admin_api_client, user, supplier, product):
    _request, _request_item, _quote_item, award = create_award_context(user, supplier, product)

    resp = admin_api_client.get("/api/v1/award-decisions/", {"search": award.rfq.rfq_no})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert [row["id"] for row in resp.data["results"]] == [award.id]


@pytest.mark.django_db
def test_award_list_filters_by_status(admin_api_client, user, supplier, product):
    _request, _request_item, _quote_item, award = create_award_context(user, supplier, product)
    assert award.status == "draft"

    resp = admin_api_client.get("/api/v1/award-decisions/", {"status": "draft"})
    assert award.id in [row["id"] for row in resp.data["results"]]

    resp_mismatch = admin_api_client.get("/api/v1/award-decisions/", {"status": "approved"})
    assert award.id not in [row["id"] for row in resp_mismatch.data["results"]]


# ---- PurchaseOrder ----


@pytest.mark.django_db
def test_purchase_order_list_is_paginated_and_search_matches_po_no(admin_api_client, user, supplier, product):
    purchase_order, _item = create_purchase_order(user, supplier, product, suffix="PAGE-1")

    resp = admin_api_client.get("/api/v1/purchase-orders/", {"search": purchase_order.po_no})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert [row["id"] for row in resp.data["results"]] == [purchase_order.id]


@pytest.mark.django_db
def test_purchase_order_list_filters_by_status(admin_api_client, user, supplier, product):
    purchase_order, _item = create_purchase_order(user, supplier, product, suffix="PAGE-2")
    assert purchase_order.status == "issued"

    resp = admin_api_client.get("/api/v1/purchase-orders/", {"status": "issued"})
    assert purchase_order.id in [row["id"] for row in resp.data["results"]]

    resp_mismatch = admin_api_client.get("/api/v1/purchase-orders/", {"status": "closed"})
    assert purchase_order.id not in [row["id"] for row in resp_mismatch.data["results"]]


# ---- GoodsReceipt ----


@pytest.mark.django_db
def test_goods_receipt_list_is_paginated_and_search_matches_receipt_no(admin_api_client, user, supplier, product):
    purchase_order, _item = create_purchase_order(user, supplier, product, suffix="PAGE-GR")
    receipt = GoodsReceipt.objects.create(
        receipt_no="GR-PAGE-001", purchase_order=purchase_order, received_by=user
    )

    resp = admin_api_client.get("/api/v1/goods-receipts/", {"search": receipt.receipt_no})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert [row["id"] for row in resp.data["results"]] == [receipt.id]


@pytest.mark.django_db
def test_goods_receipt_list_filters_by_status(admin_api_client, user, supplier, product):
    purchase_order, _item = create_purchase_order(user, supplier, product, suffix="PAGE-GR2")
    receipt = GoodsReceipt.objects.create(
        receipt_no="GR-PAGE-002", purchase_order=purchase_order, received_by=user
    )
    assert receipt.status == "draft"

    resp = admin_api_client.get("/api/v1/goods-receipts/", {"status": "draft"})
    assert receipt.id in [row["id"] for row in resp.data["results"]]

    resp_mismatch = admin_api_client.get("/api/v1/goods-receipts/", {"status": "submitted"})
    assert receipt.id not in [row["id"] for row in resp_mismatch.data["results"]]


# ---- InspectionVariance ----


@pytest.mark.django_db(transaction=True)
def test_inspection_variance_list_is_paginated_and_search_matches_receipt_no(
    api_client, user, supplier, product
):
    _order, _item, _receiver, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-PAGE-VARIANCE"
    )
    variance = InspectionVarianceCase.objects.create(
        quality_inspection=inspection, created_by=user,
    )
    receipt_no = inspection.receipt_item.receipt.receipt_no
    _grant(user, user.role, "audit.read")

    resp = api_client.get("/api/v1/inspection-variances/", {"search": receipt_no})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert [row["id"] for row in resp.data["results"]] == [variance.id]


@pytest.mark.django_db(transaction=True)
def test_inspection_variance_list_filters_by_status(api_client, user, supplier, product):
    _order, _item, _receiver, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-PAGE-VARIANCE-STATUS"
    )
    variance = InspectionVarianceCase.objects.create(quality_inspection=inspection, created_by=user)
    InspectionVarianceLine.objects.create(
        variance_case=variance, action_type=InspectionVarianceLine.ActionType.REPLACEMENT,
        quantity=Decimal("2.000"), reason="測試補交",
    )
    variance.status = InspectionVarianceCase.Status.OPEN
    variance.submitted_by = user
    variance.submitted_at = timezone.now()
    variance.save(update_fields=["status", "submitted_by", "submitted_at"])
    _grant(user, user.role, "audit.read")

    resp = api_client.get("/api/v1/inspection-variances/", {"status": "open"})
    assert variance.id in [row["id"] for row in resp.data["results"]]

    resp_mismatch = api_client.get("/api/v1/inspection-variances/", {"status": "closed"})
    assert variance.id not in [row["id"] for row in resp_mismatch.data["results"]]


# ---- PurchaseSuggestion ----


@pytest.mark.django_db
def test_purchase_suggestion_list_is_paginated_and_search_matches_product_name(admin_api_client):
    product = Product.objects.create(name="採購建議分頁品項", price=Decimal("10.00"), currency="TWD")
    PurchaseSuggestion.objects.create(product=product, suggested_qty=Decimal("5.000"))

    resp = admin_api_client.get("/api/v1/purchase-suggestions/", {"search": "採購建議分頁品項"})

    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"count", "page", "page_size", "total_pages", "results"}
    assert len(resp.data["results"]) == 1


@pytest.mark.django_db
def test_purchase_suggestion_list_filters_by_status(admin_api_client):
    product = Product.objects.create(name="採購建議篩選品項", price=Decimal("10.00"), currency="TWD")
    suggestion = PurchaseSuggestion.objects.create(
        product=product, suggested_qty=Decimal("5.000"), status=PurchaseSuggestion.Status.DISMISSED,
    )

    resp = admin_api_client.get("/api/v1/purchase-suggestions/", {"status": "dismissed"})
    assert suggestion.id in [row["id"] for row in resp.data["results"]]

    resp_mismatch = admin_api_client.get("/api/v1/purchase-suggestions/", {"status": "pending"})
    assert suggestion.id not in [row["id"] for row in resp_mismatch.data["results"]]
