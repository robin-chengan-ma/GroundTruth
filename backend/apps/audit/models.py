from django.db import models

from apps.core.models import User
from apps.crm.models import Supplier
from apps.procurement.models import PurchaseRequest, Quote


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

    class ResumeStatus(models.TextChoices):
        """supplier_fuzzy_match 案件核准後，Django 直接續傳解析的持久化狀態
        （2026-09-02 新增，見 docs/ADR/discuss/main-flow.md）。非此案件類型或尚未核准
        時維持 not_applicable；核准當下先進 pending，續傳處理完成後才落地
        succeeded／failed，管理員可依 failed 狀態呼叫 retry-resume 重試。"""
        NOT_APPLICABLE = "not_applicable", "not_applicable"
        PENDING = "pending", "pending"
        SUCCEEDED = "succeeded", "succeeded"
        FAILED = "failed", "failed"

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
        help_text="模糊比對案件：原始詢價發起人，核准後 Django 直接續傳解析時用來建立採購需求草稿",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNCLAIMED)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="claimed_review_entries", db_column="user_id",
        help_text="認領/處理的管理員",
    )
    decision = models.CharField(max_length=20, choices=Decision.choices, null=True, blank=True)
    resume_status = models.CharField(
        max_length=20, choices=ResumeStatus.choices, default=ResumeStatus.NOT_APPLICABLE,
        help_text="supplier_fuzzy_match 案件核准後續傳解析的持久化狀態，可依 failed 重試",
    )
    resume_error_code = models.CharField(
        max_length=40, null=True, blank=True,
        help_text="resume_status=failed 時的非敏感錯誤代碼；不落地原始例外訊息或供應商名稱",
    )
    created_purchase_request = models.ForeignKey(
        PurchaseRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="resumed_from_reviews", db_column="created_purchase_request_id",
        help_text="resume_status=succeeded 時續傳流程自動建立的採購需求草稿",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "manual_review_queue"
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(resume_status="succeeded")
                    | models.Q(created_purchase_request__isnull=False)
                ),
                name="manual_review_queue_resume_succeeded_has_purchase_request",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(resume_status="failed")
                    | models.Q(resume_error_code__isnull=False)
                ),
                name="manual_review_queue_resume_failed_has_error_code",
            ),
        ]

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
