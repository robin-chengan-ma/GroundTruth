from django.db import models
from django.db.models.functions import Now

from apps.core.models import Role, User
from apps.crm.models import Supplier
from apps.erp.models import Product, PurchaseSuggestion


class SupplierProduct(models.Model):
    """供應商可供應的品項及商務基準。"""

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="supplier_products",
        db_column="supplier_id",
        db_comment="對應 suppliers.id",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="supplier_products",
        db_column="product_id",
        db_comment="對應 products.id",
    )
    supplier_sku = models.CharField(max_length=100, blank=True, db_comment="供應商自己的品項代碼")
    lead_time_days = models.PositiveIntegerField(default=0, db_comment="預設交期天數")
    minimum_order_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1, db_comment="最小訂購量")
    quality_status = models.CharField(
        max_length=20,
        choices=[("qualified", "qualified"), ("conditional", "conditional"), ("blocked", "blocked")],
        default="qualified",
        db_comment="品質資格：qualified/conditional/blocked",
    )
    is_active = models.BooleanField(default=True, db_comment="是否允許用於新 RFQ")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "supplier_products"
        db_table_comment = "供應商與可供應品項的主檔關係"
        constraints = [
            models.UniqueConstraint(fields=["supplier", "product"], name="supplier_products_pair_unique"),
            models.CheckConstraint(
                condition=models.Q(minimum_order_quantity__gt=0),
                name="supplier_products_moq_positive",
            ),
        ]


class SupplierPriceVersion(models.Model):
    """供應商品項的有效期間價格版本。"""

    supplier_product = models.ForeignKey(
        SupplierProduct,
        on_delete=models.PROTECT,
        related_name="price_versions",
        db_column="supplier_product_id",
        db_comment="對應 supplier_products.id",
    )
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, db_comment="未稅單價")
    currency = models.CharField(max_length=3, default="TWD", db_comment="ISO 4217 三碼大寫幣別")
    minimum_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=1, db_comment="此價格級距的最小數量"
    )
    valid_from = models.DateTimeField(db_comment="價格生效時間")
    valid_until = models.DateTimeField(null=True, blank=True, db_comment="價格失效時間；NULL 表示持續有效")
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_supplier_prices",
        db_column="created_by_id",
        db_comment="建立價格版本的 users.id",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "supplier_price_versions"
        db_table_comment = "供應商品項價格版本；正式交易另存快照"
        constraints = [
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="supplier_prices_nonnegative"),
            models.CheckConstraint(condition=models.Q(minimum_quantity__gt=0), name="supplier_prices_qty_positive"),
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True) | models.Q(valid_until__gt=models.F("valid_from")),
                name="supplier_prices_valid_period",
            ),
        ]
        indexes = [
            models.Index(
                fields=["supplier_product", "currency", "valid_from"],
                name="supplier_price_lookup_idx",
            ),
        ]


class ApprovalPolicy(models.Model):
    """依幣別、金額及生效期間選擇的核准政策。"""

    name = models.CharField(max_length=100, db_comment="核准政策名稱")
    currency = models.CharField(max_length=3, db_comment="ISO 4217 三碼大寫幣別")
    min_amount = models.DecimalField(max_digits=14, decimal_places=2, db_comment="適用最低金額（含）")
    max_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, db_comment="適用最高金額（不含）；NULL 表示無上限"
    )
    active_from = models.DateTimeField(db_comment="政策生效時間")
    active_until = models.DateTimeField(null=True, blank=True, db_comment="政策失效時間；NULL 表示持續有效")
    is_active = models.BooleanField(default=True, db_comment="是否允許新案件選用")
    waiver_role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="waiver_approval_policies",
        db_column="waiver_role_id",
        null=True,
        blank=True,
        db_comment="必要條件例外的獨立覆核角色 roles.id；NULL 表示政策未設定例外覆核",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "approval_policies"
        db_table_comment = "版本化金額核准政策"
        constraints = [
            models.CheckConstraint(condition=models.Q(min_amount__gte=0), name="approval_policy_min_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(max_amount__isnull=True) | models.Q(max_amount__gt=models.F("min_amount")),
                name="approval_policy_amount_range",
            ),
            models.CheckConstraint(
                condition=models.Q(active_until__isnull=True) | models.Q(active_until__gt=models.F("active_from")),
                name="approval_policy_active_period",
            ),
        ]
        indexes = [
            models.Index(fields=["currency", "is_active", "active_from"], name="approval_policy_lookup_idx"),
        ]


