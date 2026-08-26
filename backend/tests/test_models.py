import pytest

from apps.core.models import Role
from apps.crm.models import Supplier
from apps.erp.models import Inventory, PurchaseSuggestion
from apps.procurement.models import Approval, Quote


@pytest.mark.django_db
def test_role_str(role_employee):
    assert str(role_employee) == "employee"


@pytest.mark.django_db
def test_user_created_with_role(user, role_employee):
    assert user.role_id == role_employee.id
    assert str(user) == "test.user@groundtruth.demo"


@pytest.mark.django_db
def test_role_unique_constraint(role_employee):
    with pytest.raises(Exception):
        Role.objects.create(role="employee")


@pytest.mark.django_db
def test_supplier_default_tier():
    s = Supplier.objects.create(name="無等級供應商")
    assert s.tier == Supplier.Tier.NORMAL


@pytest.mark.django_db
def test_inventory_one_to_one(product):
    inv = Inventory.objects.create(product=product, stock_qty=10, threshold=5)
    assert inv.product == product
    with pytest.raises(Exception):
        Inventory.objects.create(product=product, stock_qty=1, threshold=1)


@pytest.mark.django_db
def test_purchase_suggestion_default_status(product):
    ps = PurchaseSuggestion.objects.create(product=product, suggested_qty=20)
    assert ps.status == PurchaseSuggestion.Status.PENDING


@pytest.mark.django_db
def test_quote_default_status(user, supplier, product):
    q = Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=5, price="100.00", total_amount="500.00", currency="TWD",
    )
    assert q.status == Quote.Status.PENDING_VERIFICATION
    assert q.price_deviation_pct is None
    assert q.source_suggestion is None


@pytest.mark.django_db
def test_approval_defaults(user, supplier, product, role_employee):
    q = Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=1, price="10.00", total_amount="10.00", currency="TWD",
    )
    a = Approval.objects.create(quote=q, role=role_employee, approval_level=Approval.Level.SMALL)
    assert a.status == Approval.Status.PENDING
    assert a.approver is None
