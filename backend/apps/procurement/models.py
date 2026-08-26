from django.db import models

from apps.core.models import Role, User
from apps.crm.models import Supplier
from apps.erp.models import Product, PurchaseSuggestion


class Quote(models.Model):
    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "pending_verification"
        PENDING_REVIEW = "pending_review", "pending_review"
        PENDING_APPROVAL = "pending_approval", "pending_approval"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"
        CANCELLED = "cancelled", "cancelled"

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="quotes", db_column="user_id")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="quotes", db_column="supplier_id")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="quotes", db_column="product_id")
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="單價（試算當下的真實數字）")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10)
    ai_summary_text = models.TextField(null=True, blank=True, help_text="LLM 生成摘要；複核核准後改存系統制式文字")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING_VERIFICATION)
    price_deviation_pct = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="本次單價與該供應商+產品歷史已核准均價的偏離百分比；null＝過去無已核准紀錄可比較",
    )
    source_suggestion = models.ForeignKey(
        PurchaseSuggestion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="quotes", db_column="source_suggestion_id",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "quotes"

    def __str__(self):
        return f"Quote#{self.pk} {self.product} x{self.quantity}"


class Approval(models.Model):
    class Level(models.TextChoices):
        SMALL = "small", "small"
        MEDIUM = "medium", "medium"
        LARGE = "large", "large"

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"

    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="approvals", db_column="quote_id")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="approvals", db_column="role_id")
    approver = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="handled_approvals", db_column="approver_id",
        help_text="實際認領/決議的使用者；認領前為 null",
    )
    approval_level = models.CharField(max_length=10, choices=Level.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "approvals"

    def __str__(self):
        return f"Approval#{self.pk} quote={self.quote_id} ({self.status})"
