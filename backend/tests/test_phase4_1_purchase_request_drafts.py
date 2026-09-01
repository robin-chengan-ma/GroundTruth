from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import Permission, RolePermission, UserRole
from apps.crm.models import Supplier
from apps.erp.models import Product
from apps.procurement.models import (
    PurchaseRequest,
    PurchaseRequestItem,
    Quote,
    Rfq,
    RfqSupplier,
    SupplierPriceVersion,
    SupplierProduct,
)


def _grant_draft_permissions(user, role):
    UserRole.objects.create(user=user, role=role)
    for code in (
        "purchase_request.create",
        "purchase_request.read_own",
        "purchase_request.edit_draft",
        "purchase_request.submit",
    ):
        permission = Permission.objects.create(code=code, name=code)
        RolePermission.objects.create(role=role, permission=permission)


def _product(name, price):
    return Product.objects.create(name=name, price=price, currency="TWD", unit_of_measure="EA")


def _priced_supplier_product(supplier, product, user, unit_price):
    supplier_product = SupplierProduct.objects.create(supplier=supplier, product=product)
    SupplierPriceVersion.objects.create(
        supplier_product=supplier_product,
        unit_price=unit_price,
        currency="TWD",
        minimum_quantity=Decimal("1.000"),
        valid_from=timezone.now() - timedelta(days=1),
        created_by=user,
    )


@pytest.mark.django_db
def test_create_multi_item_multi_supplier_draft(api_client, user, role_employee):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)
    chair = _product("人體工學椅", Decimal("1500.00"))
    desk = _product("升降桌", Decimal("5000.00"))
    first_supplier = Supplier.objects.create(name="優品科技")
    second_supplier = Supplier.objects.create(name="大和物產")

    response = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {
            "purpose": "辦公設備汰換",
            "currency": "TWD",
            "supplier_ids": [first_supplier.id, second_supplier.id],
            "items": [
                {"product_id": chair.id, "quantity": "5", "specifications": {"material": "網布"}},
                {"product_id": desk.id, "quantity": "3"},
            ],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] == "draft"
    assert response.data["version"] == 1
    assert len(response.data["items"]) == 2
    assert {row["supplier_id"] for row in response.data["candidate_suppliers"]} == {
        first_supplier.id,
        second_supplier.id,
    }
    request = PurchaseRequest.objects.get(pk=response.data["id"])
    assert request.items.count() == 2
    assert request.rfqs.get().status == Rfq.Status.DRAFT


@pytest.mark.django_db
def test_create_draft_reports_missing_fields_without_writing(api_client, user, role_employee, product):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)

    response = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {"purpose": "補貨", "supplier_ids": [], "items": [{"product_id": product.id}]},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "clarification_required"
    assert set(response.data["missing_fields"]) == {"supplier_ids", "items.0.quantity"}
    assert PurchaseRequest.objects.count() == 0


@pytest.mark.django_db
def test_update_draft_rejects_stale_version(api_client, user, role_employee, product, supplier):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)
    create = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {
            "purpose": "補貨",
            "supplier_ids": [supplier.id],
            "items": [{"product_id": product.id, "quantity": "2"}],
        },
        format="json",
    )

    first = api_client.patch(
        f"/api/v1/purchase-request-drafts/{create.data['id']}/",
        {"version": 1, "purpose": "更新後補貨"},
        format="json",
    )
    stale = api_client.patch(
        f"/api/v1/purchase-request-drafts/{create.data['id']}/",
        {"version": 1, "purpose": "過期頁面覆寫"},
        format="json",
    )

    assert first.status_code == 200
    assert first.data["version"] == 2
    assert stale.status_code == 409
    assert stale.data["code"] == "version_conflict"


@pytest.mark.django_db
def test_preview_returns_human_readable_rows_without_formal_quote(
    api_client, user, role_employee, product, supplier,
):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)
    _priced_supplier_product(supplier, product, user, Decimal("125.00"))
    create = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {
            "purpose": "補貨",
            "supplier_ids": [supplier.id],
            "items": [{"product_id": product.id, "quantity": "2"}],
        },
        format="json",
    )

    response = api_client.post(
        f"/api/v1/purchase-request-drafts/{create.data['id']}/preview/",
        {"version": 1},
        format="json",
    )

    assert response.status_code == 200
    row = response.data["suppliers"][0]["items"][0]
    assert row["product_name"] == product.name
    assert row["unit_price"] == "125.00"
    assert row["total_amount"] == "250.00"
    assert row["price_comparison"]["label"] == "無歷史資料"
    assert Quote.objects.count() == 0
    assert PurchaseRequest.objects.get(pk=create.data["id"]).status == "draft"


