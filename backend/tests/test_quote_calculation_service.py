from decimal import Decimal

import pytest

from apps.procurement.models import Quote
from services.quote_calculation_service import (
    PRICE_DEVIATION_THRESHOLD_PCT,
    QuoteCalculationError,
    calculate_quote,
)


@pytest.mark.django_db
def test_calculate_quote_basic(product):
    result = calculate_quote(product_id=product.id, quantity=3)
    assert result["unit_price"] == product.price
    assert result["total_amount"] == product.price * 3
    assert result["currency"] == product.currency
    assert result["price_deviation_pct"] is None
    assert result["price_deviation_flag"] is False


@pytest.mark.django_db
def test_calculate_quote_invalid_quantity(product):
    with pytest.raises(QuoteCalculationError):
        calculate_quote(product_id=product.id, quantity=0)
    with pytest.raises(QuoteCalculationError):
        calculate_quote(product_id=product.id, quantity=-5)
    with pytest.raises(QuoteCalculationError):
        calculate_quote(product_id=product.id, quantity="abc")


@pytest.mark.django_db
def test_calculate_quote_product_not_found():
    with pytest.raises(QuoteCalculationError):
        calculate_quote(product_id=999999, quantity=1)


@pytest.mark.django_db
def test_calculate_quote_no_history_returns_none_deviation(product, supplier):
    result = calculate_quote(product_id=product.id, quantity=2, supplier_id=supplier.id)
    assert result["price_deviation_pct"] is None
    assert result["price_deviation_flag"] is False


@pytest.mark.django_db
def test_calculate_quote_deviation_within_threshold(user, supplier, product):
    Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=10, price=product.price, total_amount=product.price * 10,
        currency=product.currency, status=Quote.Status.APPROVED,
    )
    result = calculate_quote(product_id=product.id, quantity=5, supplier_id=supplier.id)
    assert result["price_deviation_pct"] == Decimal("0.00")
    assert result["price_deviation_flag"] is False


@pytest.mark.django_db
def test_calculate_quote_deviation_flagged_when_over_threshold(user, supplier, product):
    Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=10, price=Decimal("100.00"), total_amount=Decimal("1000.00"),
        currency=product.currency, status=Quote.Status.APPROVED,
    )
    product.price = Decimal("200.00")  # 偏離歷史均價 100%，遠超過門檻
    product.save()

    result = calculate_quote(product_id=product.id, quantity=1, supplier_id=supplier.id)
    assert result["price_deviation_pct"] == Decimal("100.00")
    assert result["price_deviation_flag"] is True
    assert abs(result["price_deviation_pct"]) > PRICE_DEVIATION_THRESHOLD_PCT


@pytest.mark.django_db
def test_calculate_quote_ignores_non_approved_history(user, supplier, product):
    Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=1, price=Decimal("999.00"), total_amount=Decimal("999.00"),
        currency=product.currency, status=Quote.Status.PENDING_VERIFICATION,
    )
    result = calculate_quote(product_id=product.id, quantity=1, supplier_id=supplier.id)
    assert result["price_deviation_pct"] is None
