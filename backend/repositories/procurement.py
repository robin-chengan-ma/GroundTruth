from django.db.models import Avg, Q
from django.utils import timezone

from apps.crm.models import Supplier
from apps.erp.models import Product
from apps.procurement.models import (
    Approval,
    ApprovalCase,
    ApprovalPolicy,
    ApprovalStep,
    AwardDecision,
    PurchaseOrder,
    PurchaseRequest,
    Quote,
    QuoteRequirementResult,
    Rfq,
    RfqSupplier,
    SupplierPriceVersion,
    SupplierProduct,
    SupplierQuote,
    SupplierQuoteItem,
)


class QuoteRepository:
    model = Quote

    @staticmethod
    def all():
        return Quote.objects.select_related("user", "supplier", "product").order_by("id")

    @staticmethod
    def get(pk):
        return Quote.objects.select_related("user", "supplier", "product").get(pk=pk)

    @staticmethod
    def approved_history(supplier_id, product_id):
        """供 FR-4a 歷史均價比對使用。"""
        return Quote.objects.filter(
            supplier_id=supplier_id, product_id=product_id, status=Quote.Status.APPROVED
        )


class ApprovalRepository:
    model = Approval

    @staticmethod
    def all():
        return Approval.objects.select_related("quote", "role", "approver").order_by("id")

    @staticmethod
    def unclaimed_for_role(role_id):
        return Approval.objects.filter(
            role_id=role_id, approver__isnull=True, status=Approval.Status.PENDING
        )


class ApprovalPolicyRepository:
    @staticmethod
    def matching(*, amount, currency, at=None):
        at = at or timezone.now()
        return (
            ApprovalPolicy.objects.prefetch_related("steps__role")
            .filter(
                currency=currency.upper(),
                is_active=True,
                min_amount__lte=amount,
                active_from__lte=at,
            )
            .filter(Q(max_amount__isnull=True) | Q(max_amount__gt=amount))
            .filter(Q(active_until__isnull=True) | Q(active_until__gt=at))
            .order_by("-active_from", "id")
        )


class ApprovalCaseRepository:
    @staticmethod
    def get(pk):
        return (
            ApprovalCase.objects.select_related(
                "award__rfq__request__requester",
                "policy",
                "requester",
            )
            .prefetch_related(
                "steps__role",
                "steps__claimed_by",
                "steps__decided_by",
                "steps__waivers__quote_requirement_result__requirement",
            )
            .get(pk=pk)
        )

    @staticmethod
    def accessible(*, role_ids, audit_all=False):
        queryset = ApprovalCase.objects.select_related(
            "award__rfq__request", "policy", "requester"
        ).prefetch_related("steps__role", "steps__claimed_by", "steps__decided_by")
        if not audit_all:
            queryset = queryset.filter(steps__role_id__in=role_ids)
        return queryset.distinct().order_by("-submitted_at", "-id")

    @staticmethod
    def step_for_update(pk):
        return (
            ApprovalStep.objects.select_for_update(of=("self",))
            .select_related(
                "approval_case__award__rfq__request",
                "approval_case__requester",
                "role",
                "claimed_by",
                "decided_by",
            )
            .prefetch_related("waivers__quote_requirement_result")
            .get(pk=pk)
        )


class PurchaseOrderRepository:
    @staticmethod
    def get(pk):
        return (
            PurchaseOrder.objects.select_related(
                "award__rfq__request__requester", "supplier"
            )
            .prefetch_related("items__product", "items__award_line__request_item")
            .get(pk=pk)
        )

    @staticmethod
    def get_for_update(pk):
        return (
            PurchaseOrder.objects.select_for_update()
            .select_related("award__rfq__request", "supplier")
            .prefetch_related("items__product", "items__award_line__request_item")
            .get(pk=pk)
        )

    @staticmethod
    def for_award_for_update(award_id):
        return list(
            PurchaseOrder.objects.select_for_update()
            .filter(award_id=award_id)
            .select_related("supplier")
            .prefetch_related("items")
            .order_by("supplier_id")
        )

    @staticmethod
    def accessible(*, user_id, can_read_all):
        queryset = PurchaseOrder.objects.select_related(
            "award__rfq__request__requester", "supplier"
        ).prefetch_related("items__product", "items__award_line__request_item")
        if not can_read_all:
            queryset = queryset.filter(award__rfq__request__requester_id=user_id)
        return queryset.order_by("-created_at", "-id")

    @staticmethod
    def statuses_for_request_for_update(request_id):
        return list(
            PurchaseOrder.objects.select_for_update()
            .filter(award__rfq__request_id=request_id)
            .values_list("status", flat=True)
        )

