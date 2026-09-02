from unittest.mock import patch

import pytest

from apps.core.models import Permission, RolePermission, UserRole
from apps.procurement.models import PurchaseRequest
from services.inquiry_resume_service import (
    RESUME_ERROR_INVALID_INPUT,
    RESUME_ERROR_MISSING_FIELDS,
    RESUME_ERROR_PARSE_FAILED,
    RESUME_ERROR_PERMISSION_DENIED,
    RESUME_ERROR_UNMASKABLE_SUPPLIER,
    InquiryResumeError,
    trigger_resume,
)
from services.inquiry_service import InquiryTriggerError, InquiryUnmaskableSupplierError, InquiryValidationError
from services.purchase_request_draft_service import DraftError


def _grant_create_permission(user, role):
    UserRole.objects.get_or_create(user=user, role=role)
    permission, _ = Permission.objects.get_or_create(
        code="purchase_request.create", defaults={"name": "建立採購需求"},
    )
    RolePermission.objects.get_or_create(role=role, permission=permission)


@pytest.mark.django_db
@patch("services.inquiry_resume_service.resolve_candidate_after_manual_review")
def test_trigger_resume_creates_draft_when_ready_for_draft(mock_resolve, user, role_employee, supplier, product):
    _grant_create_permission(user, role_employee)
    mock_resolve.return_value = {
        "purpose": "辦公設備汰換",
        "needed_by": None,
        "currency": "TWD",
        "supplier_id": supplier.id,
        "items": [{
            "product_id": product.id,
            "product_name": product.name,
            "quantity": "5",
            "unit_of_measure": "EA",
            "specifications": {},
        }],
        "missing_fields": [],
        "ready_for_draft": True,
    }

    draft, error_code = trigger_resume(
        review_id=1, raw_input_text="跟優品科採購A產品", requester_id=user.id, supplier_id=supplier.id,
    )

    assert error_code is None
    assert draft is not None
    assert draft.requester_id == user.id
    assert draft.source == "manual_review_resume"
    assert list(draft.items.values_list("product_id", flat=True)) == [product.id]
    assert list(draft.rfqs.get().invited_suppliers.values_list("supplier_id", flat=True)) == [supplier.id]
    assert PurchaseRequest.objects.filter(pk=draft.pk).exists()
    mock_resolve.assert_called_once_with("跟優品科採購A產品", supplier=supplier, requester_id=user.id)


@pytest.mark.django_db
@patch("services.inquiry_resume_service.resolve_candidate_after_manual_review")
def test_trigger_resume_missing_fields_returns_missing_fields_error_code(mock_resolve, user, supplier):
    mock_resolve.return_value = {
        "purpose": "補貨",
        "needed_by": None,
        "currency": "TWD",
        "supplier_id": supplier.id,
        "items": [{
            "product_id": None,
            "product_name": "不存在品項",
            "quantity": None,
            "unit_of_measure": "EA",
            "specifications": {},
        }],
        "missing_fields": ["items.0.product_id", "items.0.quantity"],
        "ready_for_draft": False,
    }

    draft, error_code = trigger_resume(
        review_id=1, raw_input_text="跟優品科採購一批不存在品項", requester_id=user.id, supplier_id=supplier.id,
    )

    assert draft is None
    assert error_code == RESUME_ERROR_MISSING_FIELDS
    assert PurchaseRequest.objects.count() == 0


@pytest.mark.django_db
@patch("services.inquiry_resume_service.resolve_candidate_after_manual_review")
def test_trigger_resume_parse_failure_returns_parse_failed_error_code(mock_resolve, user, supplier):
    mock_resolve.side_effect = InquiryTriggerError("AI 需求解析失敗，請稍後再試")

    draft, error_code = trigger_resume(
        review_id=1, raw_input_text="跟優品科採購A產品", requester_id=user.id, supplier_id=supplier.id,
    )

    assert draft is None
    assert error_code == RESUME_ERROR_PARSE_FAILED
    assert PurchaseRequest.objects.count() == 0


