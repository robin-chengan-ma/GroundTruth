from rest_framework import serializers

from apps.procurement.models import Approval, Quote


class QuoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quote
        fields = [
            "id", "user", "supplier", "product", "quantity", "price",
            "total_amount", "currency", "ai_summary_text", "status",
            "price_deviation_pct", "source_suggestion", "created_at",
        ]


class ApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Approval
        fields = [
            "id", "quote", "role", "approver", "approval_level",
            "status", "created_at", "updated_at",
        ]
