from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from lib.authentication import InternalApiKeyAuthentication
from lib.jwt_authentication import BusinessJwtAuthentication
from repositories.procurement import ApprovalRepository, QuoteRepository
from schemas.procurement import (
    ApprovalSerializer,
    PurchaseRequestDetailSerializer,
    PurchaseRequestDraftSerializer,
    PurchaseRequestListSerializer,
    QuoteRequirementResultSerializer,
    QuoteSerializer,
    RfqSerializer,
    SupplierProductSerializer,
    SupplierQuoteSerializer,
)
from services.approval_case_service import (
    ApprovalWorkflowConflict,
    ApprovalWorkflowError,
    ApprovalWorkflowNotFound,
    ApprovalWorkflowPermissionDenied,
    claim_step,
    decide_step,
    get_accessible_case,
    list_accessible_cases,
    serialize_case,
    serialize_step,
)
from services.award_selection_service import (
    AwardSelectionConflict,
    AwardSelectionError,
    AwardSelectionNotFound,
    AwardSelectionPermissionDenied,
    create_award_draft,
    get_accessible_award,
    list_accessible_awards,
    serialize_award,
    submit_award,
    update_award_draft,
)
from services.inquiry_service import (
    InquiryTriggerError,
    InquiryValidationError,
    parse_purchase_request_candidate,
)
from services.purchase_order_service import (
    PurchaseOrderConflict,
    PurchaseOrderError,
    PurchaseOrderNotFound,
    PurchaseOrderPermissionDenied,
    get_accessible_purchase_order,
    issue_purchase_order,
    list_accessible_purchase_orders,
    serialize_purchase_order,
)
from services.purchase_request_draft_service import (
    DraftClarificationRequired,
    DraftError,
    DraftNotFound,
    DraftPermissionDenied,
    DraftVersionConflict,
    create_draft,
    delete_draft,
    get_owned_draft,
    get_owned_request,
    list_owned_drafts,
    list_owned_requests,
    preview_draft,
    submit_draft,
    update_draft,
    withdraw_request,
)
from services.rbac_service import user_has_permission
from services.rfq_evaluation_service import evaluate_rfq
from services.rfq_quote_service import (
    RfqQuoteConflict,
    RfqQuoteError,
    RfqQuoteNotFound,
    RfqQuotePermissionDenied,
    get_accessible_quote,
    get_accessible_rfq,
    issue_rfq,
    list_accessible_quotes,
    list_accessible_rfqs,
    revise_quote,
    submit_quote,
    waive_requirement,
)
from services.rfq_quote_service import (
    create_quote as create_supplier_quote,
)
from services.supplier_product_coverage_service import (
    SupplierProductCoverageError,
    build_supplier_product_coverage,
)
from services.supplier_product_service import (
    SupplierProductConflict,
    SupplierProductError,
    SupplierProductNotFound,
    SupplierProductPermissionDenied,
    add_price_version,
    create_supplier_product,
    get_supplier_product,
    list_supplier_products,
    update_supplier_product,
)


class RfqQuoteErrorMixin:
    def _rfq_error_response(self, exc):
        if isinstance(exc, RfqQuoteNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, RfqQuotePermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, RfqQuoteConflict):
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc), "code": exc.code}, status=response_status)


def legacy_command_retired_response():
    return Response(
        {
            "detail": "舊版詢價建單流程已停用，請改用採購需求流程",
            "code": "legacy_command_retired",
        },
        status=status.HTTP_410_GONE,
    )


class AwardDecisionViewSet(viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _error_response(self, exc):
        if isinstance(exc, AwardSelectionNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, AwardSelectionPermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, AwardSelectionConflict):
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc), "code": exc.code}, status=response_status)

    def list(self, request):
        try:
            awards = list_accessible_awards(request.user)
        except AwardSelectionError as exc:
            return self._error_response(exc)
        return Response([serialize_award(award) for award in awards])

    def retrieve(self, request, pk=None):
        try:
            award = get_accessible_award(request.user, pk)
        except AwardSelectionError as exc:
            return self._error_response(exc)
        return Response(serialize_award(award))

    def create(self, request):
        try:
            award = create_award_draft(request.user, request.data)
        except AwardSelectionError as exc:
            return self._error_response(exc)
        return Response(serialize_award(award), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            award = update_award_draft(request.user, pk, request.data)
        except AwardSelectionError as exc:
            return self._error_response(exc)
        return Response(serialize_award(award))

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        try:
            award = submit_award(request.user, pk)
        except AwardSelectionError as exc:
            return self._error_response(exc)
        return Response(serialize_award(award))


class ApprovalWorkflowErrorMixin:
    def _approval_workflow_error_response(self, exc):
        if isinstance(exc, ApprovalWorkflowNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, ApprovalWorkflowPermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, ApprovalWorkflowConflict):
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc), "code": exc.code}, status=response_status)


