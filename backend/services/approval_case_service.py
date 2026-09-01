"""Phase 4.1 C5-2：得標簽核案件、依序認領與 waiver 雙人覆核。"""

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.procurement.models import (
    ApprovalCase,
    ApprovalStep,
    ApprovalStepWaiver,
    AwardDecision,
    PurchaseRequest,
    QuoteRequirementResult,
)
from repositories.core import RbacRepository
from repositories.procurement import ApprovalCaseRepository
from services.approval_policy_service import (
    ApprovalPolicyConflictError,
    ApprovalPolicyNotFoundError,
    find_approval_policy,
)
from services.purchase_order_service import PurchaseOrderConflict, create_purchase_orders_for_award
from services.rbac_service import get_permission_codes


class ApprovalWorkflowError(Exception):
    code = "invalid_approval"


class ApprovalWorkflowNotFound(ApprovalWorkflowError):
    code = "not_found"


class ApprovalWorkflowPermissionDenied(ApprovalWorkflowError):
    code = "permission_denied"


class ApprovalWorkflowConflict(ApprovalWorkflowError):
    code = "conflict"


def _audit(user, action_type, case, result="n/a"):
    AuditLog.objects.create(
        user=user,
        action_type=action_type,
        real_query_summary=f"approval_case_id={case.id}",
        verification_result=result,
    )


def _waivers_for_award(award):
    return list(
        QuoteRequirementResult.objects.select_related("requirement", "waived_by")
        .filter(
            quote_item__award_lines__award=award,
            result=QuoteRequirementResult.Result.WAIVED,
        )
        .distinct()
        .order_by("id")
    )


def create_approval_case_for_award(award):
    """必須由包含得標提交的 transaction 呼叫，使狀態與關卡同成同敗。"""
    total = sum((line.amount_snapshot for line in award.lines.all()), Decimal("0.00"))
    try:
        policy = find_approval_policy(total, "TWD")
    except (ApprovalPolicyNotFoundError, ApprovalPolicyConflictError) as exc:
        raise ApprovalWorkflowConflict(str(exc)) from exc
    policy_steps = list(policy.steps.select_related("role").order_by("sequence"))
    if not policy_steps:
        raise ApprovalWorkflowConflict("簽核政策尚未設定金額關卡")
    if any(step.decision_mode != "any_one" for step in policy_steps):
        raise ApprovalWorkflowConflict("目前簽核流程僅支援 any_one 決議模式")
    waivers = _waivers_for_award(award)
    if waivers and policy.waiver_role_id is None:
        raise ApprovalWorkflowConflict("此政策未設定必要條件例外覆核角色")
    now = timezone.now()
    try:
        case = ApprovalCase.objects.create(
            award=award,
            policy=policy,
            requester=award.rfq.request.requester,
            policy_snapshot={
                "id": policy.id,
                "name": policy.name,
                "currency": policy.currency,
                "min_amount": str(policy.min_amount),
                "max_amount": str(policy.max_amount) if policy.max_amount is not None else None,
                "waiver_role_id": policy.waiver_role_id,
                "steps": [
                    {
                        "sequence": step.sequence,
                        "role_id": step.role_id,
                        "role": step.role.role,
                        "decision_mode": step.decision_mode,
                    }
                    for step in policy_steps
                ],
            },
            total_amount=total,
            currency="TWD",
            submitted_at=now,
        )
    except IntegrityError as exc:
        raise ApprovalWorkflowConflict("此得標方案已建立簽核案件") from exc
    sequence = 1
    if waivers:
        waiver_step = ApprovalStep.objects.create(
            approval_case=case,
            sequence=sequence,
            step_type=ApprovalStep.StepType.WAIVER_EXCEPTION,
            role=policy.waiver_role,
            role_snapshot={
                "role_id": policy.waiver_role_id,
                "role": policy.waiver_role.role,
                "decision_mode": "any_one",
                "required_permissions": ["requirement.waive", "approval.decide"],
            },
        )
        ApprovalStepWaiver.objects.bulk_create(
            [
                ApprovalStepWaiver(
                    approval_step=waiver_step,
                    quote_requirement_result=waiver,
                )
                for waiver in waivers
            ]
        )
        sequence += 1
    for policy_step in policy_steps:
        ApprovalStep.objects.create(
            approval_case=case,
            sequence=sequence,
            step_type=ApprovalStep.StepType.AMOUNT_APPROVAL,
            role=policy_step.role,
            role_snapshot={
                "role_id": policy_step.role_id,
                "role": policy_step.role.role,
                "decision_mode": policy_step.decision_mode,
                "policy_sequence": policy_step.sequence,
            },
        )
        sequence += 1
    _audit(award.selected_by, "approval_case_created", case)
    return case


