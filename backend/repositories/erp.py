from django.db.models import Sum

from apps.erp.models import (
    GoodsReceipt,
    InspectionVarianceCase,
    InspectionVarianceLine,
    Inventory,
    InventoryBalance,
    InventoryMovement,
    Product,
    PurchaseSuggestion,
    QualityInspection,
)


class ProductRepository:
    model = Product

    @staticmethod
    def all():
        return Product.objects.order_by("id")

    @staticmethod
    def get(pk):
        return Product.objects.get(pk=pk)


class InventoryRepository:
    model = Inventory

    @staticmethod
    def all():
        return Inventory.objects.select_related("product").order_by("id")

    @staticmethod
    def get(pk):
        return Inventory.objects.select_related("product").get(pk=pk)

    @staticmethod
    def below_threshold():
        from django.db.models import F

        return Inventory.objects.filter(stock_qty__lt=F("threshold"))


class PurchaseSuggestionRepository:
    model = PurchaseSuggestion

    @staticmethod
    def all():
        return PurchaseSuggestion.objects.select_related(
            "product", "source_movement", "purchase_request"
        ).order_by("id")

    @staticmethod
    def get_for_update(pk):
        return PurchaseSuggestion.objects.select_for_update(of=("self",)).select_related(
            "product", "source_movement", "purchase_request"
        ).get(pk=pk)

    @staticmethod
    def has_unfinished_for_product(product_id) -> bool:
        return PurchaseSuggestion.objects.filter(
            product_id=product_id,
            status__in=[
                PurchaseSuggestion.Status.PENDING,
                PurchaseSuggestion.Status.IN_PROGRESS,
            ],
        ).exists()

    @staticmethod
    def create(**fields):
        return PurchaseSuggestion.objects.create(**fields)

    @staticmethod
    def pending_for_requests(request_ids):
        return PurchaseSuggestion.objects.filter(
            purchase_request_id__in=request_ids,
            status=PurchaseSuggestion.Status.PENDING,
        )

    @staticmethod
    def in_progress_for_request(request_id):
        return PurchaseSuggestion.objects.filter(
            purchase_request_id=request_id,
            status=PurchaseSuggestion.Status.IN_PROGRESS,
        )

    has_pending_for_product = has_unfinished_for_product


class GoodsReceiptRepository:
    @staticmethod
    def get(pk):
        return (
            GoodsReceipt.objects.select_related(
                "purchase_order__award__rfq__request__requester",
                "purchase_order__supplier",
                "received_by",
            )
            .prefetch_related("items__purchase_order_item__product", "items__quality_inspection")
            .get(pk=pk)
        )

    @staticmethod
    def get_for_update(pk):
        return (
            GoodsReceipt.objects.select_for_update(of=("self",))
            .select_related("purchase_order__award__rfq__request", "received_by")
            .prefetch_related("items__purchase_order_item__product", "items__quality_inspection")
            .get(pk=pk)
        )

    @staticmethod
    def accessible(*, user_id, can_read_all):
        queryset = GoodsReceipt.objects.select_related(
            "purchase_order__award__rfq__request__requester",
            "purchase_order__supplier",
            "received_by",
        ).prefetch_related("items__purchase_order_item__product", "items__quality_inspection")
        if not can_read_all:
            queryset = queryset.filter(
                purchase_order__award__rfq__request__requester_id=user_id
            )
        return queryset.order_by("-created_at", "-id")

    @staticmethod
    def next_sequence_for_purchase_order(purchase_order_id):
        return GoodsReceipt.objects.filter(purchase_order_id=purchase_order_id).count() + 1


class InventoryBalanceRepository:
    @staticmethod
    def get_or_create_for_update(product_id):
        balance, _ = InventoryBalance.objects.get_or_create(product_id=product_id)
        return InventoryBalance.objects.select_for_update().get(product_id=balance.product_id)

    @staticmethod
    def all():
        return InventoryBalance.objects.select_related("product", "product__inventory").order_by(
            "product_id"
        )


class InventoryMovementQueryRepository:
    @staticmethod
    def all():
        return InventoryMovement.objects.select_related("product", "posted_by").order_by(
            "-posted_at", "-id"
        )


class QualityInspectionRepository:
    @staticmethod
    def create(**fields):
        return QualityInspection.objects.create(**fields)

    @staticmethod
    def get(pk):
        return QualityInspection.objects.select_related(
            "receipt_item__purchase_order_item__purchase_order__supplier",
            "receipt_item__purchase_order_item__product",
            "receipt_item__receipt__purchase_order__award__rfq__request__requester",
        ).get(pk=pk)


class InspectionVarianceRepository:
    @staticmethod
    def _queryset():
        return InspectionVarianceCase.objects.select_related(
            "quality_inspection__receipt_item__purchase_order_item__product",
            "quality_inspection__receipt_item__receipt__purchase_order__supplier",
            "quality_inspection__receipt_item__receipt__purchase_order__award__rfq__request__requester",
            "created_by",
            "submitted_by",
            "closed_by",
        ).prefetch_related("lines__completed_by")

    @classmethod
    def get(cls, pk):
        return cls._queryset().get(pk=pk)

    @classmethod
    def get_for_update(cls, pk):
        return cls._queryset().select_for_update(of=("self",)).get(pk=pk)

    @classmethod
    def all(cls):
        return cls._queryset().order_by("-created_at", "-id")

    @staticmethod
    def create_case(**fields):
        return InspectionVarianceCase.objects.create(**fields)

    @staticmethod
    def create_line(**fields):
        return InspectionVarianceLine.objects.create(**fields)

    @staticmethod
    def delete_lines(variance_case):
        variance_case.lines.all().delete()

    @staticmethod
    def get_line_for_update(variance_case_id, line_id):
        return (
            InspectionVarianceLine.objects.select_for_update()
            .select_related("variance_case")
            .get(pk=line_id, variance_case_id=variance_case_id)
        )

    @staticmethod
    def accepted_replacement_quantity(line_id):
        return (
            QualityInspection.objects.filter(
                receipt_item__replacement_variance_line_id=line_id
            ).aggregate(total=Sum("accepted_quantity"))["total"]
            or 0
        )

    @staticmethod
    def accepted_quantity_for_order_item(order_item_id):
        return (
            QualityInspection.objects.filter(
                receipt_item__purchase_order_item_id=order_item_id
            ).aggregate(total=Sum("accepted_quantity"))["total"]
            or 0
        )

    @staticmethod
    def has_inspection_for_order_item(order_item_id):
        return QualityInspection.objects.filter(
            receipt_item__purchase_order_item_id=order_item_id
        ).exists()

    @staticmethod
    def commercially_resolved_quantity_for_order_item(order_item_id):
        return (
            InspectionVarianceLine.objects.filter(
                variance_case__quality_inspection__receipt_item__purchase_order_item_id=order_item_id,
                status=InspectionVarianceLine.Status.COMPLETED,
                action_type__in=[
                    InspectionVarianceLine.ActionType.RETURN,
                    InspectionVarianceLine.ActionType.CREDIT,
                    InspectionVarianceLine.ActionType.WAIVE,
                ],
            ).aggregate(total=Sum("quantity"))["total"]
            or 0
        )


class InventoryMovementRepository:
    @staticmethod
    def create(**fields):
        return InventoryMovement.objects.create(**fields)
