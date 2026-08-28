from rest_framework import serializers

from apps.procurement.models import Approval, Quote


class QuoteSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Quote
        fields = [
            "id", "user", "supplier", "product", "quantity", "price",
            "total_amount", "currency", "ai_summary_text", "status",
            "price_deviation_pct", "source_suggestion", "created_at",
            "user_name", "supplier_name", "product_name",
        ]


class ApprovalSerializer(serializers.ModelSerializer):
    role_code = serializers.CharField(source="role.role", read_only=True)
    approver_name = serializers.CharField(source="approver.name", read_only=True)
    quote_detail = QuoteSerializer(source="quote", read_only=True)

    class Meta:
        model = Approval
        fields = [
            "id", "quote", "role", "approver", "approval_level",
            "status", "created_at", "updated_at", "role_code", "approver_name", "quote_detail",
        ]
