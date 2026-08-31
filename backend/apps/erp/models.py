from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Now


class ProductCategory(models.Model):
    """產品類別及其規格欄位定義。"""

    code = models.CharField(max_length=50, unique=True, db_comment="產品類別唯一代碼")
    name = models.CharField(max_length=100, db_comment="產品類別名稱")
    spec_schema = models.JSONField(default=dict, db_comment="產品規格驗證定義，必須為 JSON object")
    is_active = models.BooleanField(default=True, db_comment="是否允許新產品使用此類別")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "product_categories"
        db_table_comment = "產品類別與規格定義主檔"

    def clean(self):
        super().clean()
        if not isinstance(self.spec_schema, dict):
            raise ValidationError({"spec_schema": "spec_schema 必須是 JSON object"})

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
        db_column="category_id",
        null=True,
        blank=True,
        db_comment="產品類別；舊資料可暫為 NULL",
    )
    sku = models.CharField(max_length=100, null=True, blank=True, db_comment="企業內部品項代碼")
    description = models.TextField(blank=True, db_comment="品項描述")
    specifications = models.JSONField(default=dict, db_comment="依產品類別定義驗證的規格值 JSON object")
    unit_of_measure = models.CharField(max_length=20, default="EA", db_comment="計量單位，例如 EA、KG")
    is_active = models.BooleanField(default=True, db_comment="品項是否可用於新交易")
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="成本/單價")
    currency = models.CharField(max_length=10, default="TWD")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "products"
        constraints = [
            models.UniqueConstraint(
                fields=["sku"],
                condition=models.Q(sku__isnull=False),
                name="products_sku_unique",
            ),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.specifications, dict):
            raise ValidationError({"specifications": "specifications 必須是 JSON object"})

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
        IN_PROGRESS = "in_progress", "in_progress"
        PROCESSED = "processed", "processed"
        DISMISSED = "dismissed", "dismissed"

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="purchase_suggestions", db_column="product_id",
    )
    suggested_qty = models.DecimalField(
        max_digits=14, decimal_places=3, help_text="補足目標庫存所需的建議數量"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    source_movement = models.ForeignKey(
        "InventoryMovement", on_delete=models.PROTECT, related_name="purchase_suggestions",
        db_column="source_movement_id", null=True, blank=True,
        db_comment="觸發建議的庫存流水；既有建議可為 NULL",
    )
    purchase_request = models.ForeignKey(
        "procurement.PurchaseRequest", on_delete=models.PROTECT,
        related_name="source_purchase_suggestions", db_column="purchase_request_id",
        null=True, blank=True, db_comment="由本建議轉成的採購需求",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "purchase_suggestions"

    def __str__(self):
        return f"{self.product.name} x{self.suggested_qty} ({self.status})"


class GoodsReceipt(models.Model):
    """採購單的一次收貨批次；同一採購單可分批收貨。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        INSPECTING = "inspecting", "inspecting"
        POSTED = "posted", "posted"
        PARTIALLY_ACCEPTED = "partially_accepted", "partially_accepted"
        REJECTED = "rejected", "rejected"
        VOIDED = "voided", "voided"

    receipt_no = models.CharField(max_length=50, unique=True, db_comment="收貨單唯一編號")
    purchase_order = models.ForeignKey(
        "procurement.PurchaseOrder",
        on_delete=models.PROTECT,
        related_name="goods_receipts",
        db_column="purchase_order_id",
        db_comment="對應 purchase_orders.id",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_comment="狀態：draft/inspecting/posted/partially_accepted/rejected/voided",
    )
    received_by = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="recorded_goods_receipts",
        db_column="received_by_id",
        null=True,
        blank=True,
        db_comment="實際記錄收貨的 users.id；僅 legacy migration 可為 NULL",
    )
    received_at = models.DateTimeField(null=True, blank=True, db_comment="實際收貨時間；離開 draft 後必填")
    legacy_quote = models.OneToOneField(
        "procurement.Quote",
        on_delete=models.PROTECT,
        related_name="migrated_goods_receipt",
        db_column="legacy_quote_id",
        null=True,
        blank=True,
        db_comment="舊 quotes.id；僅 legacy migration 使用",
    )
    version = models.PositiveIntegerField(default=1, db_comment="樂觀鎖版本，必須大於 0")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "goods_receipts"
        db_table_comment = "採購單的分批收貨主檔"
        constraints = [
            models.CheckConstraint(condition=models.Q(version__gt=0), name="goods_receipts_version_positive"),
            models.CheckConstraint(
                condition=models.Q(legacy_quote__isnull=False) | models.Q(received_by__isnull=False),
                name="goods_receipts_actor_required_unless_legacy",
            ),
            models.CheckConstraint(
                condition=models.Q(status="draft", received_at__isnull=True)
                | (~models.Q(status="draft") & models.Q(received_at__isnull=False)),
                name="goods_receipts_received_time_consistent",
            ),
        ]


class GoodsReceiptItem(models.Model):
    """收貨批次中對應採購單明細的實收數量。"""

    receipt = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.CASCADE,
        related_name="items",
        db_column="receipt_id",
        db_comment="對應 goods_receipts.id",
    )
    purchase_order_item = models.ForeignKey(
        "procurement.PurchaseOrderItem",
        on_delete=models.PROTECT,
        related_name="goods_receipt_items",
        db_column="purchase_order_item_id",
        db_comment="對應 purchase_order_items.id",
    )
    received_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        db_comment="本批實收數量，必須大於 0；跨批累計不得超過訂購量",
    )
    lot_no = models.CharField(max_length=100, blank=True, db_comment="供應商批號或序號群組")
    replacement_variance_line = models.ForeignKey(
        "InspectionVarianceLine",
        on_delete=models.PROTECT,
        related_name="replacement_receipt_items",
        db_column="replacement_variance_line_id",
        null=True,
        blank=True,
        db_comment="補交收貨所依據的驗收差異明細；一般收貨為 NULL",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "goods_receipt_items"
        db_table_comment = "收貨批次的逐項實收紀錄"
        constraints = [
            models.UniqueConstraint(
                fields=["receipt", "purchase_order_item"], name="goods_receipt_items_receipt_po_item_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(received_quantity__gt=0), name="goods_receipt_items_qty_positive"
            ),
        ]


class QualityInspection(models.Model):
    """收貨明細的品質驗收結果；合格、瑕疵與拒收數量分開保存。"""

    class Status(models.TextChoices):
        ACCEPTED = "accepted", "accepted"
        PARTIALLY_ACCEPTED = "partially_accepted", "partially_accepted"
        REJECTED = "rejected", "rejected"

    receipt_item = models.OneToOneField(
        GoodsReceiptItem,
        on_delete=models.PROTECT,
        related_name="quality_inspection",
        db_column="receipt_item_id",
        db_comment="對應 goods_receipt_items.id；每筆收貨明細只能有一筆最終驗收",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        db_comment="結果：accepted/partially_accepted/rejected",
    )
    accepted_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, db_comment="合格數量；只有此數量可入庫"
    )
    defective_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, db_comment="瑕疵待處理數量；不得入庫"
    )
    rejected_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, db_comment="直接拒收數量；不得入庫"
    )
    defect_details = models.TextField(blank=True, db_comment="瑕疵內容；defective_quantity 大於 0 時必填")
    inspected_by = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="quality_inspections",
        db_column="inspected_by_id",
        null=True,
        blank=True,
        db_comment="執行品質驗收的 users.id；僅 legacy migration 可為 NULL",
    )
    inspected_at = models.DateTimeField(db_comment="品質驗收完成時間")
    notes = models.TextField(blank=True, db_comment="驗收補充說明")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "quality_inspections"
        db_table_comment = "收貨明細的最終品質驗收結果"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(accepted_quantity__gte=0)
                & models.Q(defective_quantity__gte=0)
                & models.Q(rejected_quantity__gte=0),
                name="quality_inspections_quantities_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(defective_quantity=0)
                | (~models.Q(defect_details="") & models.Q(defect_details__isnull=False)),
                name="quality_inspections_defect_details_required",
            ),
        ]


class InspectionVarianceCase(models.Model):
    """品質驗收不合格數量的後續處理案件。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        OPEN = "open", "open"
        CLOSED = "closed", "closed"
        CANCELLED = "cancelled", "cancelled"

    quality_inspection = models.OneToOneField(
        QualityInspection, on_delete=models.PROTECT, related_name="variance_case",
        db_column="quality_inspection_id", db_comment="對應有瑕疵或拒收數量的品質驗收",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1, db_comment="樂觀鎖版本，必須大於 0")
    created_by = models.ForeignKey(
        "core.User", on_delete=models.PROTECT, related_name="created_inspection_variances",
        db_column="created_by_id",
    )
    submitted_by = models.ForeignKey(
        "core.User", on_delete=models.PROTECT, related_name="submitted_inspection_variances",
        db_column="submitted_by_id", null=True, blank=True,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        "core.User", on_delete=models.PROTECT, related_name="closed_inspection_variances",
        db_column="closed_by_id", null=True, blank=True,
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    updated_at = models.DateTimeField(db_default=Now(), db_comment="由資料庫 trigger 維護")

    class Meta:
        db_table = "inspection_variance_cases"
        db_table_comment = "品質驗收差異的後續處理案件"
        constraints = [
            models.CheckConstraint(condition=models.Q(version__gt=0), name="inspection_variance_version_positive"),
        ]


class InspectionVarianceLine(models.Model):
    """差異案件內可拆量的退貨、補交、折讓或短交結案決議。"""

    class ActionType(models.TextChoices):
        REPLACEMENT = "replacement", "replacement"
        RETURN = "return", "return"
        CREDIT = "credit", "credit"
        WAIVE = "waive", "waive"

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        COMPLETED = "completed", "completed"
        CANCELLED = "cancelled", "cancelled"

    variance_case = models.ForeignKey(
        InspectionVarianceCase, on_delete=models.PROTECT, related_name="lines",
        db_column="variance_case_id",
    )
    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField()
    completed_by = models.ForeignKey(
        "core.User", on_delete=models.PROTECT, related_name="completed_inspection_variance_lines",
        db_column="completed_by_id", null=True, blank=True,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "inspection_variance_lines"
        db_table_comment = "驗收差異的拆量處理明細"
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="inspection_variance_line_qty_positive"),
            models.CheckConstraint(condition=~models.Q(reason=""), name="inspection_variance_line_reason_not_blank"),
        ]


class InventoryMovement(models.Model):
    """不可覆寫的庫存異動真相來源；更正必須新增反向流水。"""

    class MovementType(models.TextChoices):
        RECEIPT_ACCEPT = "receipt_accept", "receipt_accept"
        RETURN_OUT = "return_out", "return_out"
        ISSUE_OUT = "issue_out", "issue_out"
        ADJUSTMENT_IN = "adjustment_in", "adjustment_in"
        ADJUSTMENT_OUT = "adjustment_out", "adjustment_out"
        REVERSAL = "reversal", "reversal"
        MIGRATION_ASSUMED_RECEIPT = "migration_assumed_receipt", "migration_assumed_receipt"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="inventory_movements",
        db_column="product_id",
        db_comment="對應 products.id",
    )
    movement_type = models.CharField(
        max_length=40,
        choices=MovementType.choices,
        db_comment="異動類型：receipt_accept/return_out/issue_out/adjustment_in/adjustment_out/reversal/migration_assumed_receipt",
    )
    quantity_delta = models.DecimalField(
        max_digits=14, decimal_places=3, db_comment="庫存數量增減值，不得為 0"
    )
    reference_type = models.CharField(max_length=50, db_comment="來源類型，例如 quality_inspection")
    reference_id = models.PositiveBigIntegerField(db_comment="來源資料主鍵")
    affects_balance = models.BooleanField(default=True, db_comment="是否實際影響 inventory_balances")
    reason = models.TextField(db_comment="異動或更正原因")
    posted_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="正式過帳時間（由資料庫產生）")
    posted_by = models.ForeignKey(
        "core.User",
        on_delete=models.PROTECT,
        related_name="posted_inventory_movements",
        db_column="posted_by_id",
        null=True,
        blank=True,
        db_comment="過帳者 users.id；系統 migration 可為 NULL",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "inventory_movements"
        db_table_comment = "不可覆寫的庫存異動流水帳"
        constraints = [
            models.UniqueConstraint(
                fields=["reference_type", "reference_id", "movement_type"],
                name="inventory_movements_reference_type_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(quantity_delta=0), name="inventory_movements_delta_nonzero"
            ),
            models.CheckConstraint(
                condition=~models.Q(reason=""), name="inventory_movements_reason_not_blank"
            ),
        ]


class InventoryBalance(models.Model):
    """由庫存流水在同一交易維護的品項庫存查詢快照。"""

    product = models.OneToOneField(
        Product,
        on_delete=models.PROTECT,
        related_name="inventory_balance",
        db_column="product_id",
        primary_key=True,
        serialize=False,
        db_comment="對應 products.id，亦為本表主鍵",
    )
    on_hand_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, db_comment="已驗收合格且實際在庫數量"
    )
    reserved_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, db_comment="已保留但尚未出庫數量"
    )
    in_transit_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, db_comment="已發出採購單但尚未完成驗收數量快照"
    )
    version = models.PositiveIntegerField(default=1, db_comment="樂觀鎖版本，必須大於 0")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "inventory_balances"
        db_table_comment = "品項庫存餘額查詢快照；真相來源為 inventory_movements"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(on_hand_quantity__gte=0)
                & models.Q(reserved_quantity__gte=0)
                & models.Q(in_transit_quantity__gte=0),
                name="inventory_balances_quantities_nonnegative",
            ),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="inventory_balances_version_positive"),
        ]