class PurchaseRequestRepository:
    @staticmethod
    def active_suppliers(ids):
        return Supplier.objects.filter(id__in=ids, is_active=True)

    @staticmethod
    def active_products(ids):
        return Product.objects.filter(id__in=ids, is_active=True)

    @staticmethod
    def owned(user_id, *, search=None, status=None):
        queryset = (
            PurchaseRequest.objects.filter(requester_id=user_id)
            .select_related("requester")
            .prefetch_related("items__product", "rfqs__invited_suppliers__supplier")
        )
        if search:
            queryset = queryset.filter(
                Q(request_no__icontains=search)
                | Q(purpose__icontains=search)
                | Q(items__product__name__icontains=search)
                | Q(rfqs__invited_suppliers__supplier__name__icontains=search)
            )
        if status:
            queryset = queryset.filter(status=status)
        return queryset.distinct().order_by("-created_at", "-id")

    @staticmethod
    def owned_drafts(user_id):
        return (
            PurchaseRequest.objects.filter(
                requester_id=user_id,
                status=PurchaseRequest.Status.DRAFT,
            )
            .prefetch_related("items__product", "rfqs__invited_suppliers__supplier")
            .order_by("-updated_at", "-id")
        )

    @staticmethod
    def get_owned_draft(pk, user_id, *, for_update=False):
        queryset = PurchaseRequest.objects.filter(
            pk=pk,
            requester_id=user_id,
            status=PurchaseRequest.Status.DRAFT,
        )
        if for_update:
            queryset = queryset.select_for_update()
        return queryset.get()

    @staticmethod
    def get_owned(pk, user_id, *, for_update=False):
        queryset = PurchaseRequest.objects.filter(pk=pk, requester_id=user_id)
        if for_update:
            queryset = queryset.select_for_update()
        return queryset.get()

    @staticmethod
    def active_price(*, supplier_id, product_id, quantity, currency, at=None):
        at = at or timezone.now()
        return (
            SupplierPriceVersion.objects.select_related("supplier_product")
            .filter(
                supplier_product__supplier_id=supplier_id,
                supplier_product__product_id=product_id,
                supplier_product__is_active=True,
                supplier_product__quality_status__in=["qualified", "conditional"],
                currency=currency,
                minimum_quantity__lte=quantity,
                valid_from__lte=at,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=at))
            .order_by("-minimum_quantity", "-valid_from", "-id")
            .first()
        )

    @staticmethod
    def supplier_product(*, supplier_id, product_id):
        return (
            SupplierProduct.objects.select_related("supplier", "product")
            .filter(supplier_id=supplier_id, product_id=product_id)
            .first()
        )

    @staticmethod
    def historical_average_price(*, supplier_id, product_id, currency):
        from apps.procurement.models import PurchaseOrderItem

        return PurchaseOrderItem.objects.filter(
            purchase_order__supplier_id=supplier_id,
            purchase_order__currency=currency,
            purchase_order__status__in=["issued", "partially_received", "received", "closed"],
            product_id=product_id,
        ).aggregate(value=Avg("unit_price"))["value"]


