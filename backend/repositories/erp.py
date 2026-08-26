from apps.erp.models import Inventory, Product, PurchaseSuggestion


class ProductRepository:
    model = Product

    @staticmethod
    def all():
        return Product.objects.all()

    @staticmethod
    def get(pk):
        return Product.objects.get(pk=pk)


class InventoryRepository:
    model = Inventory

    @staticmethod
    def all():
        return Inventory.objects.select_related("product").all()

    @staticmethod
    def get(pk):
        return Inventory.objects.select_related("product").get(pk=pk)

    @staticmethod
    def below_threshold():
        from django.db.models import F

        return Inventory.objects.filter(stock_qty__lt=F("threshold"))


class PurchaseSuggestionRepository:
    model = PurchaseSuggestion

    @staticmethod
    def all():
        return PurchaseSuggestion.objects.select_related("product").all()

    @staticmethod
    def has_pending_for_product(product_id) -> bool:
        return PurchaseSuggestion.objects.filter(
            product_id=product_id, status=PurchaseSuggestion.Status.PENDING
        ).exists()