class ApprovalPolicyStep(models.Model):
    """核准政策內依序執行的角色步驟。"""

    class DecisionMode(models.TextChoices):
        ANY_ONE = "any_one", "any_one"
        ALL = "all", "all"

    policy = models.ForeignKey(
        ApprovalPolicy,
        on_delete=models.CASCADE,
        related_name="steps",
        db_column="policy_id",
        db_comment="對應 approval_policies.id",
    )
    sequence = models.PositiveIntegerField(db_comment="政策內的核准順序，從 1 開始")
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="approval_policy_steps",
        db_column="role_id",
        db_comment="此步驟可決議的 roles.id",
    )
    decision_mode = models.CharField(
        max_length=10,
        choices=DecisionMode.choices,
        default=DecisionMode.ANY_ONE,
        db_comment="同一步驟決議方式：any_one/all",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "approval_policy_steps"
        db_table_comment = "核准政策的角色與順序快照來源"
        constraints = [
            models.UniqueConstraint(fields=["policy", "sequence"], name="approval_policy_steps_sequence_unique"),
            models.CheckConstraint(condition=models.Q(sequence__gt=0), name="approval_policy_steps_sequence_positive"),
        ]


class PurchaseRequest(models.Model):
    """企業內部的採購需求單。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        SUBMITTED = "submitted", "submitted"
        SOURCING = "sourcing", "sourcing"
        AWARDING = "awarding", "awarding"
        APPROVAL = "approval", "approval"
        REJECTED = "rejected", "rejected"
        ORDERED = "ordered", "ordered"
        PARTIALLY_RECEIVED = "partially_received", "partially_received"
        COMPLETED = "completed", "completed"
        WITHDRAWN = "withdrawn", "withdrawn"
        CANCELLED = "cancelled", "cancelled"

    request_no = models.CharField(max_length=50, unique=True, db_comment="採購需求唯一單號")
    requester = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="purchase_requests",
        db_column="requester_id",
        db_comment="提出需求的 users.id",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_comment=(
            "狀態：draft/submitted/sourcing/awarding/approval/rejected/ordered/partially_received/completed/withdrawn/cancelled"
        ),
    )
    purpose = models.TextField(db_comment="採購目的")
    needed_by = models.DateField(null=True, blank=True, db_comment="期望到貨日期")
    currency = models.CharField(max_length=3, default="TWD", db_comment="ISO 4217 三碼大寫幣別")
    source = models.CharField(max_length=30, default="manual", db_comment="需求來源，例如 manual/ai/legacy")
    legacy_quote = models.OneToOneField(
        "Quote",
        on_delete=models.PROTECT,
        related_name="migrated_purchase_request",
        db_column="legacy_quote_id",
        null=True,
        blank=True,
        db_comment="對應舊 quotes.id；僅舊資料回填使用",
    )
    idempotency_key = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        db_comment="防止重複提交的唯一鍵；草稿可為 NULL",
    )
    version = models.PositiveIntegerField(default=1, db_comment="樂觀鎖版本，必須大於 0")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "purchase_requests"
        db_table_comment = "企業採購需求單；可包含多筆需求明細"
        constraints = [
            models.CheckConstraint(condition=models.Q(version__gt=0), name="purchase_requests_version_positive"),
        ]
        indexes = [
            models.Index(fields=["requester", "status"], name="pr_requester_status_idx"),
            models.Index(fields=["status", "-updated_at"], name="pr_status_updated_idx"),
        ]


class PurchaseRequestItem(models.Model):
    """採購需求的品項與規格快照。"""

    request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="items",
        db_column="request_id",
        db_comment="對應 purchase_requests.id",
    )
    line_no = models.PositiveIntegerField(db_comment="需求單內行號，從 1 開始")
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="purchase_request_items",
        db_column="product_id",
        null=True,
        blank=True,
        db_comment="對應 products.id；尚未建立正式品項時可為 NULL",
    )
    description_snapshot = models.TextField(db_comment="提交時的品項名稱與描述快照")
    specification_snapshot = models.JSONField(default=dict, db_comment="提交時的規格 JSON object 快照")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, db_comment="需求數量，必須大於 0")
    unit_of_measure = models.CharField(max_length=20, db_comment="計量單位快照，例如 EA、KG")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "purchase_request_items"
        db_table_comment = "採購需求明細與不可變品項規格快照"
        constraints = [
            models.UniqueConstraint(fields=["request", "line_no"], name="purchase_request_items_line_unique"),
            models.CheckConstraint(condition=models.Q(line_no__gt=0), name="purchase_request_items_line_positive"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="purchase_request_items_qty_positive"),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.specification_snapshot, dict):
            from django.core.exceptions import ValidationError

            raise ValidationError({"specification_snapshot": "specification_snapshot 必須是 JSON object"})


class RequestItemRequirement(models.Model):
    """需求明細的必要或評選條件快照。"""

    class DataType(models.TextChoices):
        STRING = "string", "string"
        NUMBER = "number", "number"
        BOOLEAN = "boolean", "boolean"
        ENUM = "enum", "enum"

    class Operator(models.TextChoices):
        EQUALS = "equals", "equals"
        NOT_EQUALS = "not_equals", "not_equals"
        GREATER_THAN_OR_EQUAL = "gte", "gte"
        LESS_THAN_OR_EQUAL = "lte", "lte"
        IN = "in", "in"
        CONTAINS = "contains", "contains"

    request_item = models.ForeignKey(
        PurchaseRequestItem,
        on_delete=models.CASCADE,
        related_name="requirements",
        db_column="request_item_id",
        db_comment="對應 purchase_request_items.id",
    )
    code = models.CharField(max_length=50, db_comment="需求條件代碼")
    label = models.CharField(max_length=100, db_comment="使用者可讀的條件名稱")
    data_type = models.CharField(
        max_length=20, choices=DataType.choices, db_comment="資料型別：string/number/boolean/enum"
    )
    operator = models.CharField(
        max_length=20, choices=Operator.choices, db_comment="比較運算子：equals/not_equals/gte/lte/in/contains"
    )
    expected_value = models.JSONField(db_comment="預期值 JSON scalar 或 array")
    is_mandatory = models.BooleanField(default=False, db_comment="是否為不得忽略的必要條件")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "request_item_requirements"
        db_table_comment = "需求明細的規格與必要條件快照"
        constraints = [
            models.UniqueConstraint(fields=["request_item", "code"], name="request_item_requirements_code_unique"),
        ]


class Rfq(models.Model):
    """向多間供應商發出的詢價單版本。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        ISSUED = "issued", "issued"
        COLLECTING = "collecting", "collecting"
        EVALUATING = "evaluating", "evaluating"
        CLOSED = "closed", "closed"
        CANCELLED = "cancelled", "cancelled"

    rfq_no = models.CharField(max_length=50, db_comment="詢價單業務單號；不同 revision 共用")
    request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.PROTECT,
        related_name="rfqs",
        db_column="request_id",
        db_comment="對應 purchase_requests.id",
    )
    revision = models.PositiveIntegerField(default=1, db_comment="詢價修訂版次，從 1 開始")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_comment="狀態：draft/issued/collecting/evaluating/closed/cancelled",
    )
    response_due_at = models.DateTimeField(null=True, blank=True, db_comment="供應商回覆期限")
    rule_snapshot = models.JSONField(default=dict, db_comment="評選規則與權重 JSON object 快照")
    version = models.PositiveIntegerField(default=1, db_comment="樂觀鎖版本，必須大於 0")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "rfqs"
        db_table_comment = "多供應商詢價單及其修訂版本"
        constraints = [
            models.UniqueConstraint(fields=["rfq_no", "revision"], name="rfqs_number_revision_unique"),
            models.UniqueConstraint(
                fields=["request"],
                condition=models.Q(status__in=["draft", "issued", "collecting", "evaluating"]),
                name="rfqs_one_active_per_request",
            ),
            models.CheckConstraint(condition=models.Q(revision__gt=0), name="rfqs_revision_positive"),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="rfqs_version_positive"),
        ]
        indexes = [
            models.Index(fields=["status", "response_due_at"], name="rfq_status_due_idx"),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.rule_snapshot, dict):
            from django.core.exceptions import ValidationError

            raise ValidationError({"rule_snapshot": "rule_snapshot 必須是 JSON object"})


