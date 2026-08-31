from django.db import models
from django.db.models.functions import Now


class Supplier(models.Model):
    class Tier(models.TextChoices):
        PRIORITY = "priority", "priority"
        NORMAL = "normal", "normal"
        WATCH = "watch", "watch"

    name = models.CharField(max_length=200, unique=True)
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.NORMAL)
    code = models.CharField(max_length=50, null=True, blank=True, db_comment="企業內部供應商代碼")
    status = models.CharField(
        max_length=20,
        choices=[("active", "active"), ("on_hold", "on_hold"), ("blocked", "blocked")],
        default="active",
        db_comment="供應商狀態：active/on_hold/blocked",
    )
    tax_id = models.CharField(max_length=30, null=True, blank=True, db_comment="統一編號或稅籍識別碼")
    contact = models.JSONField(default=dict, db_comment="聯絡資料 JSON object；API 依權限遮罩")
    payment_terms = models.CharField(max_length=100, blank=True, db_comment="預設付款條件")
    is_active = models.BooleanField(default=True, db_comment="是否允許用於新交易")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "suppliers"
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(code__isnull=False),
                name="suppliers_code_unique",
            ),
            models.UniqueConstraint(
                fields=["tax_id"],
                condition=models.Q(tax_id__isnull=False),
                name="suppliers_tax_id_unique",
            ),
        ]

    def __str__(self):
        return self.name
