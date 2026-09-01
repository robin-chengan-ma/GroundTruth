import pytest

from services.authentication_service import issue_token_pair


def bearer(user):
    access, _, _ = issue_token_pair(user)
    return f"Bearer {access}"


@pytest.mark.django_db
def test_inquiry_trigger_endpoint_requires_login(api_client):
    resp = api_client.post("/api/v1/inquiries/trigger/", {"raw_text": "test"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_quote_calculate_requires_internal_api_key(api_client, product, supplier, user, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post(
        "/api/v1/quotes/calculate/",
        {"user_id": user.id, "product_id": product.id, "supplier_id": supplier.id, "quantity": 5},
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_quote_calculate_wrong_key_rejected(api_client, product, supplier, user, settings):
    # 帶錯的 key：authenticate() 主動拋 AuthenticationFailed → 401
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post(
        "/api/v1/quotes/calculate/",
        {"user_id": user.id, "product_id": product.id, "supplier_id": supplier.id, "quantity": 5},
        HTTP_X_INTERNAL_API_KEY="wrong-key",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_supplier_search_by_name(api_client, supplier, user):
    resp = api_client.get(f"/api/v1/suppliers/?search={supplier.name}", HTTP_AUTHORIZATION=bearer(user))
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == supplier.id


@pytest.mark.django_db
def test_supplier_search_allows_internal_api_key_read_only(api_client, supplier, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"

    search = api_client.get(
        f"/api/v1/suppliers/?search={supplier.name}",
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )
    create = api_client.post(
        "/api/v1/suppliers/",
        {"name": "n8n 不得建立", "tier": "normal"},
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )

    assert search.status_code == 200
    assert search.data["results"][0]["id"] == supplier.id
    assert create.status_code == 403


@pytest.mark.django_db
def test_product_search_by_name(api_client, product, user):
    resp = api_client.get(f"/api/v1/products/?search={product.name}", HTTP_AUTHORIZATION=bearer(user))
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == product.id


@pytest.mark.django_db
def test_product_search_allows_internal_api_key_read_only(api_client, product, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"

    search = api_client.get(
        f"/api/v1/products/?search={product.name}",
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )
    update = api_client.patch(
        f"/api/v1/products/{product.id}/",
        {"price": "1.00"},
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )

    assert search.status_code == 200
    assert search.data["results"][0]["id"] == product.id
    assert update.status_code == 403