class RfqSupplier(models.Model):
    """RFQ 邀請的供應商。"""

    class Status(models.TextChoices):
        INVITED = "invited", "invited"
        RESPONDED = "responded", "responded"
        DECLINED = "declined", "declined"
        EXPIRED = "expired", "expired"
        CANCELLED = "cancelled", "cancelled"

    rfq = models.ForeignKey(
        Rfq,
        on_delete=models.CASCADE,
        related_name="invited_suppliers",
        db_column="rfq_id",
        db_comment="對應 rfqs.id",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="rfq_invitations",
        db_column="supplier_id",
        db_comment="受邀 suppliers.id",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INVITED,
        db_comment="狀態：invited/responded/declined/expired/cancelled",
    )
    invited_at = models.DateTimeField(db_comment="發出邀請時間")
    responded_at = models.DateTimeField(null=True, blank=True, db_comment="供應商回覆時間")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "rfq_suppliers"
        db_table_comment = "RFQ 與受邀供應商的獨立狀態"
        constraints = [
            models.UniqueConstraint(fields=["rfq", "supplier"], name="rfq_suppliers_pair_unique"),
            models.CheckConstraint(
                condition=models.Q(responded_at__isnull=True) | models.Q(responded_at__gte=models.F("invited_at")),
                name="rfq_suppliers_response_after_invite",
            ),
        ]
        indexes = [
            models.Index(fields=["supplier", "status", "-invited_at"], name="rfq_supplier_queue_idx"),
        ]


