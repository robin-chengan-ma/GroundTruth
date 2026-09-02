from rest_framework import serializers

from apps.crm.models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id", "name", "tier", "code", "status", "tax_id", "contact",
            "payment_terms", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
