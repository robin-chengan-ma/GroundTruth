from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone

from apps.core.models import Permission, Role, RolePermission, UserRole
from apps.erp.models import Product, ProductCategory
from apps.procurement.models import (
    ApprovalPolicy,
    ApprovalPolicyStep,
    SupplierPriceVersion,
    SupplierProduct,
)
from services.approval_policy_service import (
    ApprovalPolicyConflictError,
    ApprovalPolicyNotFoundError,
    find_approval_policy,
)
from services.rbac_service import get_permission_codes, user_has_permission


@pytest.mark.django_db
def test_user_can_hold_multiple_roles(user, role_employee, role_admin):
    UserRole.objects.create(user=user, role=role_employee)
    UserRole.objects.create(user=user, role=role_admin)

    assert set(user.user_roles.values_list("role__role", flat=True)) == {"employee", "admin"}


@pytest.mark.django_db
def test_user_role_pair_is_unique(user, role_employee):
    UserRole.objects.create(user=user, role=role_employee)

    with pytest.raises(IntegrityError):
        UserRole.objects.create(user=user, role=role_employee)


@pytest.mark.django_db
def test_permission_can_be_granted_to_role(role_employee):
    permission = Permission.objects.create(
        code="purchase_request.create",
        name="建立採購需求",
    )
    RolePermission.objects.create(role=role_employee, permission=permission)

    assert role_employee.role_permissions.get().permission == permission


@pytest.mark.django_db
def test_product_category_requires_object_schema():
    category = ProductCategory(code="OFFICE", name="辦公設備", spec_schema=["material"])

    with pytest.raises(ValidationError, match="JSON object"):
        category.full_clean()


@pytest.mark.django_db
def test_product_accepts_category_and_specifications():
    category = ProductCategory.objects.create(
        code="OFFICE",
        name="辦公設備",
        spec_schema={"required": ["material"]},
    )
    product = Product.objects.create(
        name="人體工學椅",
        sku="CHAIR-001",
        category=category,
        specifications={"material": "網布"},
        unit_of_measure="EA",
        price=Decimal("1500.00"),
        currency="TWD",
    )

    assert product.category == category
    assert product.specifications["material"] == "網布"


@pytest.mark.django_db
def test_supplier_product_and_price_version(supplier, product, user):
    supplier_product = SupplierProduct.objects.create(
        supplier=supplier,
        product=product,
        supplier_sku="SUP-CHAIR-01",
        minimum_order_quantity=Decimal("1.000"),
        lead_time_days=7,
    )
    price = SupplierPriceVersion.objects.create(
        supplier_product=supplier_product,
        unit_price=Decimal("1500.00"),
        currency="TWD",
        minimum_quantity=Decimal("1.000"),
        valid_from=timezone.now(),
        created_by=user,
    )

    assert price.supplier_product == supplier_product


@pytest.mark.django_db
def test_supplier_product_pair_is_unique(supplier, product):
    SupplierProduct.objects.create(supplier=supplier, product=product)

    with pytest.raises(IntegrityError):
        SupplierProduct.objects.create(supplier=supplier, product=product)


@pytest.mark.django_db
def test_approval_policy_rejects_invalid_amount_range():
    policy = ApprovalPolicy(
        name="錯誤區間",
        currency="TWD",
        min_amount=Decimal("100000.00"),
        max_amount=Decimal("10000.00"),
        active_from=timezone.now(),
    )

    with pytest.raises(ValidationError):
        policy.full_clean()


@pytest.mark.django_db
def test_approval_policy_steps_are_ordered_and_unique(role_employee):
    now = timezone.now()
    policy = ApprovalPolicy.objects.create(
        name="TWD 小額",
        currency="TWD",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("10000.00"),
        active_from=now,
        active_until=now + timedelta(days=365),
    )
    ApprovalPolicyStep.objects.create(policy=policy, sequence=1, role=role_employee)

    with pytest.raises(IntegrityError):
        ApprovalPolicyStep.objects.create(policy=policy, sequence=1, role=role_employee)


@pytest.mark.django_db
def test_rbac_service_ignores_expired_role(user, role_employee, role_admin):
    create_permission = Permission.objects.create(
        code="purchase_request.create",
        name="建立採購需求",
    )
    audit_permission = Permission.objects.create(code="audit.read", name="讀取稽核紀錄")
    RolePermission.objects.create(role=role_employee, permission=create_permission)
    RolePermission.objects.create(role=role_admin, permission=audit_permission)
    UserRole.objects.create(user=user, role=role_employee)
    UserRole.objects.create(
        user=user,
        role=role_admin,
        valid_from=timezone.now() - timedelta(days=2),
        valid_until=timezone.now() - timedelta(days=1),
    )

    assert get_permission_codes(user) == {"purchase_request.create"}
    assert user_has_permission(user, "purchase_request.create") is True
    assert user_has_permission(user, "audit.read") is False


@pytest.mark.django_db
def test_find_approval_policy_uses_left_inclusive_right_exclusive_range(role_employee):
    now = timezone.now()
    small = ApprovalPolicy.objects.create(
        name="TWD 小額",
        currency="TWD",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("10000.00"),
        active_from=now - timedelta(days=1),
    )
    medium = ApprovalPolicy.objects.create(
        name="TWD 中額",
        currency="TWD",
        min_amount=Decimal("10000.00"),
        max_amount=Decimal("100000.00"),
        active_from=now - timedelta(days=1),
    )
    ApprovalPolicyStep.objects.create(policy=small, sequence=1, role=role_employee)
    ApprovalPolicyStep.objects.create(policy=medium, sequence=1, role=role_employee)

    assert find_approval_policy(Decimal("9999.99"), "TWD", at=now) == small
    assert find_approval_policy(Decimal("10000.00"), "TWD", at=now) == medium


@pytest.mark.django_db
def test_find_approval_policy_raises_when_no_policy_matches():
    with pytest.raises(ApprovalPolicyNotFoundError):
        find_approval_policy(Decimal("100.00"), "USD")


def test_find_approval_policy_rejects_ambiguous_match(monkeypatch):
    monkeypatch.setattr(
        "services.approval_policy_service.ApprovalPolicyRepository.matching",
        lambda **kwargs: [object(), object()],
    )

    with pytest.raises(ApprovalPolicyConflictError):
        find_approval_policy(Decimal("100.00"), "TWD")


@pytest.mark.django_db
def test_seed_demo_data_creates_rbac_and_approval_policy_without_duplicates():
    call_command("seed_demo_data")
    call_command("seed_demo_data")

    assert UserRole.objects.count() == 10
    exception_reviewer = Role.objects.get(role="procurement_exception_reviewer")
    assert set(
        UserRole.objects.filter(role=exception_reviewer).values_list("user__email", flat=True)
    ) == {"carol@groundtruth.demo", "david@groundtruth.demo"}
    assert Permission.objects.filter(code="purchase_request.create").exists()
    assert UserRole.objects.filter(
        user__email="frank@groundtruth.demo", role__role="receiver"
    ).exists()
    assert UserRole.objects.filter(
        user__email="grace@groundtruth.demo", role__role="inspector"
    ).exists()
    assert Permission.objects.filter(code="receipt.record").exists()
    assert Permission.objects.filter(code="inspection.decide").exists()
    assert ApprovalPolicy.objects.filter(currency="TWD").count() == 3
    assert not ApprovalPolicy.objects.filter(currency="TWD").exclude(
        waiver_role=exception_reviewer
    ).exists()
    large_policy = ApprovalPolicy.objects.get(name="TWD 大額 Demo")
    assert large_policy.steps.get().role.role == "procurement_director"