class SupplierQuote(models.Model):
    """受邀供應商針對 RFQ 提交的不可變版本報價。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        SUBMITTED = "submitted", "submitted"
        ACCEPTED_FOR_EVALUATION = "accepted_for_evaluation", "accepted_for_evaluation"
        REVISED = "revised", "revised"
        REJECTED = "rejected", "rejected"
        EXPIRED = "expired", "expired"

    quote_no = models.CharField(max_length=50, db_comment="供應商報價業務單號；不同 revision 共用")
    rfq_supplier = models.ForeignKey(
        RfqSupplier,
        on_delete=models.PROTECT,
        related_name="quotes",
        db_column="rfq_supplier_id",
        db_comment="對應 rfq_suppliers.id，決定 RFQ 與供應商",
    )
    revision = models.PositiveIntegerField(default=1, db_comment="報價修訂版次，從 1 開始")
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_comment="狀態：draft/submitted/accepted_for_evaluation/revised/rejected/expired",
    )
    currency = models.CharField(max_length=3, db_comment="原始報價 ISO 4217 三碼大寫幣別")
    exchange_rate_to_twd = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        db_comment="換算 TWD 的匯率快照，必須大於 0",
    )
    items_subtotal = models.DecimalField(max_digits=14, decimal_places=2, db_comment="原幣品項小計")
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, db_comment="原幣稅額")
    shipping_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, db_comment="原幣運費")
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, db_comment="原幣折扣")
    landed_total_twd = models.DecimalField(max_digits=14, decimal_places=2, db_comment="換算後實際總成本 TWD")
    payment_terms_snapshot = models.TextField(blank=True, db_comment="付款條件快照")
    valid_until = models.DateTimeField(null=True, blank=True, db_comment="報價有效期限")
    submitted_at = models.DateTimeField(null=True, blank=True, db_comment="正式提交時間")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "supplier_quotes"
        db_table_comment = "供應商針對 RFQ 提交的版本化正式報價快照"
        constraints = [
            models.UniqueConstraint(fields=["quote_no", "revision"], name="supplier_quotes_number_revision_unique"),
            models.UniqueConstraint(
                fields=["rfq_supplier", "revision"], name="supplier_quotes_invitation_revision_unique"
            ),
            models.UniqueConstraint(
                fields=["rfq_supplier"],
                condition=models.Q(status__in=["draft", "submitted", "accepted_for_evaluation"]),
                name="supplier_quotes_one_active_invitation",
            ),
            models.CheckConstraint(condition=models.Q(revision__gt=0), name="supplier_quotes_revision_positive"),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="supplier_quotes_currency_format",
            ),
            models.CheckConstraint(
                condition=models.Q(exchange_rate_to_twd__gt=0), name="supplier_quotes_exchange_rate_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(items_subtotal__gte=0)
                & models.Q(tax_amount__gte=0)
                & models.Q(shipping_amount__gte=0)
                & models.Q(discount_amount__gte=0)
                & models.Q(landed_total_twd__gte=0),
                name="supplier_quotes_amounts_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "valid_until"], name="sq_status_valid_idx"),
        ]


class SupplierQuoteItem(models.Model):
    """報價中逐一對應需求明細的商務與規格快照。"""

    supplier_quote = models.ForeignKey(
        SupplierQuote,
        on_delete=models.CASCADE,
        related_name="items",
        db_column="supplier_quote_id",
        db_comment="對應 supplier_quotes.id",
    )
    request_item = models.ForeignKey(
        PurchaseRequestItem,
        on_delete=models.PROTECT,
        related_name="supplier_quote_items",
        db_column="request_item_id",
        db_comment="對應 purchase_request_items.id",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3, db_comment="報價數量，必須大於 0")
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, db_comment="原幣未稅單價")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, db_comment="原幣品項小計")
    lead_time_days = models.PositiveIntegerField(null=True, blank=True, db_comment="交期天數")
    warranty_months = models.PositiveIntegerField(null=True, blank=True, db_comment="保固月數")
    specification_snapshot = models.JSONField(default=dict, db_comment="供應商回覆的規格 JSON object 快照")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "supplier_quote_items"
        db_table_comment = "供應商報價的逐項商務與規格快照"
        constraints = [
            models.UniqueConstraint(
                fields=["supplier_quote", "request_item"], name="supplier_quote_items_request_unique"
            ),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="supplier_quote_items_qty_positive"),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0) & models.Q(subtotal__gte=0),
                name="supplier_quote_items_amounts_nonnegative",
            ),
        ]
    def clean(self):
        super().clean()
        if not isinstance(self.specification_snapshot, dict):
            from django.core.exceptions import ValidationError

            raise ValidationError({"specification_snapshot": "specification_snapshot 必須是 JSON object"})


class QuoteRequirementResult(models.Model):
    """報價明細對需求條件的符合度與例外核准快照。"""

    class Result(models.TextChoices):
        PASS = "pass", "pass"
        FAIL = "fail", "fail"
        NOT_PROVIDED = "not_provided", "not_provided"
        WAIVED = "waived", "waived"

    quote_item = models.ForeignKey(
        SupplierQuoteItem,
        on_delete=models.CASCADE,
        related_name="requirement_results",
        db_column="quote_item_id",
        db_comment="對應 supplier_quote_items.id",
    )
    requirement = models.ForeignKey(
        RequestItemRequirement,
        on_delete=models.PROTECT,
        related_name="quote_results",
        db_column="requirement_id",
        db_comment="對應 request_item_requirements.id",
    )
    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        db_comment="結果：pass/fail/not_provided/waived",
    )
    evidence = models.TextField(blank=True, db_comment="供應商證明或系統比對依據")
    waiver_reason = models.TextField(null=True, blank=True, db_comment="例外採用理由；waived 時必填")
    waived_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="approved_quote_requirement_waivers",
        db_column="waived_by_id",
        null=True,
        blank=True,
        db_comment="例外核准的 users.id；waived 時必填",
    )
    waived_at = models.DateTimeField(null=True, blank=True, db_comment="例外核准時間；waived 時必填")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "quote_requirement_results"
        db_table_comment = "報價明細對必要與偏好條件的符合結果"
        constraints = [
            models.UniqueConstraint(
                fields=["quote_item", "requirement"], name="quote_requirement_results_pair_unique"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        result="waived",
                        waiver_reason__isnull=False,
                        waived_by__isnull=False,
                        waived_at__isnull=False,
                    )
                    & ~models.Q(waiver_reason="")
                )
                | (
                    ~models.Q(result="waived")
                    & models.Q(
                        waiver_reason__isnull=True,
                        waived_by__isnull=True,
                        waived_at__isnull=True,
                    )
                ),
                name="quote_requirement_results_waiver_complete",
            ),
        ]

class RfqScoringCriterion(models.Model):
    """RFQ 發出時固定的評分準則與權重快照。"""

    rfq = models.ForeignKey(
        Rfq,
        on_delete=models.CASCADE,
        related_name="scoring_criteria",
        db_column="rfq_id",
        db_comment="對應 rfqs.id",
    )
    code = models.CharField(max_length=50, db_comment="評分準則代碼")
    label = models.CharField(max_length=100, db_comment="使用者可讀的評分準則名稱")
    weight = models.DecimalField(max_digits=5, decimal_places=2, db_comment="百分比權重，必須大於 0 且不超過 100")
    calculation_method = models.CharField(max_length=50, db_comment="Django 固定計算方法代碼")
    sequence = models.PositiveIntegerField(db_comment="畫面與計算順序，從 1 開始")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "rfq_scoring_criteria"
        db_table_comment = "RFQ 的不可變評分準則與權重快照"
        constraints = [
            models.UniqueConstraint(fields=["rfq", "code"], name="rfq_scoring_criteria_code_unique"),
            models.UniqueConstraint(fields=["rfq", "sequence"], name="rfq_scoring_criteria_sequence_unique"),
            models.CheckConstraint(
                condition=models.Q(weight__gt=0) & models.Q(weight__lte=100),
                name="rfq_scoring_criteria_weight_range",
            ),
            models.CheckConstraint(condition=models.Q(sequence__gt=0), name="rfq_scoring_criteria_sequence_positive"),
        ]


class SupplierQuoteScore(models.Model):
    """Django 固定公式產生的供應商報價評分快照。"""

    supplier_quote = models.ForeignKey(
        SupplierQuote,
        on_delete=models.CASCADE,
        related_name="scores",
        db_column="supplier_quote_id",
        db_comment="對應 supplier_quotes.id",
    )
    criterion = models.ForeignKey(
        RfqScoringCriterion,
        on_delete=models.PROTECT,
        related_name="quote_scores",
        db_column="criterion_id",
        db_comment="對應 rfq_scoring_criteria.id",
    )
    raw_value = models.JSONField(default=dict, db_comment="固定公式使用的原始值快照 JSON object")
    normalized_score = models.DecimalField(max_digits=5, decimal_places=2, db_comment="標準化分數 0 到 100")
    weighted_score = models.DecimalField(max_digits=7, decimal_places=2, db_comment="套用權重後分數 0 到 100")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "supplier_quote_scores"
        db_table_comment = "供應商報價的固定公式評分快照；AI 不得寫入"
        constraints = [
            models.UniqueConstraint(
                fields=["supplier_quote", "criterion"], name="supplier_quote_scores_pair_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(normalized_score__gte=0) & models.Q(normalized_score__lte=100),
                name="supplier_quote_scores_normalized_range",
            ),
            models.CheckConstraint(
                condition=models.Q(weighted_score__gte=0) & models.Q(weighted_score__lte=100),
                name="supplier_quote_scores_weighted_range",
            ),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.raw_value, dict):
            from django.core.exceptions import ValidationError

            raise ValidationError({"raw_value": "raw_value 必須是 JSON object"})


class AwardDecision(models.Model):
    """一次選商方案版本；送出後以新 revision 更正。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        SUBMITTED = "submitted", "submitted"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"
        CANCELLED = "cancelled", "cancelled"

    rfq = models.ForeignKey(
        Rfq, on_delete=models.PROTECT, related_name="award_decisions", db_column="rfq_id",
        db_comment="對應 rfqs.id",
    )
    revision = models.PositiveIntegerField(default=1, db_comment="得標方案版次，從 1 開始")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT,
        db_comment="狀態：draft/submitted/approved/rejected/cancelled",
    )
    recommended_quote = models.ForeignKey(
        SupplierQuote, on_delete=models.PROTECT, related_name="recommended_awards",
        db_column="recommended_quote_id", null=True, blank=True,
        db_comment="系統建議的 supplier_quotes.id；逐項得標時可為 NULL",
    )
    selected_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="selected_awards", db_column="selected_by_id",
        db_comment="建立選商方案的 users.id",
    )
    selection_reason = models.TextField(db_comment="人工選商理由")
    submitted_at = models.DateTimeField(null=True, blank=True, db_comment="送出簽核時間")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "award_decisions"
        db_table_comment = "得標選商方案版本"
        constraints = [
            models.UniqueConstraint(fields=["rfq", "revision"], name="award_decisions_rfq_revision_unique"),
            models.UniqueConstraint(
                fields=["rfq"], condition=models.Q(status__in=["draft", "submitted", "approved"]),
                name="award_decisions_one_active_rfq",
            ),
            models.CheckConstraint(condition=models.Q(revision__gt=0), name="award_decisions_revision_positive"),
            models.CheckConstraint(
                condition=(models.Q(status="draft", submitted_at__isnull=True)
                           | (~models.Q(status="draft") & models.Q(submitted_at__isnull=False))),
                name="award_decisions_submission_time_consistent",
            ),
        ]


