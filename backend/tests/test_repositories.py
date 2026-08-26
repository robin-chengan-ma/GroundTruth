import pytest

from apps.erp.models import Inventory
from apps.procurement.models import Quote
from repositories.core import UserRepository
from repositories.crm import SupplierRepository
from repositories.erp import InventoryRepository, PurchaseSuggestionRepository
from repositories.procurement import QuoteRepository


@pytest.mark.django_db
def test_user_repository_find_by_role(user, role_employee):
    results = UserRepository.find_by_role("employee")
    assert user in results


@pytest.mark.django_db
def test_supplier_repository_exact_match(supplier):
    assert SupplierRepository.find_by_exact_name("測試供應商") == supplier
    assert SupplierRepository.find_by_exact_name("不存在的供應商") is None


@pytest.mark.django_db
def test_inventory_below_threshold(product):
    low = Inventory.objects.create(product=product, stock_qty=1, threshold=5)
    results = InventoryRepository.below_threshold()
    assert low in results


@pytest.mark.django_db
def test_purchase_suggestion_has_pending_for_product(product):
    from apps.erp.models import PurchaseSuggestion

    assert PurchaseSuggestionRepository.has_pending_for_product(product.id) is False
    PurchaseSuggestion.objects.create(product=product, suggested_qty=10)
    assert PurchaseSuggestionRepository.has_pending_for_product(product.id) is True


@pytest.mark.django_db
def test_quote_repository_approved_history(user, supplier, product):
    Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=1, price="10.00", total_amount="10.00", currency="TWD",
        status=Quote.Status.APPROVED,
    )
    Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=1, price="20.00", total_amount="20.00", currency="TWD",
        status=Quote.Status.PENDING_VERIFICATION,
    )
    history = QuoteRepository.approved_history(supplier.id, product.id)
    assert history.count() == 1
    assert history.first().status == Quote.Status.APPROVED
