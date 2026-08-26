from rest_framework import serializers

from apps.crm.models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "tier", "created_at"]
