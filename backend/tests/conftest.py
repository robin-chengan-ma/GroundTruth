import pytest
from rest_framework.test import APIClient

from apps.core.models import Role, User
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
    return Product.objects.create(name="測試產品", price="100.00", currency="TWD")
