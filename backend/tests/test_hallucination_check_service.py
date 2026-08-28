from decimal import Decimal

import pytest

from apps.audit.models import ManualReviewQueue
from apps.procurement.models import Quote
from services import hallucination_check_service as svc


@pytest.fixture
def quote(db, user, supplier, product):
    return Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=20,
        price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        currency="TWD",
        status=Quote.Status.PENDING_VERIFICATION,
    )


def test_check_summary_empty_raises(quote):
    with pytest.raises(svc.HallucinationCheckError):
        svc.check_summary(
            summary_text="",
            quote=quote,
            quantity=20,
            unit_price=Decimal("1500.00"),
            total_amount=Decimal("30000.00"),
            supplier_name="測試供應商",
            product_name="測試產品",
        )


def test_check_summary_invalid_number_raises(quote):
    with pytest.raises(svc.HallucinationCheckError):
        svc.check_summary(
            summary_text="摘要文字",
            quote=quote,
            quantity="not-a-number",
            unit_price=Decimal("1500.00"),
            total_amount=Decimal("30000.00"),
            supplier_name="測試供應商",
            product_name="測試產品",
        )


def test_check_summary_passes_when_all_match(quote):
    summary = "測試供應商採購測試產品，數量20，單價1500，總金額30000元"
    result = svc.check_summary(
        summary_text=summary,
        quote=quote,
        quantity=20,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        supplier_name="測試供應商",
        product_name="測試產品",
    )
    assert result == {"passed": True}
    assert ManualReviewQueue.objects.count() == 0


def test_check_summary_passes_with_comma_formatted_numbers(quote):
    summary = "測試供應商採購測試產品，數量20，單價1,500，總金額30,000元"
    result = svc.check_summary(
        summary_text=summary,
        quote=quote,
        quantity=20,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        supplier_name="測試供應商",
        product_name="測試產品",
    )
    assert result == {"passed": True}


def test_check_summary_passes_with_company_suffix_variation(quote):
    # 真實供應商全名帶「股份有限公司」，摘要文字只寫核心字串也應通過。
    summary = "優品採購測試產品，數量20，單價1500，總金額30000元"
    result = svc.check_summary(
        summary_text=summary,
        quote=quote,
        quantity=20,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        supplier_name="優品股份有限公司",
        product_name="測試產品",
    )
    assert result == {"passed": True}


def test_check_summary_fails_missing_number_creates_review(quote):
    summary = "測試供應商採購測試產品，數量20，總金額30000元"  # 少了單價 1500
    result = svc.check_summary(
        summary_text=summary,
        quote=quote,
        quantity=20,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        supplier_name="測試供應商",
        product_name="測試產品",
    )
    assert result["passed"] is False
    assert any("缺少真實數字" in reason for reason in result["reasons"])

    review = ManualReviewQueue.objects.get(id=result["review_id"])
    assert review.review_type == ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH
    assert review.quote_id == quote.id
    assert review.ai_generated_text == summary
    assert "1500" in review.expected_value

    quote.refresh_from_db()
    assert quote.status == Quote.Status.PENDING_REVIEW


def test_check_summary_fails_extra_unexplained_number(quote):
    summary = "測試供應商採購測試產品，數量20，單價1500，總金額30000元，另加運費999元"
    result = svc.check_summary(
        summary_text=summary,
        quote=quote,
        quantity=20,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        supplier_name="測試供應商",
        product_name="測試產品",
    )
    assert result["passed"] is False
    assert any("多餘數字" in reason for reason in result["reasons"])


def test_check_summary_fails_supplier_name_mismatch(quote):
    summary = "某間廠商採購測試產品，數量20，單價1500，總金額30000元"
    result = svc.check_summary(
        summary_text=summary,
        quote=quote,
        quantity=20,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        supplier_name="測試供應商",
        product_name="測試產品",
    )
    assert result["passed"] is False
    assert any("供應商名稱" in reason for reason in result["reasons"])


def test_check_summary_fails_product_name_mismatch(quote):
    summary = "測試供應商採購某個東西，數量20，單價1500，總金額30000元"
    result = svc.check_summary(
        summary_text=summary,
        quote=quote,
        quantity=20,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        supplier_name="測試供應商",
        product_name="測試產品",
    )
    assert result["passed"] is False
    assert any("產品名稱" in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    "name,expected_core",
    [
        ("優品股份有限公司", "優品"),
        ("優品有限公司", "優品"),
        ("優品企業社", "優品"),
        ("優品工作室", "優品"),
        ("優品商行", "優品"),
        ("優品", "優品"),
        ("", ""),
        (None, ""),
    ],
)
def test_strip_company_suffix(name, expected_core):
    assert svc._strip_company_suffix(name) == expected_core