@pytest.mark.django_db
def test_submit_is_idempotent_and_locks_draft(api_client, user, role_employee, product, supplier):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)
    _priced_supplier_product(supplier, product, user, Decimal("100.00"))
    create = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {
            "purpose": "補貨",
            "supplier_ids": [supplier.id],
            "items": [{"product_id": product.id, "quantity": "2"}],
        },
        format="json",
    )
    payload = {"version": 1, "idempotency_key": "draft-submit-001"}

    first = api_client.post(
        f"/api/v1/purchase-request-drafts/{create.data['id']}/submit/", payload, format="json",
    )
    repeated = api_client.post(
        f"/api/v1/purchase-request-drafts/{create.data['id']}/submit/", payload, format="json",
    )

    assert first.status_code == 200
    assert first.data["status"] == "submitted"
    assert repeated.status_code == 200
    assert repeated.data == first.data
    assert PurchaseRequest.objects.filter(idempotency_key="draft-submit-001").count() == 1


@pytest.mark.django_db
def test_other_user_cannot_read_or_edit_draft(api_client, user, role_employee, product, supplier):
    _grant_draft_permissions(user, role_employee)
    request = PurchaseRequest.objects.create(
        request_no="PR-PRIVATE",
        requester=user,
        purpose="私人草稿",
    )
    other_user = type(user).objects.create(
        name="Other User", email="other@groundtruth.demo", password="hashed", role=role_employee,
    )
    UserRole.objects.create(user=other_user, role=role_employee)
    api_client.force_authenticate(user=other_user)

    response = api_client.get(f"/api/v1/purchase-request-drafts/{request.id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_list_and_delete_only_operate_on_own_drafts(api_client, user, role_employee, product, supplier):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)
    created = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {
            "purpose": "可刪除草稿",
            "supplier_ids": [supplier.id],
            "items": [{"product_id": product.id, "quantity": "1"}],
        },
        format="json",
    )

    listed = api_client.get("/api/v1/purchase-request-drafts/")
    deleted = api_client.delete(f"/api/v1/purchase-request-drafts/{created.data['id']}/")

    assert listed.status_code == 200
    assert [row["id"] for row in listed.data] == [created.data["id"]]
    assert deleted.status_code == 204
    assert not PurchaseRequest.objects.filter(pk=created.data["id"]).exists()


@pytest.mark.django_db
def test_list_owned_purchase_requests_includes_submitted_and_orders_newest_first(
    api_client, user, role_employee, product, supplier,
):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)
    older = PurchaseRequest.objects.create(
        request_no="PR-OLDER", requester=user, purpose="舊需求",
        status=PurchaseRequest.Status.SUBMITTED,
    )
    newer = PurchaseRequest.objects.create(
        request_no="PR-NEWER", requester=user, purpose="新需求",
        status=PurchaseRequest.Status.DRAFT,
    )
    other_user = type(user).objects.create(
        name="Other User", email="other-list@groundtruth.demo", password="hashed", role=role_employee,
    )
    PurchaseRequest.objects.create(
        request_no="PR-OTHER", requester=other_user, purpose="別人的需求",
        status=PurchaseRequest.Status.SUBMITTED,
    )

    response = api_client.get("/api/v1/purchase-requests/?page=1&page_size=10")

    assert response.status_code == 200
    assert response.data["count"] == 2
    assert response.data["page"] == 1
    assert response.data["page_size"] == 10
    assert response.data["total_pages"] == 1
    assert [row["id"] for row in response.data["results"]] == [newer.id, older.id]
    assert response.data["results"][0]["request_no"] == "PR-NEWER"
    assert response.data["results"][0]["requester_name"] == user.name
    assert "created_at" in response.data["results"][0]