class AwardLine(models.Model):
    """得標方案的逐品項供應商與數量分配。"""

    award = models.ForeignKey(
        AwardDecision, on_delete=models.CASCADE, related_name="lines", db_column="award_id",
        db_comment="對應 award_decisions.id",
    )
    request_item = models.ForeignKey(
        PurchaseRequestItem, on_delete=models.PROTECT, related_name="award_lines", db_column="request_item_id",
        db_comment="對應 purchase_request_items.id",
    )
    supplier_quote_item = models.ForeignKey(
        SupplierQuoteItem, on_delete=models.PROTECT, related_name="award_lines",
        db_column="supplier_quote_item_id", db_comment="對應 supplier_quote_items.id",
    )
    awarded_quantity = models.DecimalField(max_digits=14, decimal_places=3, db_comment="得標數量，必須大於 0")
    unit_price_snapshot = models.DecimalField(max_digits=14, decimal_places=2, db_comment="得標時單價快照")
    amount_snapshot = models.DecimalField(max_digits=14, decimal_places=2, db_comment="得標時金額快照")
    reason = models.TextField(blank=True, db_comment="逐項選商或拆量理由")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "award_lines"
        db_table_comment = "得標方案的逐品項與拆量結果"
        constraints = [
            models.UniqueConstraint(
                fields=["award", "supplier_quote_item"], name="award_lines_quote_item_unique"
            ),
            models.CheckConstraint(condition=models.Q(awarded_quantity__gt=0), name="award_lines_qty_positive"),
            models.CheckConstraint(
                condition=models.Q(unit_price_snapshot__gte=0) & models.Q(amount_snapshot__gte=0),
                name="award_lines_amounts_nonnegative",
            ),
        ]


