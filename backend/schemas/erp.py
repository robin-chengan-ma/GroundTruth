from rest_framework import serializers

from apps.erp.models import (
    Inventory,
    InventoryBalance,
    InventoryMovement,
    Product,
    ProductCategory,
    PurchaseSuggestion,
)


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "code", "name", "spec_schema", "is_active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta:
        model = Product
        fields = [
            "id", "name", "category", "category_name", "sku", "description",
            "specifications", "unit_of_measure", "is_active", "price", "currency", "updated_at",
        ]
        read_only_fields = ["updated_at"]


class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = ["id", "product", "stock_qty", "threshold"]


class InventoryBalanceSerializer(serializers.ModelSerializer):
    """FR-10a：庫存位置＝on_hand - reserved + in_transit；threshold 沿用 Phase 1 Inventory
    主檔（低於此值時 purchase_suggestion_service 觸發採購建議），舊資料未建檔時回傳 null。"""

    product_name = serializers.CharField(source="product.name", read_only=True)
    threshold = serializers.SerializerMethodField()
    available_quantity = serializers.SerializerMethodField()

    class Meta:
        model = InventoryBalance
        fields = [
            "product", "product_name", "on_hand_quantity", "reserved_quantity",
            "in_transit_quantity", "available_quantity", "threshold", "version", "updated_at",
        ]

    def get_threshold(self, obj):
        legacy = getattr(obj.product, "inventory", None)
        return legacy.threshold if legacy else None

    def get_available_quantity(self, obj):
        return str(obj.on_hand_quantity - obj.reserved_quantity + obj.in_transit_quantity)


class InventoryMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    posted_by_name = serializers.CharField(source="posted_by.name", read_only=True, default=None)

    class Meta:
        model = InventoryMovement
        fields = [
            "id", "product", "product_name", "movement_type", "quantity_delta",
            "reference_type", "reference_id", "affects_balance", "reason",
            "posted_at", "posted_by", "posted_by_name", "created_at",
        ]


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
