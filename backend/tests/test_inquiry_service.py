from unittest.mock import patch

import pytest
import requests

from services.inquiry_service import InquiryTriggerError, InquiryValidationError, trigger_inquiry


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