class ApprovalCaseViewSet(ApprovalWorkflowErrorMixin, viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        try:
            cases = list_accessible_cases(request.user)
        except ApprovalWorkflowError as exc:
            return self._approval_workflow_error_response(exc)
        return Response([serialize_case(case, request.user) for case in cases])

    def retrieve(self, request, pk=None):
        try:
            case = get_accessible_case(request.user, pk)
        except ApprovalWorkflowError as exc:
            return self._approval_workflow_error_response(exc)
        return Response(serialize_case(case, request.user))


class ApprovalStepViewSet(ApprovalWorkflowErrorMixin, viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        try:
            step = claim_step(request.user, pk)
        except ApprovalWorkflowError as exc:
            return self._approval_workflow_error_response(exc)
        return Response(serialize_step(step, request.user))

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        try:
            step = decide_step(
                request.user,
                pk,
                request.data.get("decision"),
                request.data.get("reason"),
            )
        except ApprovalWorkflowError as exc:
            return self._approval_workflow_error_response(exc)
        return Response(serialize_step(step, request.user))


class PurchaseOrderViewSet(viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _error_response(self, exc):
        if isinstance(exc, PurchaseOrderNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, PurchaseOrderPermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, PurchaseOrderConflict):
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc), "code": exc.code}, status=response_status)

    def list(self, request):
        try:
            purchase_orders = list_accessible_purchase_orders(request.user)
        except PurchaseOrderError as exc:
            return self._error_response(exc)
        return Response([serialize_purchase_order(order) for order in purchase_orders])

    def retrieve(self, request, pk=None):
        try:
            purchase_order = get_accessible_purchase_order(request.user, pk)
        except PurchaseOrderError as exc:
            return self._error_response(exc)
        return Response(serialize_purchase_order(purchase_order))

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        try:
            purchase_order = issue_purchase_order(request.user, pk, request.data.get("version"))
        except PurchaseOrderError as exc:
            return self._error_response(exc)
        return Response(serialize_purchase_order(purchase_order))

