"""管理型資源 CRUD 與正式流程資源唯讀限制驗收。"""
import pytest


@pytest.mark.django_db
def test_role_crud(admin_api_client):
    resp = admin_api_client.post("/api/v1/roles/", {"role": "approver_5k", "approval_amount_limit": "5000.00"})
    assert resp.status_code == 201
    role_id = resp.data["id"]

    resp = admin_api_client.get("/api/v1/roles/")
    assert resp.status_code == 200
    assert resp.data["count"] >= 1

    resp = admin_api_client.get(f"/api/v1/roles/{role_id}/")
    assert resp.status_code == 200
    assert resp.data["role"] == "approver_5k"

    resp = admin_api_client.patch(f"/api/v1/roles/{role_id}/", {"approval_amount_limit": "6000.00"})
    assert resp.status_code == 200
    assert resp.data["approval_amount_limit"] == "6000.00"

    resp = admin_api_client.delete(f"/api/v1/roles/{role_id}/")
    assert resp.status_code == 204

    resp = admin_api_client.get(f"/api/v1/roles/{role_id}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_supplier_crud(admin_api_client):
    resp = admin_api_client.post("/api/v1/suppliers/", {"name": "API測試供應商", "tier": "priority"})
    assert resp.status_code == 201
    supplier_id = resp.data["id"]

    resp = admin_api_client.put(
        f"/api/v1/suppliers/{supplier_id}/", {"name": "API測試供應商-改名", "tier": "watch"}
    )
    assert resp.status_code == 200
    assert resp.data["tier"] == "watch"

    resp = admin_api_client.delete(f"/api/v1/suppliers/{supplier_id}/")
    assert resp.status_code == 204


@pytest.mark.django_db
def test_user_crud(admin_api_client, role_employee):
    resp = admin_api_client.post(
        "/api/v1/users/",
        {"name": "API User", "email": "api.user@groundtruth.demo", "password": "pw", "role": role_employee.id},
    )
    assert resp.status_code == 201
    assert "password" not in resp.data  # write_only 不應回傳
    user_id = resp.data["id"]

    resp = admin_api_client.get(f"/api/v1/users/{user_id}/")
    assert resp.status_code == 200
    assert resp.data["email"] == "api.user@groundtruth.demo"


@pytest.mark.django_db
def test_product_and_inventory_crud(admin_api_client):
    resp = admin_api_client.post("/api/v1/products/", {"name": "API產品", "price": "999.00", "currency": "TWD"})
    assert resp.status_code == 201
    product_id = resp.data["id"]

    resp = admin_api_client.post("/api/v1/inventory/", {"product": product_id, "stock_qty": 3, "threshold": 10})
    assert resp.status_code == 201
    inv_id = resp.data["id"]

    resp = admin_api_client.get(f"/api/v1/inventory/{inv_id}/")
    assert resp.status_code == 200
    assert resp.data["stock_qty"] == 3


@pytest.mark.django_db
def test_quote_cannot_bypass_workflow_crud(admin_api_client, user, supplier, product):
    resp = admin_api_client.post(
        "/api/v1/quotes/",
        {
            "user": user.id, "supplier": supplier.id, "product": product.id,
            "quantity": 10, "price": "100.00", "total_amount": "1000.00", "currency": "TWD",
        },
    )
    assert resp.status_code == 405


@pytest.mark.django_db
def test_manual_review_queue_and_audit_log_are_not_general_crud(admin_api_client):
    resp = admin_api_client.post(
        "/api/v1/manual-review-queue/",
        {"review_type": "supplier_fuzzy_match", "status": "unclaimed"},
    )
    assert resp.status_code == 405

    resp = admin_api_client.post(
        "/api/v1/audit-logs/",
        {"action_type": "llm_parse", "masked_payload": "SUP_001 x 10"},
    )
    assert resp.status_code == 405
