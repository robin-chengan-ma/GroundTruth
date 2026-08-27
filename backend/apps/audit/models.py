from django.db import models

from apps.core.models import User
from apps.crm.models import Supplier
from apps.procurement.models import Quote


class ManualReviewQueue(models.Model):
    class ReviewType(models.TextChoices):
        HALLUCINATION_MISMATCH = "hallucination_mismatch", "hallucination_mismatch"
        SUPPLIER_FUZZY_MATCH = "supplier_fuzzy_match", "supplier_fuzzy_match"

    class Status(models.TextChoices):
        UNCLAIMED = "unclaimed", "unclaimed"
        CLAIMED = "claimed", "claimed"
        RESOLVED = "resolved", "resolved"

    class Decision(models.TextChoices):
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"

    quote = models.ForeignKey(
        Quote, on_delete=models.CASCADE, null=True, blank=True,
        related_name="review_entries", db_column="quote_id",
        help_text="supplier_fuzzy_match 案件在 Mask 階段建立，尚無 Quote，此欄位為 null",
    )
    review_type = models.CharField(max_length=30, choices=ReviewType.choices)
    ai_generated_text = models.TextField(null=True, blank=True, help_text="幻覺案件用")
    expected_value = models.TextField(null=True, blank=True, help_text="原始真實數字（JSON），幻覺案件用")
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fuzzy_review_entries", db_column="supplier_id",
        help_text="模糊比對案件：系統疑似比對到的供應商",
    )
    raw_input_text = models.TextField(null=True, blank=True, help_text="模糊比對案件：使用者原始輸入")
    requester = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="requested_review_entries", db_column="requester_user_id",
        help_text="模糊比對案件：原始詢價發起人，核准後交還 n8n 重新觸發流程時要用來建立 Quote",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNCLAIMED)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="claimed_review_entries", db_column="user_id",
        help_text="認領/處理的管理員",
    )
    decision = models.CharField(max_length=20, choices=Decision.choices, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "manual_review_queue"

    def __str__(self):
        return f"Review#{self.pk} quote={self.quote_id} ({self.status})"


class AuditLog(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_logs", db_column="user_id",
        help_text="觸發者；系統自動觸發時為 null",
    )
    action_type = models.CharField(max_length=50, help_text="例如 llm_parse／hallucination_check／review_decision")
    masked_payload = models.TextField(null=True, blank=True, help_text="送往 LLM 的脫敏內容")
    real_query_summary = models.TextField(null=True, blank=True, help_text="查了哪張表的摘要")
    verification_result = models.CharField(max_length=10, null=True, blank=True, help_text="pass／fail／n/a")
    quote = models.ForeignKey(
        Quote, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_logs", db_column="quote_id",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"

    def __str__(self):
        return f"AuditLog#{self.pk} {self.action_type}"
