from rest_framework import serializers

from apps.erp.models import Inventory, Product, PurchaseSuggestion


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "price", "currency"]


class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = ["id", "product", "stock_qty", "threshold"]


class PurchaseSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseSuggestion
        fields = [
            "id",
            "product",
            "suggested_qty",
            "status",
            "source_movement",
            "purchase_request",
            "created_at",
        ]
