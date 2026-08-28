from decimal import Decimal

from django.db import transaction

from apps.core.models import Role
from apps.procurement.models import Approval, Quote

SMALL_MAX = Decimal(10000)
MEDIUM_MAX = Decimal(100000)


class ApprovalRoutingError(Exception):
    """簽核角色資料不完整或 Quote 狀態不允許路由。"""


@transaction.atomic
def route_quote(quote):
    locked_quote = Quote.objects.select_for_update().get(pk=quote.pk)
    existing = Approval.objects.select_related("role", "approver").filter(quote=locked_quote).first()
    if existing:
        return existing
    if locked_quote.status != Quote.Status.PENDING_APPROVAL:
        raise ApprovalRoutingError("只有待簽核案件可以建立簽核路由")

    role = (
        Role.objects.filter(approval_amount_limit__gte=locked_quote.total_amount)
        .exclude(role__in=["employee", "admin"])
        .order_by("approval_amount_limit", "id")
        .first()
    )
    if role is None:
        try:
            role = Role.objects.get(role="admin")
        except Role.DoesNotExist as exc:
            raise ApprovalRoutingError("系統缺少 admin 角色，無法建立簽核路由") from exc

    return Approval.objects.create(
        quote=locked_quote,
        role=role,
        approval_level=_approval_level(locked_quote.total_amount),
    )


def _approval_level(amount):
    if amount <= SMALL_MAX:
        return Approval.Level.SMALL
    if amount <= MEDIUM_MAX:
        return Approval.Level.MEDIUM
    return Approval.Level.LARGE
