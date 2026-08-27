from unittest.mock import patch

import pytest
import requests

from services.inquiry_service import InquiryTriggerError, trigger_inquiry


def test_trigger_inquiry_empty_text_raises():
    with pytest.raises(InquiryTriggerError):
        trigger_inquiry("")
    with pytest.raises(InquiryTriggerError):
        trigger_inquiry("   ")


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
