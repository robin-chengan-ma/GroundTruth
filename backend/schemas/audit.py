from rest_framework import serializers

from apps.audit.models import AuditLog, ManualReviewQueue


class ManualReviewQueueSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    claimant_name = serializers.CharField(source="user.name", read_only=True)
    copied_to_request_no = serializers.SerializerMethodField()

    class Meta:
        model = ManualReviewQueue
        fields = [
            "id", "quote", "review_type", "ai_generated_text", "expected_value",
            "supplier", "raw_input_text", "requester", "status", "user", "decision",
            "rejection_reason", "resume_status", "resume_error_code", "created_purchase_request",
            "copied_to_request_no", "created_at", "updated_at", "supplier_name", "claimant_name",
        ]

    def get_copied_to_request_no(self, obj):
        """此案件是否已經被複製並重新編輯成新草稿（Robin 2026-09-03 決策：同一案件只能
        複製一次，前端靠這個欄位判斷「複製並重新編輯」按鈕要不要顯示）。"""
        copy = obj.copies.first()
        return copy.request_no if copy else None


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "action_type", "masked_payload", "real_query_summary",
            "verification_result", "quote", "created_at",
        ]