class ApprovalCase(models.Model):
    """針對得標方案建立的簽核案件與政策快照。"""

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        IN_PROGRESS = "in_progress", "in_progress"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"
        CANCELLED = "cancelled", "cancelled"

    award = models.OneToOneField(
        AwardDecision, on_delete=models.PROTECT, related_name="approval_case", db_column="award_id",
        db_comment="對應 award_decisions.id",
    )
    policy = models.ForeignKey(
        ApprovalPolicy, on_delete=models.PROTECT, related_name="approval_cases", db_column="policy_id",
        db_comment="產生案件的 approval_policies.id",
    )
    requester = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="requested_approval_cases", db_column="requester_id",
        db_comment="不得決議本案的原始申請人 users.id",
    )
    policy_snapshot = models.JSONField(default=dict, db_comment="案件建立時的簽核政策 JSON object 快照")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, db_comment="得標後實際總金額")
    currency = models.CharField(max_length=3, db_comment="ISO 4217 三碼大寫幣別")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        db_comment="狀態：pending/in_progress/approved/rejected/cancelled",
    )
    submitted_at = models.DateTimeField(db_comment="簽核案件建立時間")
    decided_at = models.DateTimeField(null=True, blank=True, db_comment="最終決議時間")
    version = models.PositiveIntegerField(default=1, db_comment="樂觀鎖版本，必須大於 0")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "approval_cases"
        db_table_comment = "得標方案的多關簽核案件"
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name="approval_cases_amount_nonnegative"),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="approval_cases_version_positive"),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="approval_cases_currency_format",
            ),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.policy_snapshot, dict):
            from django.core.exceptions import ValidationError
            raise ValidationError({"policy_snapshot": "policy_snapshot 必須是 JSON object"})


