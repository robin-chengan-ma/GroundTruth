from unittest.mock import patch

import pytest
import requests

from apps.crm.models import Supplier
from services.inquiry_service import (
    InquiryTriggerError,
    InquiryValidationError,
    parse_purchase_request_candidate,
    trigger_inquiry,
)


def test_trigger_inquiry_empty_text_raises():
    with pytest.raises(InquiryValidationError):
        trigger_inquiry("")
    with pytest.raises(InquiryValidationError):
        trigger_inquiry("   ")


@pytest.mark.parametrize(
    "raw_text",
    [
        "跟優品科技買一些 A產品-辦公椅",
        "跟優品科技買幾個 A產品-辦公椅",
        "跟優品科技買 0 個 A產品-辦公椅",
    ],
)
def test_trigger_inquiry_requires_explicit_positive_quantity(raw_text):
    with pytest.raises(InquiryValidationError, match="格式無法解析"):
        trigger_inquiry(raw_text)


@pytest.mark.parametrize(
    "raw_text",
    [
        "跟優品科技採購 6 個 A產品-辦公椅",
        "跟優品科技採購數量：20 A產品-辦公椅",
        "跟優品科技採購 ６ 件 A產品-辦公椅",
        "跟優品科技買五個 A產品-辦公椅",
        "跟優品科技買十五件 A產品-辦公椅",
        "跟優品科技買兩百個 A產品-辦公椅",
    ],
)
@patch("services.inquiry_service.requests.post")
def test_trigger_inquiry_accepts_supported_quantity_formats(mock_post, raw_text):
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {"status": "ok"}

    assert trigger_inquiry(raw_text) == {"status": "ok"}


@patch("services.inquiry_service.requests.post")
def test_trigger_inquiry_success(mock_post):
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.return_value = {"status": "ok", "quote": {}}

    result = trigger_inquiry("幫我訂50個A產品，跟X供應商拿貨")

    assert result == {"status": "ok", "quote": {}}
    mock_post.assert_called_once()


@patch("services.inquiry_service.requests.post")
def test_trigger_inquiry_connection_error_wrapped(mock_post):
    mock_post.side_effect = requests.ConnectionError("boom")

    with pytest.raises(InquiryTriggerError):
        trigger_inquiry("幫我訂50個A產品")


@patch("services.inquiry_service.requests.post")
def test_trigger_inquiry_http_error_wrapped(mock_post):
    mock_post.return_value.raise_for_status.side_effect = requests.HTTPError("502")

    with pytest.raises(InquiryTriggerError):
        trigger_inquiry("幫我訂50個A產品")


@patch("services.inquiry_service.requests.post")
def test_trigger_inquiry_non_json_response_wrapped(mock_post):
    mock_post.return_value.raise_for_status.return_value = None
    mock_post.return_value.json.side_effect = requests.JSONDecodeError("invalid", "", 0)

    with pytest.raises(InquiryTriggerError, match="詢價流程觸發失敗"):
        trigger_inquiry("幫我訂50個A產品")


@pytest.mark.django_db
@patch("services.inquiry_service.request_candidate_parse")
def test_parse_candidate_resolves_exact_master_data_without_writing(
    mock_parse, user, product, supplier,
):
    mock_parse.return_value = {
        "purpose": "辦公設備汰換",
        "currency": "twd",
        "needed_by": None,
        "suppliers": [{"name": supplier.name}],
        "items": [{
            "product_name": product.name,
            "quantity": "5",
            "unit_of_measure": "EA",
            "specifications": {"material": "網布"},
        }],
        "assistant_message": "已整理需求",
    }

    result = parse_purchase_request_candidate("跟測試供應商買 5 張測試產品", user_id=user.id)

    assert result["ready_for_draft"] is True
    assert result["supplier_candidates"] == [{"supplier_id": supplier.id, "supplier_name": supplier.name}]
    assert result["items"][0]["product_id"] == product.id
    assert result["items"][0]["quantity"] == "5"
    sent_text = mock_parse.call_args.args[0]
    assert supplier.name not in sent_text
    assert "SUP_001" in sent_text
    assert mock_parse.call_args.kwargs == {"user_id": user.id}


@pytest.mark.django_db
@patch("services.inquiry_service.request_candidate_parse")
def test_parse_candidate_masks_multiple_suppliers_and_amount_before_n8n(
    mock_parse, user, product,
):
    supplier_a = Supplier.objects.create(name="甲方供應", tier="normal")
    supplier_b = Supplier.objects.create(name="乙方物產", tier="normal")
    mock_parse.return_value = {
        "purpose": "向 SUP_001 與 SUP_002 詢價，預算 AMOUNT_001",
        "suppliers": [{"name": "SUP_001"}, {"name": "SUP_002"}],
        "items": [{"product_name": product.name, "quantity": 5}],
        "assistant_message": "已遮罩 SUP_001、SUP_002 與 AMOUNT_001",
    }

    result = parse_purchase_request_candidate(
        "向甲方供應與乙方物產詢價，預算30000元，採購 5 張測試產品",
        user_id=user.id,
    )

    sent_text = mock_parse.call_args.args[0]
    assert "甲方供應" not in sent_text
    assert "乙方物產" not in sent_text
    assert "30000元" not in sent_text
    assert {row["supplier_id"] for row in result["supplier_candidates"]} == {
        supplier_a.id,
        supplier_b.id,
    }
    assert result["purpose"] == "向 甲方供應 與 乙方物產 詢價，預算 30000元"
    assert "甲方供應" in result["assistant_message"]


@pytest.mark.django_db
@patch("services.inquiry_service.request_candidate_parse")
def test_parse_candidate_returns_editable_unresolved_product_fields(mock_parse, supplier):
    mock_parse.return_value = {
        "purpose": "補貨",
        "suppliers": [{"name": "SUP_001"}],
        "items": [{"product_name": "不存在品項", "quantity": None}],
    }

    result = parse_purchase_request_candidate(f"跟{supplier.name}補貨", user_id=1)

    assert result["ready_for_draft"] is False
    assert set(result["missing_fields"]) == {
        "items.0.product_id",
        "items.0.quantity",
    }
    assert result["supplier_candidates"][0] == {
        "supplier_id": supplier.id,
        "supplier_name": supplier.name,
    }


@pytest.mark.django_db
@patch("services.inquiry_service.request_candidate_parse")
def test_parse_candidate_unknown_supplier_never_calls_n8n(mock_parse):
    with pytest.raises(InquiryValidationError, match="找不到可確認的供應商"):
        parse_purchase_request_candidate("跟完全未知公司採購產品", user_id=1)

    mock_parse.assert_not_called()


@pytest.mark.django_db
@patch("services.inquiry_service.request_candidate_parse")
def test_parse_candidate_rejects_malformed_n8n_payload(mock_parse, supplier):
    mock_parse.return_value = {"items": "not-an-array", "suppliers": []}

    with pytest.raises(InquiryTriggerError, match="候選資料格式錯誤"):
        parse_purchase_request_candidate(f"跟{supplier.name}測試", user_id=1)
