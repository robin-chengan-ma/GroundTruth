from unittest.mock import patch

import pytest
import requests

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
    mock_parse.assert_called_once_with("跟測試供應商買 5 張測試產品", user_id=user.id)


@pytest.mark.django_db
@patch("services.inquiry_service.request_candidate_parse")
def test_parse_candidate_returns_editable_unresolved_fields(mock_parse):
    mock_parse.return_value = {
        "purpose": "補貨",
        "suppliers": [{"name": "不存在供應商"}],
        "items": [{"product_name": "不存在品項", "quantity": None}],
    }

    result = parse_purchase_request_candidate("幫我補貨", user_id=1)

    assert result["ready_for_draft"] is False
    assert set(result["missing_fields"]) == {
        "supplier_candidates.0.supplier_id",
        "items.0.product_id",
        "items.0.quantity",
    }
    assert result["supplier_candidates"][0]["supplier_name"] == "不存在供應商"


@patch("services.inquiry_service.request_candidate_parse")
def test_parse_candidate_rejects_malformed_n8n_payload(mock_parse):
    mock_parse.return_value = {"items": "not-an-array", "suppliers": []}

    with pytest.raises(InquiryTriggerError, match="候選資料格式錯誤"):
        parse_purchase_request_candidate("測試", user_id=1)
