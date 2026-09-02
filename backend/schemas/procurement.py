from rest_framework import serializers

from apps.procurement.models import (
    Approval,
    PurchaseRequest,
    PurchaseRequestItem,
    Quote,
    QuoteRequirementResult,
    Rfq,
    SupplierPriceVersion,
    SupplierProduct,
    SupplierQuote,
    SupplierQuoteItem,
)


class SupplierPriceVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.name", read_only=True)

    class Meta:
        model = SupplierPriceVersion
        fields = [
            "id", "supplier_product", "unit_price", "currency", "minimum_quantity",
            "valid_from", "valid_until", "created_by", "created_by_name", "created_at",
        ]
        read_only_fields = ["id", "supplier_product", "created_by", "created_by_name", "created_at"]


class SupplierProductSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    price_versions = SupplierPriceVersionSerializer(many=True, read_only=True)

    class Meta:
        model = SupplierProduct
        fields = [
            "id", "supplier", "supplier_name", "product", "product_name", "supplier_sku",
            "lead_time_days", "minimum_order_quantity", "quality_status", "is_active",
            "price_versions", "created_at", "updated_at",
        ]


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


class PurchaseRequestItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    specifications = serializers.JSONField(source="specification_snapshot", read_only=True)

    class Meta:
        model = PurchaseRequestItem
        fields = [
            "id",
            "line_no",
            "product_id",
            "product_name",
            "description_snapshot",
            "specifications",
            "quantity",
            "unit_of_measure",
        ]


class PurchaseRequestDraftSerializer(serializers.ModelSerializer):
    items = PurchaseRequestItemSerializer(many=True, read_only=True)
    candidate_suppliers = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequest
        fields = [
            "id",
            "request_no",
            "status",
            "purpose",
            "needed_by",
            "currency",
            "source",
            "version",
            "items",
            "candidate_suppliers",
            "created_at",
            "updated_at",
        ]

    def get_candidate_suppliers(self, obj):
        rfq = next((candidate for candidate in obj.rfqs.all() if candidate.status == "draft"), None)
        if rfq is None:
            return []
        return [
            {"supplier_id": invitation.supplier_id, "supplier_name": invitation.supplier.name}
            for invitation in rfq.invited_suppliers.all()
        ]


class PurchaseRequestListSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(source="requester.name", read_only=True)
    item_summary = serializers.SerializerMethodField()
    supplier_summary = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequest
        fields = [
            "id", "request_no", "purpose", "requester_name", "status", "currency",
            "item_summary", "supplier_summary", "created_at", "updated_at",
        ]

    def get_item_summary(self, obj):
        items = list(obj.items.all())
        if not items:
            return "—"
        first = items[0].product.name if items[0].product else items[0].description_snapshot
        return first if len(items) == 1 else f"{first}等 {len(items)} 項"

    def get_supplier_summary(self, obj):
        names = []
        for rfq in obj.rfqs.all():
            for invitation in rfq.invited_suppliers.all():
                if invitation.supplier.name not in names:
                    names.append(invitation.supplier.name)
        if not names:
            return "—"
        return names[0] if len(names) == 1 else f"{names[0]}等 {len(names)} 間"


class PurchaseRequestDetailSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(source="requester.name", read_only=True)
    items = PurchaseRequestItemSerializer(many=True, read_only=True)
    candidate_suppliers = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequest
        fields = [
            "id",
            "request_no",
            "status",
            "purpose",
            "needed_by",
            "currency",
            "source",
            "requester_name",
            "items",
            "candidate_suppliers",
            "created_at",
            "updated_at",
        ]

    def get_candidate_suppliers(self, obj):
        suppliers = {}
        for rfq in obj.rfqs.all():
            for invitation in rfq.invited_suppliers.all():
                suppliers[invitation.supplier_id] = invitation.supplier.name
        return [
            {"supplier_id": supplier_id, "supplier_name": name}
            for supplier_id, name in suppliers.items()
        ]


class RfqSerializer(serializers.ModelSerializer):
    request_id = serializers.IntegerField(source="request.id", read_only=True)
    supplier_ids = serializers.SerializerMethodField()
    criteria = serializers.SerializerMethodField()

    class Meta:
        model = Rfq
        fields = [
            "id", "rfq_no", "request_id", "revision", "status", "response_due_at",
            "rule_snapshot", "version", "supplier_ids", "criteria", "created_at", "updated_at",
        ]

    def get_supplier_ids(self, obj):
        return list(obj.invited_suppliers.values_list("supplier_id", flat=True))

    def get_criteria(self, obj):
        return [
            {
                "code": criterion.code,
                "label": criterion.label,
                "weight": f"{criterion.weight:.2f}",
                "calculation_method": criterion.calculation_method,
                "sequence": criterion.sequence,
            }
            for criterion in obj.scoring_criteria.all().order_by("sequence")
        ]


class SupplierQuoteItemSerializer(serializers.ModelSerializer):
    request_item_id = serializers.IntegerField(source="request_item.id", read_only=True)
    specifications = serializers.JSONField(source="specification_snapshot", read_only=True)

    class Meta:
        model = SupplierQuoteItem
        fields = [
            "id", "request_item_id", "quantity", "unit_price", "subtotal",
            "lead_time_days", "warranty_months", "specifications",
        ]


class SupplierQuoteSerializer(serializers.ModelSerializer):
    items = SupplierQuoteItemSerializer(many=True, read_only=True)
    supplier_id = serializers.IntegerField(source="rfq_supplier.supplier_id", read_only=True)
    supplier_name = serializers.CharField(source="rfq_supplier.supplier.name", read_only=True)
    rfq_id = serializers.IntegerField(source="rfq_supplier.rfq_id", read_only=True)

    class Meta:
        model = SupplierQuote
        fields = [
            "id", "quote_no", "rfq_id", "supplier_id", "supplier_name", "revision", "status",
            "currency", "exchange_rate_to_twd", "items_subtotal", "tax_amount", "shipping_amount",
            "discount_amount", "landed_total_twd", "payment_terms_snapshot", "valid_until",
            "submitted_at", "items", "created_at",
        ]


class QuoteRequirementResultSerializer(serializers.ModelSerializer):
    requirement_code = serializers.CharField(source="requirement.code", read_only=True)
    requirement_label = serializers.CharField(source="requirement.label", read_only=True)
    waived_by_name = serializers.CharField(source="waived_by.name", read_only=True)

    class Meta:
        model = QuoteRequirementResult
        fields = [
            "id", "quote_item", "requirement", "requirement_code", "requirement_label",
            "result", "evidence", "waiver_reason", "waived_by", "waived_by_name", "waived_at",
        ]