def _active_role_ids(user):
    return set(RbacRepository.active_role_ids(user.id))


def _require_action_permissions(user, *required):
    permissions = get_permission_codes(user)
    if not set(required) <= permissions:
        raise ApprovalWorkflowPermissionDenied("沒有認領或決議此簽核案件的權限")


def _ensure_actor_allowed(step, user):
    if step.role_id not in _active_role_ids(user):
        raise ApprovalWorkflowPermissionDenied("不屬於此簽核關卡的指定角色")
    if step.approval_case.requester_id == user.id:
        raise ApprovalWorkflowPermissionDenied("申請人不得認領或核准自己的案件")
    if step.step_type == ApprovalStep.StepType.WAIVER_EXCEPTION:
        if "requirement.waive" not in get_permission_codes(user):
            raise ApprovalWorkflowPermissionDenied("沒有必要條件例外覆核權限")
        original_approvers = {
            link.quote_requirement_result.waived_by_id for link in step.waivers.all()
        }
        if user.id in original_approvers:
            raise ApprovalWorkflowPermissionDenied("原 waiver 核准人不得再次覆核同一例外")


def _locked_step(step_id):
    try:
        return ApprovalCaseRepository.step_for_update(step_id)
    except ObjectDoesNotExist as exc:
        raise ApprovalWorkflowNotFound("找不到指定的簽核關卡") from exc


@transaction.atomic
def claim_step(user, step_id):
    _require_action_permissions(user, "approval.claim", "approval.decide")
    step = _locked_step(step_id)
    _ensure_actor_allowed(step, user)
    if step.status != ApprovalStep.Status.PENDING:
        raise ApprovalWorkflowConflict("此關卡已被認領或已結案")
    if step.approval_case.steps.filter(sequence__lt=step.sequence).exclude(
        status=ApprovalStep.Status.APPROVED
    ).exists():
        raise ApprovalWorkflowConflict("前一簽核關卡尚未通過，不可跳關認領")
    now = timezone.now()
    step.status = ApprovalStep.Status.CLAIMED
    step.claimed_by = user
    step.claimed_at = now
    step.save(update_fields=["status", "claimed_by", "claimed_at", "updated_at"])
    case = ApprovalCase.objects.select_for_update().get(pk=step.approval_case_id)
    if case.status == ApprovalCase.Status.PENDING:
        case.status = ApprovalCase.Status.IN_PROGRESS
        case.version += 1
        case.save(update_fields=["status", "version", "updated_at"])
    _audit(user, "approval_step_claimed", case)
    return ApprovalCaseRepository.get(case.id).steps.get(pk=step.id)


@transaction.atomic
def decide_step(user, step_id, decision, reason):
    _require_action_permissions(user, "approval.decide")
    if decision not in {ApprovalStep.Status.APPROVED, ApprovalStep.Status.REJECTED}:
        raise ApprovalWorkflowError("decision 必須是 approved 或 rejected")
    reason = str(reason or "").strip()
    if not reason:
        raise ApprovalWorkflowError("簽核決議必須填寫理由")
    step = _locked_step(step_id)
    _ensure_actor_allowed(step, user)
    if step.status != ApprovalStep.Status.CLAIMED or step.claimed_by_id != user.id:
        raise ApprovalWorkflowConflict("只有認領此關卡的使用者可以決議")
    case = ApprovalCase.objects.select_for_update().select_related(
        "award__rfq__request"
    ).get(pk=step.approval_case_id)
    now = timezone.now()
    step.status = decision
    step.decided_by = user
    step.decided_at = now
    step.decision_reason = reason
    step.save(
        update_fields=["status", "decided_by", "decided_at", "decision_reason", "updated_at"]
    )
    award = case.award
    request = award.rfq.request
    if decision == ApprovalStep.Status.REJECTED:
        case.status = ApprovalCase.Status.REJECTED
        case.decided_at = now
        award.status = AwardDecision.Status.REJECTED
        request.status = PurchaseRequest.Status.REJECTED
    elif not case.steps.exclude(status=ApprovalStep.Status.APPROVED).exists():
        current_total = sum(
            (line.amount_snapshot for line in award.lines.all()), Decimal("0.00")
        )
        if current_total != case.total_amount:
            raise ApprovalWorkflowConflict("得標金額與簽核案件快照不一致")
        case.status = ApprovalCase.Status.APPROVED
        case.decided_at = now
        award.status = AwardDecision.Status.APPROVED
        try:
            create_purchase_orders_for_award(award, user)
        except PurchaseOrderConflict as exc:
            raise ApprovalWorkflowConflict(str(exc)) from exc
        request.status = PurchaseRequest.Status.ORDERED
    case.version += 1
    case.save(update_fields=["status", "decided_at", "version", "updated_at"])
    award.save(update_fields=["status"])
    if decision == ApprovalStep.Status.REJECTED or case.status == ApprovalCase.Status.APPROVED:
        request.version += 1
        request.save(update_fields=["status", "version", "updated_at"])
    _audit(user, "approval_step_decided", case, decision)
    return ApprovalCaseRepository.get(case.id).steps.get(pk=step.id)


