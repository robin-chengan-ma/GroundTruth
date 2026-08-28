from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.core.models import Role, User
from apps.procurement.models import Approval, Quote
from services.approval_routing_service import ApprovalRoutingError, route_quote
from services.approval_service import (
    ApprovalConflictError,
    ApprovalError,
    claim_approval,
    decide_approval,
    withdraw_quote,
)


@pytest.fixture
def approver_10k_role(db):
    return Role.objects.create(role="approver_10k", approval_amount_limit=Decimal(10000))


@pytest.fixture
def approver_100k_role(db):
    return Role.objects.create(role="approver_100k", approval_amount_limit=Decimal(100000))


@pytest.fixture
def approver_user(db, approver_10k_role):
    return User.objects.create(
        name="Approver", email="approver@example.com", password="x", role=approver_10k_role
    )


def make_quote(user, supplier, product, total_amount):
    return Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=1,
        price=total_amount,
        total_amount=total_amount,
        currency="TWD",
        status=Quote.Status.PENDING_APPROVAL,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("amount", "expected_level", "expected_role"),
    [
        (Decimal(10000), "small", "approver_10k"),
        (Decimal("10000.01"), "medium", "approver_100k"),
        (Decimal(100000), "medium", "approver_100k"),
        (Decimal("100000.01"), "large", "admin"),
    ],
)
def test_route_quote_uses_exact_boundaries(
    user,
    supplier,
    product,
    role_admin,
    approver_10k_role,
    approver_100k_role,
    amount,
    expected_level,
    expected_role,
):
    quote = make_quote(user, supplier, product, amount)

    approval = route_quote(quote)

    assert approval.approval_level == expected_level
    assert approval.role.role == expected_role
    assert approval.approver is None


@pytest.mark.django_db
def test_claim_requires_matching_routed_role(user, supplier, product, role_admin, approver_10k_role):
    quote = make_quote(user, supplier, product, Decimal(5000))
    approval = route_quote(quote)
    admin = User.objects.create(name="Admin", email="admin@example.com", password="x", role=role_admin)

    with pytest.raises(ApprovalError, match="不符合"):
        claim_approval(approval.id, admin)


@pytest.mark.django_db
def test_claim_prevents_double_claim(user, supplier, product, approver_user):
    approval = route_quote(make_quote(user, supplier, product, Decimal(5000)))
    claim_approval(approval.id, approver_user)

    with pytest.raises(ApprovalConflictError):
        claim_approval(approval.id, approver_user)


@pytest.mark.django_db
def test_decide_updates_quote_and_writes_audit_log(user, supplier, product, approver_user):
    quote = make_quote(user, supplier, product, Decimal(5000))
    approval = route_quote(quote)
    claim_approval(approval.id, approver_user)

    decided = decide_approval(approval.id, approver_user, Approval.Status.APPROVED)

    quote.refresh_from_db()
    assert decided.status == Approval.Status.APPROVED
    assert quote.status == Quote.Status.APPROVED
    assert AuditLog.objects.filter(
        user=approver_user, quote=quote, action_type="approval_decision", verification_result="approved"
    ).exists()


@pytest.mark.django_db
def test_only_claimant_can_decide(user, supplier, product, approver_user, approver_10k_role):
    approval = route_quote(make_quote(user, supplier, product, Decimal(5000)))
    claim_approval(approval.id, approver_user)
    other = User.objects.create(name="Other", email="other@example.com", password="x", role=approver_10k_role)

    with pytest.raises(ApprovalConflictError, match="認領"):
        decide_approval(approval.id, other, Approval.Status.REJECTED)


@pytest.mark.django_db
def test_requester_can_withdraw_pending_approval(user, supplier, product, approver_10k_role):
    quote = make_quote(user, supplier, product, Decimal(5000))
    approval = route_quote(quote)

    withdrawn = withdraw_quote(quote.id, user)

    approval.refresh_from_db()
    assert withdrawn.status == Quote.Status.CANCELLED
    assert approval.status == Approval.Status.CANCELLED
    assert AuditLog.objects.filter(user=user, quote=quote, action_type="quote_withdrawal").exists()


@pytest.mark.django_db
def test_non_requester_cannot_withdraw(user, supplier, product, approver_user):
    quote = make_quote(user, supplier, product, Decimal(5000))
    route_quote(quote)

    with pytest.raises(ApprovalError, match="申請人"):
        withdraw_quote(quote.id, approver_user)


@pytest.mark.django_db
def test_route_quote_is_idempotent(user, supplier, product, approver_10k_role):
    quote = make_quote(user, supplier, product, Decimal(5000))
    first = route_quote(quote)

    assert route_quote(quote).id == first.id


@pytest.mark.django_db
def test_route_quote_rejects_non_pending_quote(user, supplier, product):
    quote = make_quote(user, supplier, product, Decimal(5000))
    quote.status = Quote.Status.APPROVED
    quote.save(update_fields=["status"])

    with pytest.raises(ApprovalRoutingError, match="待簽核"):
        route_quote(quote)


@pytest.mark.django_db
def test_route_quote_requires_admin_for_large_amount(user, supplier, product):
    quote = make_quote(user, supplier, product, Decimal(100001))

    with pytest.raises(ApprovalRoutingError, match="缺少 admin"):
        route_quote(quote)
