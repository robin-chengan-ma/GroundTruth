from rest_framework import serializers

from apps.audit.models import AuditLog, ManualReviewQueue


class ManualReviewQueueSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    claimant_name = serializers.CharField(source="user.name", read_only=True)
    class Meta:
        model = ManualReviewQueue
        fields = [
            "id", "quote", "review_type", "ai_generated_text", "expected_value",
            "supplier", "raw_input_text", "requester", "status", "user", "decision",
            "created_at", "updated_at", "supplier_name", "claimant_name",
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "action_type", "masked_payload", "real_query_summary",
            "verification_result", "quote", "created_at",
        ]