def list_accessible_cases(user):
    permissions = get_permission_codes(user)
    audit_all = "audit.read" in permissions
    if "approval.read_all" not in permissions and not audit_all:
        raise ApprovalWorkflowPermissionDenied("沒有讀取簽核佇列的權限")
    return ApprovalCaseRepository.accessible(role_ids=_active_role_ids(user), audit_all=audit_all)


def get_accessible_case(user, case_id):
    cases = list_accessible_cases(user)
    try:
        return cases.get(pk=case_id)
    except ApprovalCase.DoesNotExist as exc:
        raise ApprovalWorkflowNotFound("找不到指定的簽核案件") from exc


def _step_capabilities(step, user):
    permissions = get_permission_codes(user)
    active_role_ids = _active_role_ids(user)
    actor_allowed = (
        step.role_id in active_role_ids
        and step.approval_case.requester_id != user.id
        and {"approval.claim", "approval.decide"} <= permissions
    )
    if actor_allowed and step.step_type == ApprovalStep.StepType.WAIVER_EXCEPTION:
        original_approvers = {
            link.quote_requirement_result.waived_by_id for link in step.waivers.all()
        }
        actor_allowed = "requirement.waive" in permissions and user.id not in original_approvers
    previous_approved = not step.approval_case.steps.filter(
        sequence__lt=step.sequence
    ).exclude(status=ApprovalStep.Status.APPROVED).exists()
    return {
        "can_claim": actor_allowed and previous_approved and step.status == ApprovalStep.Status.PENDING,
        "can_decide": (
            actor_allowed
            and step.status == ApprovalStep.Status.CLAIMED
            and step.claimed_by_id == user.id
        ),
    }


def serialize_step(step, user=None):
    capabilities = _step_capabilities(step, user) if user is not None else {
        "can_claim": False,
        "can_decide": False,
    }
    return {
        "id": step.id,
        "sequence": step.sequence,
        "step_type": step.step_type,
        "role": {"id": step.role_id, "code": step.role.role},
        "status": step.status,
        "claimed_by": (
            {"id": step.claimed_by_id, "name": step.claimed_by.name} if step.claimed_by_id else None
        ),
        "claimed_at": step.claimed_at,
        "decided_by": (
            {"id": step.decided_by_id, "name": step.decided_by.name} if step.decided_by_id else None
        ),
        "decided_at": step.decided_at,
        "decision_reason": step.decision_reason,
        **capabilities,
    }


def serialize_case(case, user=None):
    return {
        "id": case.id,
        "award_id": case.award_id,
        "request_id": case.award.rfq.request_id,
        "request_no": case.award.rfq.request.request_no,
        "purpose": case.award.rfq.request.purpose,
        "requester": {"id": case.requester_id, "name": case.requester.name},
        "policy": {"id": case.policy_id, "name": case.policy.name},
        "total_amount": f"{case.total_amount:.2f}",
        "currency": case.currency,
        "status": case.status,
        "submitted_at": case.submitted_at,
        "decided_at": case.decided_at,
        "steps": [serialize_step(step, user) for step in case.steps.all().order_by("sequence")],
    }