class ApprovalStep(models.Model):
    """簽核案件的可認領、可決議關卡快照。"""

    class StepType(models.TextChoices):
        WAIVER_EXCEPTION = "waiver_exception", "waiver_exception"
        AMOUNT_APPROVAL = "amount_approval", "amount_approval"

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        CLAIMED = "claimed", "claimed"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"

    approval_case = models.ForeignKey(
        ApprovalCase, on_delete=models.CASCADE, related_name="steps", db_column="approval_case_id",
        db_comment="對應 approval_cases.id",
    )
    sequence = models.PositiveIntegerField(db_comment="簽核順序，從 1 開始")
    step_type = models.CharField(
        max_length=30,
        choices=StepType.choices,
        default=StepType.AMOUNT_APPROVAL,
        db_comment="關卡類型：waiver_exception/amount_approval",
    )
    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, related_name="approval_steps", db_column="role_id",
        db_comment="可認領此關卡的 roles.id",
    )
    role_snapshot = models.JSONField(default=dict, db_comment="關卡建立時的角色與決議規則 JSON object 快照")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        db_comment="狀態：pending/claimed/approved/rejected",
    )
    claimed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="claimed_approval_steps", db_column="claimed_by_id",
        null=True, blank=True, db_comment="認領人 users.id",
    )
    claimed_at = models.DateTimeField(null=True, blank=True, db_comment="認領時間")
    decided_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="decided_approval_steps", db_column="decided_by_id",
        null=True, blank=True, db_comment="決議人 users.id",
    )
    decided_at = models.DateTimeField(null=True, blank=True, db_comment="決議時間")
    decision_reason = models.TextField(null=True, blank=True, db_comment="核准或駁回理由")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "approval_steps"
        db_table_comment = "簽核案件的角色關卡、認領與決議紀錄"
        constraints = [
            models.UniqueConstraint(fields=["approval_case", "sequence"], name="approval_steps_case_sequence_unique"),
            models.CheckConstraint(condition=models.Q(sequence__gt=0), name="approval_steps_sequence_positive"),
            models.CheckConstraint(
                condition=models.Q(step_type__in=["waiver_exception", "amount_approval"]),
                name="approval_steps_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending", claimed_by__isnull=True, claimed_at__isnull=True,
                             decided_by__isnull=True, decided_at__isnull=True, decision_reason__isnull=True)
                    | (models.Q(status="claimed", claimed_by__isnull=False, claimed_at__isnull=False,
                                decided_by__isnull=True, decided_at__isnull=True, decision_reason__isnull=True))
                    | (models.Q(status__in=["approved", "rejected"], claimed_by__isnull=False,
                                claimed_at__isnull=False, decided_by__isnull=False, decided_at__isnull=False,
                                decision_reason__isnull=False) & ~models.Q(decision_reason=""))
                ),
                name="approval_steps_actor_fields_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=["role", "status", "sequence"], name="approval_step_queue_idx"),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.role_snapshot, dict):
            from django.core.exceptions import ValidationError
            raise ValidationError({"role_snapshot": "role_snapshot 必須是 JSON object"})


class ApprovalStepWaiver(models.Model):
    """例外覆核關卡與必要條件 waiver 的正規化關聯。"""

    id = models.BigAutoField(primary_key=True, db_comment="簽核例外關聯 ID")
    approval_step = models.ForeignKey(
        ApprovalStep,
        on_delete=models.CASCADE,
        related_name="waivers",
        db_column="approval_step_id",
        db_comment="對應 approval_steps.id，僅限 waiver_exception 關卡",
    )
    quote_requirement_result = models.ForeignKey(
        QuoteRequirementResult,
        on_delete=models.PROTECT,
        related_name="approval_step_waivers",
        db_column="quote_requirement_result_id",
        db_comment="對應 quote_requirement_results.id 的已核准 waiver",
    )
    created_at = models.DateTimeField(
        db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）"
    )

    class Meta:
        db_table = "approval_step_waivers"
        db_table_comment = "簽核例外關卡與必要條件 waiver 的對照"
        constraints = [
            models.UniqueConstraint(
                fields=["approval_step", "quote_requirement_result"],
                name="approval_step_waivers_pair_unique",
            ),
        ]


