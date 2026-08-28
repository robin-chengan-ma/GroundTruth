from django.db import transaction

from apps.audit.models import AuditLog
from apps.procurement.models import Approval, Quote


class ApprovalError(Exception):
    """簽核輸入或角色資格不符。"""


class ApprovalConflictError(ApprovalError):
    """案件已被認領、結案或不是目前使用者認領。"""


@transaction.atomic
def claim_approval(approval_id, user):
    approval = _get_locked_approval(approval_id)
    if approval.status != Approval.Status.PENDING or approval.approver_id is not None:
        raise ApprovalConflictError("此案件已被認領或已結案")
    if approval.role_id != user.role_id:
        raise ApprovalError("目前角色不符合此案件的簽核資格")
    approval.approver = user
    approval.save(update_fields=["approver", "updated_at"])
    AuditLog.objects.create(
        user=user,
        quote=approval.quote,
        action_type="approval_claim",
        verification_result="n/a",
    )
    return approval


@transaction.atomic
def decide_approval(approval_id, user, decision):
    if decision not in (Approval.Status.APPROVED, Approval.Status.REJECTED):
        raise ApprovalError("decision 必須是 approved 或 rejected")
    approval = _get_locked_approval(approval_id)
    if approval.status != Approval.Status.PENDING or approval.approver_id != user.id:
        raise ApprovalConflictError("只有認領此案件的使用者可以決議")

    approval.status = decision
    approval.save(update_fields=["status", "updated_at"])
    approval.quote.status = Quote.Status.APPROVED if decision == Approval.Status.APPROVED else Quote.Status.REJECTED
    approval.quote.save(update_fields=["status"])
    AuditLog.objects.create(
        user=user,
        quote=approval.quote,
        action_type="approval_decision",
        verification_result=decision,
    )
    return approval


@transaction.atomic
def withdraw_quote(quote_id, user):
    try:
        quote = Quote.objects.select_for_update().get(pk=quote_id)
    except Quote.DoesNotExist as exc:
        raise ApprovalError("找不到指定的採購單") from exc
    if quote.user_id != user.id:
        raise ApprovalError("只有原申請人可以撤回採購單")
    if quote.status != Quote.Status.PENDING_APPROVAL:
        raise ApprovalConflictError("只有待簽核案件可以撤回")

    try:
        approval = Approval.objects.select_for_update().get(quote=quote)
    except Approval.DoesNotExist as exc:
        raise ApprovalError("採購單缺少簽核路由，無法撤回") from exc
    if approval.status != Approval.Status.PENDING:
        raise ApprovalConflictError("簽核案件已結案，無法撤回")

    quote.status = Quote.Status.CANCELLED
    quote.save(update_fields=["status"])
    approval.status = Approval.Status.CANCELLED
    approval.save(update_fields=["status", "updated_at"])
    AuditLog.objects.create(
        user=user,
        quote=quote,
        action_type="quote_withdrawal",
        verification_result="n/a",
    )
    return quote


def _get_locked_approval(approval_id):
    try:
        return Approval.objects.select_for_update().select_related("quote", "role").get(pk=approval_id)
    except Approval.DoesNotExist as exc:
        raise ApprovalError("找不到指定的簽核案件") from exc