class SupplierProductRepository:
    @staticmethod
    def all():
        return (
            SupplierProduct.objects.select_related("supplier", "product")
            .prefetch_related("price_versions")
            .order_by("supplier__name", "product__name", "id")
        )

    @staticmethod
    def get(pk):
        return SupplierProductRepository.all().get(pk=pk)

    @staticmethod
    def overlapping_price_versions(*, supplier_product_id, currency, minimum_quantity, valid_from, valid_until):
        """新增價格版本前檢查同商品／幣別／數量級距是否已有時間重疊的版本，避免同一時間點出現兩個有效單價。"""
        queryset = SupplierPriceVersion.objects.filter(
            supplier_product_id=supplier_product_id,
            currency=currency,
            minimum_quantity=minimum_quantity,
        ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=valid_from))
        if valid_until is not None:
            queryset = queryset.filter(valid_from__lt=valid_until)
        return queryset


class RfqRepository:
    @staticmethod
    def accessible():
        return (
            Rfq.objects.select_related("request")
            .prefetch_related(
                "invited_suppliers__supplier", "scoring_criteria", "request__items__product",
            )
            .order_by("-created_at", "-id")
        )

    @staticmethod
    def get_for_update(pk):
        return (
            Rfq.objects.select_for_update()
            .select_related("request")
            .prefetch_related("invited_suppliers", "scoring_criteria")
            .get(pk=pk)
        )

    @staticmethod
    def evaluation_context_for_update(pk):
        return (
            Rfq.objects.select_for_update()
            .select_related("request")
            .prefetch_related(
                "scoring_criteria",
                "request__items__requirements",
                "invited_suppliers__supplier",
                "invited_suppliers__quotes__items__request_item",
                "invited_suppliers__quotes__items__requirement_results__requirement",
            )
            .get(pk=pk)
        )


class SupplierQuoteRepository:
    @staticmethod
    def accessible():
        return (
            SupplierQuote.objects.select_related("rfq_supplier__rfq__request", "rfq_supplier__supplier")
            .prefetch_related("items__request_item", "items__requirement_results__requirement")
            .order_by("-created_at", "-id")
        )

    @staticmethod
    def invitation_for_update(pk):
        return (
            RfqSupplier.objects.select_for_update()
            .select_related("rfq__request", "supplier")
            .get(pk=pk)
        )

    @staticmethod
    def get_for_update(pk):
        return (
            SupplierQuote.objects.select_for_update()
            .select_related("rfq_supplier__rfq__request", "rfq_supplier__supplier")
            .prefetch_related("items__request_item", "items__requirement_results__requirement")
            .get(pk=pk)
        )

    @staticmethod
    def requirement_result_for_update(pk):
        return (
            QuoteRequirementResult.objects.select_for_update()
            .select_related("quote_item__supplier_quote")
            .get(pk=pk)
        )


class AwardRepository:
    @staticmethod
    def accessible():
        return (
            AwardDecision.objects.select_related("selected_by", "rfq__request")
            .prefetch_related(
                "lines__request_item",
                "lines__supplier_quote_item__supplier_quote__rfq_supplier__supplier",
            )
            .order_by("-created_at", "-id")
        )

    @staticmethod
    def rfq_for_award(pk):
        return (
            Rfq.objects.select_for_update()
            .select_related("request")
            .prefetch_related("request__items")
            .get(pk=pk)
        )

    @staticmethod
    def quote_item_for_award(pk):
        return (
            SupplierQuoteItem.objects.select_related(
                "request_item",
                "supplier_quote__rfq_supplier__supplier",
                "supplier_quote__rfq_supplier__rfq",
            )
            .get(pk=pk)
        )

    @staticmethod
    def get(pk):
        return (
            AwardDecision.objects.select_related("selected_by", "rfq__request")
            .prefetch_related(
                "lines__request_item",
                "lines__supplier_quote_item__supplier_quote__rfq_supplier__supplier",
            )
            .get(pk=pk)
        )

    @staticmethod
    def get_for_update(pk):
        return (
            AwardDecision.objects.select_for_update()
            .select_related("selected_by", "rfq__request")
            .prefetch_related(
                "rfq__request__items",
                "lines__request_item",
                "lines__supplier_quote_item__supplier_quote__rfq_supplier__supplier",
            )
            .get(pk=pk)
        )