class PurchaseOrder(models.Model):
    """核准後依得標供應商拆分的正式採購單。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        ISSUED = "issued", "issued"
        PARTIALLY_RECEIVED = "partially_received", "partially_received"
        RECEIVED = "received", "received"
        CLOSED = "closed", "closed"
        CANCELLED = "cancelled", "cancelled"

    po_no = models.CharField(max_length=50, unique=True, db_comment="採購單唯一單號")
    award = models.ForeignKey(
        AwardDecision, on_delete=models.PROTECT, related_name="purchase_orders", db_column="award_id",
        db_comment="對應 award_decisions.id",
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="purchase_orders", db_column="supplier_id",
        db_comment="得標供應商 suppliers.id",
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.DRAFT,
        db_comment="狀態：draft/issued/partially_received/received/closed/cancelled",
    )
    currency = models.CharField(max_length=3, db_comment="ISO 4217 三碼大寫幣別")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, db_comment="採購單總金額快照")
    issued_at = models.DateTimeField(null=True, blank=True, db_comment="發單時間")
    closed_at = models.DateTimeField(null=True, blank=True, db_comment="結案時間")
    cancelled_at = models.DateTimeField(null=True, blank=True, db_comment="取消時間")
    version = models.PositiveIntegerField(default=1, db_comment="樂觀鎖版本，必須大於 0")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")
    updated_at = models.DateTimeField(db_default=Now(), db_comment="最後更新時間（由資料庫 trigger 維護）")

    class Meta:
        db_table = "purchase_orders"
        db_table_comment = "得標核准後依供應商拆分的正式採購單"
        constraints = [
            models.UniqueConstraint(fields=["award", "supplier"], name="purchase_orders_award_supplier_unique"),
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name="purchase_orders_amount_nonnegative"),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="purchase_orders_version_positive"),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="purchase_orders_currency_format",
            ),
        ]
        indexes = [
            models.Index(fields=["supplier", "status"], name="po_supplier_status_idx"),
        ]


class PurchaseOrderItem(models.Model):
    """採購單逐項不可變的品項、規格與價格快照。"""

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="items", db_column="purchase_order_id",
        db_comment="對應 purchase_orders.id",
    )
    award_line = models.OneToOneField(
        AwardLine, on_delete=models.PROTECT, related_name="purchase_order_item", db_column="award_line_id",
        db_comment="對應 award_lines.id",
    )
    line_no = models.PositiveIntegerField(db_comment="採購單內行號，從 1 開始")
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="purchase_order_items", db_column="product_id",
        null=True, blank=True, db_comment="對應 products.id；同時保留名稱與規格快照",
    )
    product_name_snapshot = models.TextField(db_comment="正式下單時的品項名稱快照")
    specification_snapshot = models.JSONField(default=dict, db_comment="正式下單時的規格 JSON object 快照")
    ordered_quantity = models.DecimalField(max_digits=14, decimal_places=3, db_comment="訂購數量，必須大於 0")
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, db_comment="正式下單單價快照")
    amount = models.DecimalField(max_digits=14, decimal_places=2, db_comment="正式下單金額快照")
    created_at = models.DateTimeField(db_default=Now(), editable=False, db_comment="建立時間（由資料庫產生）")

    class Meta:
        db_table = "purchase_order_items"
        db_table_comment = "正式採購單品項、規格、價格與數量快照"
        constraints = [
            models.UniqueConstraint(fields=["purchase_order", "line_no"], name="purchase_order_items_line_unique"),
            models.CheckConstraint(condition=models.Q(line_no__gt=0), name="purchase_order_items_line_positive"),
            models.CheckConstraint(
                condition=models.Q(ordered_quantity__gt=0),
                name="purchase_order_items_qty_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0) & models.Q(amount__gte=0),
                name="purchase_order_items_amounts_nonnegative",
            ),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.specification_snapshot, dict):
            from django.core.exceptions import ValidationError
            raise ValidationError({"specification_snapshot": "specification_snapshot 必須是 JSON object"})


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
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="本次單價與該供應商+產品歷史已核准均價的偏離百分比；null＝過去無已核准紀錄可比較",
    )
    source_suggestion = models.ForeignKey(
        PurchaseSuggestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
        db_column="source_suggestion_id",
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
        CANCELLED = "cancelled", "cancelled"

    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="approvals", db_column="quote_id")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="approvals", db_column="role_id")
    approver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handled_approvals",
        db_column="approver_id",
        help_text="實際認領/決議的使用者；認領前為 null",
    )
    approval_level = models.CharField(max_length=10, choices=Level.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "approvals"
        constraints = [
            models.UniqueConstraint(fields=["quote"], name="approvals_quote_unique"),
        ]

    def __str__(self):
        return f"Approval#{self.pk} quote={self.quote_id} ({self.status})"