class RfqViewSet(RfqQuoteErrorMixin, viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        try:
            rfqs = list_accessible_rfqs(request.user)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(RfqSerializer(rfqs, many=True).data)

    def retrieve(self, request, pk=None):
        try:
            rfq = get_accessible_rfq(request.user, pk)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(RfqSerializer(rfq).data)

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        try:
            rfq = issue_rfq(request.user, pk, request.data)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(RfqSerializer(rfq).data)

    @action(detail=True, methods=["post"])
    def evaluate(self, request, pk=None):
        try:
            result = evaluate_rfq(request.user, pk)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(result)


class SupplierQuoteViewSet(RfqQuoteErrorMixin, viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        try:
            quotes = list_accessible_quotes(request.user)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(SupplierQuoteSerializer(quotes, many=True).data)

    def retrieve(self, request, pk=None):
        try:
            quote = get_accessible_quote(request.user, pk)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(SupplierQuoteSerializer(quote).data)

    def create(self, request):
        try:
            quote = create_supplier_quote(request.user, request.data)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(SupplierQuoteSerializer(quote).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        try:
            quote = submit_quote(request.user, pk)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(SupplierQuoteSerializer(quote).data)

    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        try:
            quote = revise_quote(request.user, pk, request.data)
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(SupplierQuoteSerializer(quote).data, status=status.HTTP_201_CREATED)


class QuoteRequirementResultViewSet(RfqQuoteErrorMixin, viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=["post"])
    def waive(self, request, pk=None):
        try:
            result = waive_requirement(request.user, pk, request.data.get("reason"))
        except RfqQuoteError as exc:
            return self._rfq_error_response(exc)
        return Response(QuoteRequirementResultSerializer(result).data)


class SupplierProductViewSet(viewsets.ViewSet):
    """FR-2／FR-16：供應商可供應品項與版本化價格主檔。"""

    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _error_response(self, exc):
        if isinstance(exc, SupplierProductNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, SupplierProductPermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, SupplierProductConflict):
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc), "code": exc.code}, status=response_status)

    def list(self, request):
        try:
            items = list_supplier_products(request.user)
        except SupplierProductError as exc:
            return self._error_response(exc)
        return Response(SupplierProductSerializer(items, many=True).data)

    def retrieve(self, request, pk=None):
        try:
            item = get_supplier_product(request.user, pk)
        except SupplierProductError as exc:
            return self._error_response(exc)
        return Response(SupplierProductSerializer(item).data)

    def create(self, request):
        try:
            item = create_supplier_product(request.user, request.data)
        except SupplierProductError as exc:
            return self._error_response(exc)
        return Response(SupplierProductSerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            item = update_supplier_product(request.user, pk, request.data)
        except SupplierProductError as exc:
            return self._error_response(exc)
        return Response(SupplierProductSerializer(item).data)

    def destroy(self, request, pk=None):
        return Response(
            {
                "detail": "供應商品項關係不得實體刪除，請改為停用",
                "code": "physical_delete_forbidden",
            },
            status=status.HTTP_409_CONFLICT,
        )

    @action(detail=True, methods=["post"], url_path="price-versions")
    def price_versions(self, request, pk=None):
        try:
            item = add_price_version(request.user, pk, request.data)
        except SupplierProductError as exc:
            return self._error_response(exc)
        return Response(SupplierProductSerializer(item).data, status=status.HTTP_201_CREATED)


class PurchaseRequestDraftViewSet(viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _error_response(self, exc):
        payload = {"detail": str(exc), "code": exc.code}
        if isinstance(exc, DraftClarificationRequired):
            payload["missing_fields"] = exc.missing_fields
        if isinstance(exc, DraftNotFound):
            code = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, DraftPermissionDenied):
            code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, DraftVersionConflict):
            code = status.HTTP_409_CONFLICT
        else:
            code = status.HTTP_400_BAD_REQUEST
        return Response(payload, status=code)

    def create(self, request):
        try:
            draft = create_draft(request.user, request.data)
        except DraftError as exc:
            return self._error_response(exc)
        return Response(PurchaseRequestDraftSerializer(draft).data, status=status.HTTP_201_CREATED)

    def list(self, request):
        try:
            drafts = list_owned_drafts(request.user)
        except DraftError as exc:
            return self._error_response(exc)
        return Response(PurchaseRequestDraftSerializer(drafts, many=True).data)

    def retrieve(self, request, pk=None):
        try:
            draft = get_owned_draft(request.user, pk)
        except DraftError as exc:
            return self._error_response(exc)
        return Response(PurchaseRequestDraftSerializer(draft).data)

    def partial_update(self, request, pk=None):
        try:
            draft = update_draft(request.user, pk, request.data)
        except DraftError as exc:
            return self._error_response(exc)
        return Response(PurchaseRequestDraftSerializer(draft).data)

    def destroy(self, request, pk=None):
        try:
            delete_draft(request.user, pk)
        except DraftError as exc:
            return self._error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        try:
            result = preview_draft(request.user, pk, request.data.get("version"))
        except DraftError as exc:
            return self._error_response(exc)
        return Response(result)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        try:
            draft = submit_draft(
                request.user,
                pk,
                version=request.data.get("version"),
                idempotency_key=request.data.get("idempotency_key"),
            )
        except DraftError as exc:
            return self._error_response(exc)
        return Response({
            "id": draft.id,
            "request_no": draft.request_no,
            "status": draft.status,
            "version": draft.version,
            "idempotency_key": draft.idempotency_key,
        })


