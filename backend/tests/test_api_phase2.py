from unittest.mock import patch

import pytest


@pytest.mark.django_db
@patch("api.procurement.views.trigger_inquiry")
def test_inquiry_trigger_endpoint_success(mock_trigger, api_client):
    mock_trigger.return_value = {"status": "ok"}
    resp = api_client.post("/api/v1/inquiries/trigger/", {"raw_text": "幫我訂50個A產品，跟X供應商拿貨"})
    assert resp.status_code == 200
    assert resp.data == {"status": "ok"}


@pytest.mark.django_db
@patch("api.procurement.views.trigger_inquiry")
def test_inquiry_trigger_endpoint_upstream_failure(mock_trigger, api_client):
    from services.inquiry_service import InquiryTriggerError

    mock_trigger.side_effect = InquiryTriggerError("詢價流程觸發失敗，請稍後再試")
    resp = api_client.post("/api/v1/inquiries/trigger/", {"raw_text": "test"})
    assert resp.status_code == 502


@pytest.mark.django_db
def test_quote_calculate_requires_internal_api_key(api_client, product, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post("/api/v1/quotes/calculate/", {"product_id": product.id, "quantity": 5})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_quote_calculate_with_valid_key(api_client, product, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post(
        "/api/v1/quotes/calculate/",
        {"product_id": product.id, "quantity": 5},
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )
    assert resp.status_code == 200
    assert resp.data["total_amount"] == product.price * 5


@pytest.mark.django_db
def test_quote_calculate_wrong_key_rejected(api_client, product, settings):
    # 帶錯的 key：authenticate() 主動拋 AuthenticationFailed → 401
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post(
        "/api/v1/quotes/calculate/",
        {"product_id": product.id, "quantity": 5},
        HTTP_X_INTERNAL_API_KEY="wrong-key",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_supplier_search_by_name(api_client, supplier):
    resp = api_client.get(f"/api/v1/suppliers/?search={supplier.name}")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == supplier.id


@pytest.mark.django_db
def test_product_search_by_name(api_client, product):
    resp = api_client.get(f"/api/v1/products/?search={product.name}")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == product.id


@pytest.mark.django_db
def test_quote_calculate_invalid_quantity(api_client, product, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post(
        "/api/v1/quotes/calculate/",
        {"product_id": product.id, "quantity": "abc"},
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )
    assert resp.status_code == 400
