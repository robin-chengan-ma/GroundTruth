from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="成本/單價")
    currency = models.CharField(max_length=10, default="TWD")

    class Meta:
        db_table = "products"

    def __str__(self):
        return self.name


class Inventory(models.Model):
    product = models.OneToOneField(
        Product, on_delete=models.CASCADE, related_name="inventory", db_column="product_id",
    )
    stock_qty = models.IntegerField(default=0, help_text="目前庫存數量")
    threshold = models.IntegerField(help_text="低於此值觸發 purchase_suggestions")

    class Meta:
        db_table = "inventory"

    def __str__(self):
        return f"{self.product.name}: {self.stock_qty}"


class PurchaseSuggestion(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        PROCESSED = "processed", "processed"
        DISMISSED = "dismissed", "dismissed"

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="purchase_suggestions", db_column="product_id",
    )
    suggested_qty = models.IntegerField(help_text="系統建議本次補貨數量，演算法於實作階段定案")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "purchase_suggestions"

    def __str__(self):
        return f"{self.product.name} x{self.suggested_qty} ({self.status})"