class PurchaseRequestViewSet(viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    page_sizes = {10, 20, 50}

    @staticmethod
    def _pagination_error(detail):
        return Response(
            {"detail": detail, "code": "invalid_pagination"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def list(self, request):
        try:
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 20))
        except (TypeError, ValueError):
            return self._pagination_error("page 與 page_size 必須是整數")
        if page < 1:
            return self._pagination_error("page 必須大於 0")
        if page_size not in self.page_sizes:
            return self._pagination_error("page_size 只允許 10、20 或 50")
        try:
            requests = list_owned_requests(
                request.user,
                search=request.query_params.get("search"),
                status=request.query_params.get("status"),
            )
        except DraftError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_403_FORBIDDEN,
            )
        paginator = Paginator(requests, page_size)
        try:
            page_data = paginator.page(page)
        except EmptyPage:
            return self._pagination_error("page 超出有效範圍")
        return Response({
            "count": paginator.count,
            "page": page_data.number,
            "page_size": page_size,
            "total_pages": max(1, paginator.num_pages),
            "results": PurchaseRequestListSerializer(page_data.object_list, many=True).data,
        })

    def retrieve(self, request, pk=None):
        try:
            purchase_request = get_owned_request(request.user, pk)
        except DraftNotFound:
            return Response(
                {"detail": "找不到指定的採購需求", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DraftError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(PurchaseRequestDetailSerializer(purchase_request).data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        try:
            purchase_request = withdraw_request(
                request.user,
                pk,
                version=request.data.get("version"),
                reason=request.data.get("reason"),
            )
        except DraftNotFound as exc:
            response_status = status.HTTP_404_NOT_FOUND
            error = exc
        except DraftPermissionDenied as exc:
            response_status = status.HTTP_403_FORBIDDEN
            error = exc
        except DraftVersionConflict as exc:
            response_status = status.HTTP_409_CONFLICT
            error = exc
        except DraftError as exc:
            response_status = status.HTTP_400_BAD_REQUEST
            error = exc
        else:
            return Response(PurchaseRequestDetailSerializer(purchase_request).data)
        return Response({"detail": str(error), "code": error.code}, status=response_status)


class QuoteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = QuoteSerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = QuoteRepository.all()
        user = self.request.user
        if user.role.role == "admin":
            return queryset
        if user.role.role == "employee":
            return queryset.filter(user=user)
        return queryset.filter(Q(approvals__role=user.role) | Q(user=user)).distinct()

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        return legacy_command_retired_response()


class ApprovalViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ApprovalSerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ApprovalRepository.all()
        if self.request.user.role.role == "admin":
            return queryset
        return queryset.filter(role=self.request.user.role)

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        return legacy_command_retired_response()

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        return legacy_command_retired_response()


class InquiryTriggerView(APIView):
    """Phase 5.0：保留舊路徑以回覆明確的停用契約。"""

    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return legacy_command_retired_response()


class InquiryCandidateParseView(APIView):
    """FR-3：只產生可編輯的採購需求候選結構。"""

    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not user_has_permission(request.user, "purchase_request.create"):
            return Response(
                {"detail": "沒有執行此操作的權限", "code": "permission_denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            result = parse_purchase_request_candidate(
                request.data.get("raw_text", ""), user_id=request.user.id,
            )
        except InquiryValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InquiryTriggerError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        coverage = build_supplier_product_coverage({
            "currency": result.get("currency", "TWD"),
            "supplier_ids": [
                row["supplier_id"]
                for row in result.get("supplier_candidates", [])
                if row.get("supplier_id") is not None
            ],
            "items": [
                row
                for row in result.get("items", [])
                if row.get("product_id") is not None and row.get("quantity") is not None
            ],
        })
        result["supplier_product_coverage"] = coverage["rows"]
        return Response(result)


class SupplierProductCoverageView(APIView):
    """建立草稿前，回傳目前選擇的供應商與品項供應能力矩陣。"""

    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not user_has_permission(request.user, "purchase_request.create"):
            return Response(
                {"detail": "沒有執行此操作的權限", "code": "permission_denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            result = build_supplier_product_coverage(request.data)
        except (SupplierProductCoverageError, TypeError, ValueError) as exc:
            return Response(
                {"detail": str(exc), "code": "invalid_coverage_request"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)


class QuoteCalculationView(APIView):
    """Phase 5.0：保留舊內部路徑以回覆明確的停用契約。"""

    authentication_classes = [InternalApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return legacy_command_retired_response()


class QuoteHallucinationVerifyView(APIView):
    """Phase 5.0：保留舊內部路徑以回覆明確的停用契約。"""

    authentication_classes = [InternalApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return legacy_command_retired_response()