@pytest.mark.django_db
def test_purchase_request_list_validates_page_size(api_client, user, role_employee):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1/purchase-requests/?page_size=25")

    assert response.status_code == 400
    assert response.data["code"] == "invalid_pagination"


@pytest.mark.django_db
def test_purchase_request_detail_is_read_only_and_returns_snapshot(
    api_client, user, role_employee, product, supplier,
):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)
    purchase_request = PurchaseRequest.objects.create(
        request_no="PR-DETAIL", requester=user, purpose="辦公設備汰換",
        needed_by="2026-09-30", status=PurchaseRequest.Status.SUBMITTED,
    )
    PurchaseRequestItem.objects.create(
        request=purchase_request,
        line_no=1,
        product=product,
        description_snapshot=product.name,
        specification_snapshot={"material": "網布", "feature": "有頭枕"},
        quantity="5",
        unit_of_measure="EA",
    )
    rfq = Rfq.objects.create(rfq_no="RFQ-DETAIL", request=purchase_request)
    RfqSupplier.objects.create(rfq=rfq, supplier=supplier, invited_at=timezone.now())

    response = api_client.get(f"/api/v1/purchase-requests/{purchase_request.id}/")
    write_response = api_client.patch(
        f"/api/v1/purchase-requests/{purchase_request.id}/",
        {"purpose": "不得修改"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["request_no"] == "PR-DETAIL"
    assert response.data["requester_name"] == user.name
    assert response.data["candidate_suppliers"] == [
        {"supplier_id": supplier.id, "supplier_name": supplier.name},
    ]
    assert response.data["items"][0]["specifications"] == {
        "material": "網布",
        "feature": "有頭枕",
    }
    assert write_response.status_code == 405


@pytest.mark.django_db
def test_purchase_request_detail_hides_other_users_document(
    api_client, user, role_employee,
):
    _grant_draft_permissions(user, role_employee)
    other_user = type(user).objects.create(
        name="Other User", email="other-detail@groundtruth.demo", password="hashed", role=role_employee,
    )
    other_request = PurchaseRequest.objects.create(
        request_no="PR-OTHER-DETAIL", requester=other_user, purpose="別人的需求",
    )
    api_client.force_authenticate(user=user)

    response = api_client.get(f"/api/v1/purchase-requests/{other_request.id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_create_draft_requires_rbac_permission(api_client, user, product, supplier):
    api_client.force_authenticate(user=user)

    response = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {
            "purpose": "無權限",
            "supplier_ids": [supplier.id],
            "items": [{"product_id": product.id, "quantity": "1"}],
        },
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


@pytest.mark.django_db
@pytest.mark.parametrize("quantity", ["0", "-1", "1.0001", "NaN"])
def test_create_draft_rejects_invalid_quantities(
    api_client, user, role_employee, product, supplier, quantity,
):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)

    response = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {
            "purpose": "錯誤數量",
            "supplier_ids": [supplier.id],
            "items": [{"product_id": product.id, "quantity": quantity}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert PurchaseRequest.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("items", "not-an-array"),
        ("supplier_ids", "not-an-array"),
        ("supplier_ids", ["1"]),
        ("currency", "TAIWAN"),
        ("needed_by", "2026-02-30"),
    ],
)
def test_create_draft_rejects_malformed_structured_fields(
    api_client, user, role_employee, product, supplier, field, value,
):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)
    payload = {
        "purpose": "錯誤格式",
        "supplier_ids": [supplier.id],
        "items": [{"product_id": product.id, "quantity": "1"}],
    }
    payload[field] = value

    response = api_client.post("/api/v1/purchase-request-drafts/", payload, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "invalid_draft"
    assert PurchaseRequest.objects.count() == 0


@pytest.mark.django_db
def test_create_draft_does_not_trust_client_source(api_client, user, role_employee, product, supplier):
    _grant_draft_permissions(user, role_employee)
    api_client.force_authenticate(user=user)

    response = api_client.post(
        "/api/v1/purchase-request-drafts/",
        {
            "purpose": "來源防偽",
            "source": "legacy",
            "supplier_ids": [supplier.id],
            "items": [{"product_id": product.id, "quantity": "1"}],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["source"] == "manual"