@pytest.mark.django_db
@patch("services.inquiry_resume_service.resolve_candidate_after_manual_review")
def test_trigger_resume_validation_failure_returns_invalid_input_error_code(mock_resolve, user, supplier):
    mock_resolve.side_effect = InquiryValidationError("採購需求不可為空")

    draft, error_code = trigger_resume(
        review_id=1, raw_input_text="   ", requester_id=user.id, supplier_id=supplier.id,
    )

    assert draft is None
    assert error_code == RESUME_ERROR_INVALID_INPUT


@pytest.mark.django_db
@patch("services.inquiry_resume_service.resolve_candidate_after_manual_review")
def test_trigger_resume_unmaskable_supplier_returns_dedicated_error_code(mock_resolve, user, supplier):
    mock_resolve.side_effect = InquiryUnmaskableSupplierError("找不到可定位的供應商片段，無法安全遮罩後續傳送 AI 解析")

    draft, error_code = trigger_resume(
        review_id=1, raw_input_text="A", requester_id=user.id, supplier_id=supplier.id,
    )

    assert draft is None
    assert error_code == RESUME_ERROR_UNMASKABLE_SUPPLIER


@pytest.mark.django_db
def test_trigger_resume_unknown_supplier_raises():
    with pytest.raises(InquiryResumeError):
        trigger_resume(review_id=1, raw_input_text="x", requester_id=1, supplier_id=99999)


@pytest.mark.django_db
def test_trigger_resume_unknown_requester_raises(supplier):
    with pytest.raises(InquiryResumeError):
        trigger_resume(review_id=1, raw_input_text="x", requester_id=99999, supplier_id=supplier.id)


@pytest.mark.django_db
@patch("services.inquiry_resume_service.resolve_candidate_after_manual_review")
def test_trigger_resume_requester_without_create_permission_returns_permission_denied(
    mock_resolve, user, supplier, product,
):
    # user（role_employee）預設沒有任何權限授予（見 conftest），create_draft 內部的
    # _require_permission 會擋下來——這屬於「無法自動建立草稿」的正常情況之一，
    # 不應該讓 decide API 500，改回傳非敏感錯誤代碼讓管理員人工確認。
    mock_resolve.return_value = {
        "purpose": "辦公設備汰換",
        "needed_by": None,
        "currency": "TWD",
        "supplier_id": supplier.id,
        "items": [{
            "product_id": product.id,
            "product_name": product.name,
            "quantity": "5",
            "unit_of_measure": "EA",
            "specifications": {},
        }],
        "missing_fields": [],
        "ready_for_draft": True,
    }

    draft, error_code = trigger_resume(
        review_id=1, raw_input_text="跟優品科採購A產品", requester_id=user.id, supplier_id=supplier.id,
    )

    assert draft is None
    assert error_code == RESUME_ERROR_PERMISSION_DENIED
    assert PurchaseRequest.objects.count() == 0


@pytest.mark.django_db
def test_trigger_resume_unmaskable_supplier_end_to_end_without_leaking_name(user, supplier):
    # 端到端（不 mock resolve_candidate_after_manual_review）驗證 Codex 審查發現的
    # fail-open 缺口已修正：raw_text 找不到任何可定位的供應商片段時，masking_service
    # 會 fail-closed 拋出 MaskingError，一路轉換成 trigger_resume 回傳
    # (None, RESUME_ERROR_UNMASKABLE_SUPPLIER)（不建立草稿、不洩漏供應商真名），
    # 而不是讓例外往上炸穿已提交的複核決議交易。
    draft, error_code = trigger_resume(review_id=1, raw_input_text="A", requester_id=user.id, supplier_id=supplier.id)
    assert draft is None
    assert error_code == RESUME_ERROR_UNMASKABLE_SUPPLIER
    assert PurchaseRequest.objects.count() == 0


def test_draft_error_is_caught_by_trigger_resume_contract():
    # 防呆：確保 create_draft 實際拋出的例外型別確實是 trigger_resume 攔截的 DraftError，
    # 避免未來 purchase_request_draft_service 改了例外階層卻沒同步這裡。
    from services.purchase_request_draft_service import DraftPermissionDenied

    assert issubclass(DraftPermissionDenied, DraftError)
