from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.core.models import Permission, Role, RolePermission, User, UserRole
from apps.crm.models import Supplier
from apps.erp.models import Product


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def role_employee(db):
    return Role.objects.create(role="employee", approval_amount_limit=None)


@pytest.fixture
def role_admin(db):
    return Role.objects.create(role="admin", approval_amount_limit=None)


@pytest.fixture
def admin_user(db, role_admin):
    user = User.objects.create(
        name="Test Admin",
        email="test.admin@groundtruth.demo",
        password="hashed-not-tested-here",
        role=role_admin,
    )
    UserRole.objects.create(user=user, role=role_admin)
    for code in (
        "identity.manage",
        "master_data.read",
        "master_data.manage",
        "inventory.read",
        "manual_review.claim",
        "manual_review.decide",
        "audit.read",
        "purchase_suggestion.read",
    ):
        permission = Permission.objects.create(code=code, name=code)
        RolePermission.objects.create(role=role_admin, permission=permission)
    return user


@pytest.fixture
def admin_api_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def user(db, role_employee):
    return User.objects.create(
        name="Test User",
        email="test.user@groundtruth.demo",
        password="hashed-not-tested-here",
        role=role_employee,
    )


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(name="測試供應商", tier=Supplier.Tier.NORMAL)


@pytest.fixture
def product(db):
    return Product.objects.create(name="測試產品", price=Decimal("100.00"), currency="TWD")
