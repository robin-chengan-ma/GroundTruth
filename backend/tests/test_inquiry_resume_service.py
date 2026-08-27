from unittest.mock import Mock, patch

import pytest
import requests

from services.inquiry_resume_service import InquiryResumeError, trigger_resume


@patch("services.inquiry_resume_service.requests.post")
def test_trigger_resume_success(mock_post, settings):
    settings.N8N_RESUME_WEBHOOK_URL = "http://n8n.test/webhook/inquiry/resume"
    settings.INTERNAL_API_KEY = "test-key"
    mock_post.return_value = Mock(status_code=200, raise_for_status=lambda: None)

    trigger_resume(review_id=1, raw_input_text="跟優品科採購A產品", requester_id=5, supplier_id=2)

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {
        "review_id": 1, "raw_input_text": "跟優品科採購A產品", "user_id": 5, "supplier_id": 2,
    }
    assert kwargs["headers"]["X-Internal-Api-Key"] == "test-key"


@patch("services.inquiry_resume_service.requests.post")
def test_trigger_resume_connection_failure_raises(mock_post, settings):
    settings.N8N_RESUME_WEBHOOK_URL = "http://n8n.test/webhook/inquiry/resume"
    mock_post.side_effect = requests.ConnectionError("boom")

    with pytest.raises(InquiryResumeError):
        trigger_resume(review_id=1, raw_input_text="x", requester_id=5, supplier_id=2)


@patch("services.inquiry_resume_service.requests.post")
def test_trigger_resume_upstream_error_raises(mock_post, settings):
    settings.N8N_RESUME_WEBHOOK_URL = "http://n8n.test/webhook/inquiry/resume"
    response = Mock(status_code=500)
    response.raise_for_status.side_effect = requests.HTTPError("500")
    mock_post.return_value = response

    with pytest.raises(InquiryResumeError):
        trigger_resume(review_id=1, raw_input_text="x", requester_id=5, supplier_id=2)
