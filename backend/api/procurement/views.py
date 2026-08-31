from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.procurement.models import Quote
from lib.authentication import InternalApiKeyAuthentication
from lib.jwt_authentication import BusinessJwtAuthentication
from repositories.procurement import ApprovalRepository, QuoteRepository
from schemas.procurement import (
    ApprovalSerializer,
    PurchaseRequestDraftSerializer,
    PurchaseRequestListSerializer,
    QuoteRequirementResultSerializer,
    QuoteSerializer,
    RfqSerializer,
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
from services.approval_routing_service import route_quote
from services.approval_service import (
    ApprovalConflictError,
    ApprovalError,
    claim_approval,
    decide_approval,
    withdraw_quote,
)
from services.award_selection_service import (
    AwardSelectionConflict,
    AwardSelectionError,
    AwardSelectionNotFound,
    AwardSelectionPermissionDenied,
    create_award_draft,
    serialize_award,
    submit_award,
    update_award_draft,
)
from services.hallucination_check_service import HallucinationCheckError, check_summary
from services.inquiry_service import (
    InquiryTriggerError,
    InquiryValidationError,
    parse_purchase_request_candidate,
    trigger_inquiry,
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
    list_owned_drafts,
    list_owned_requests,
    preview_draft,
    submit_draft,
    update_draft,
)
from services.quote_calculation_service import QuoteCalculationError, create_quote
from services.rbac_service import user_has_permission
from services.rfq_evaluation_service import evaluate_rfq
from services.rfq_quote_service import (
    RfqQuoteConflict,
    RfqQuoteError,
    RfqQuoteNotFound,
    RfqQuotePermissionDenied,
    issue_rfq,
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
        return Response([serialize_case(case) for case in cases])

    def retrieve(self, request, pk=None):
        try:
            case = get_accessible_case(request.user, pk)
        except ApprovalWorkflowError as exc:
            return self._approval_workflow_error_response(exc)
        return Response(serialize_case(case))


class ApprovalStepViewSet(ApprovalWorkflowErrorMixin, viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        try:
            step = claim_step(request.user, pk)
        except ApprovalWorkflowError as exc:
            return self._approval_workflow_error_response(exc)
        return Response(serialize_step(step))

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
        return Response(serialize_step(step))


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

    def list(self, request):
        try:
            requests = list_owned_requests(request.user)
        except DraftError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(PurchaseRequestListSerializer(requests, many=True).data)


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
        try:
            quote = withdraw_quote(pk, request.user)
        except ApprovalConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(QuoteSerializer(quote).data)


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
        try:
            approval = claim_approval(pk, request.user)
        except ApprovalConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ApprovalSerializer(approval).data)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        try:
            approval = decide_approval(pk, request.user, request.data.get("decision"))
        except ApprovalConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ApprovalSerializer(approval).data)


class InquiryTriggerView(APIView):
    """FR-1：以 JWT 使用者身分接收自然語言詢價文字，觸發 n8n Webhook。"""

    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        raw_text = request.data.get("raw_text", "")
        try:
            result = trigger_inquiry(raw_text, user_id=request.user.id)
        except InquiryValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InquiryTriggerError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result, status=status.HTTP_200_OK)


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
    """FR-4／FR-4a：n8n 查完供應商/產品資料後，呼叫這裡做固定邏輯試算＋歷史均價比對，
    並正式建立 Quote 資料列（Phase 3：幻覺驗證需要一個真實存在的 quote_id 才能運作）。

    只給 n8n 呼叫，用內部 API Key 驗證（FR-1a），不開放給一般使用者。

    user_id：由 inquiries/trigger/ 驗證 JWT 後傳給 n8n，再由 n8n 原樣帶回建立 Quote。
    """

    authentication_classes = [InternalApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user_id = request.data.get("user_id")
        product_id = request.data.get("product_id")
        supplier_id = request.data.get("supplier_id")
        quantity = request.data.get("quantity")

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"detail": "quantity 必須是整數"}, status=status.HTTP_400_BAD_REQUEST)

        if user_id is None:
            return Response({"detail": "user_id 為必填"}, status=status.HTTP_400_BAD_REQUEST)
        if product_id is None:
            return Response({"detail": "product_id 為必填"}, status=status.HTTP_400_BAD_REQUEST)
        if supplier_id is None:
            return Response({"detail": "supplier_id 為必填"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = create_quote(
                user_id=user_id, product_id=product_id, quantity=quantity, supplier_id=supplier_id,
            )
        except QuoteCalculationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)


class QuoteHallucinationVerifyView(APIView):
    """FR-6：比對 LLM 生成摘要文字中的數字與真實查詢值；不一致時寫入複核佇列並中止流程。

    真實數字／名稱一律從 Quote 資料列本身讀取，不信任呼叫端傳入的數字——
    唯一信任呼叫端傳入的是 summary_text（LLM 生成內容，正是這支端點要驗證的對象）。
    只給 n8n 呼叫，用內部 API Key 驗證，不開放給一般使用者。
    """

    authentication_classes = [InternalApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        quote_id = request.data.get("quote_id")
        summary_text = request.data.get("summary_text", "")

        if quote_id is None:
            return Response({"detail": "quote_id 為必填"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quote = QuoteRepository.get(quote_id)
        except Quote.DoesNotExist:
            return Response({"detail": "找不到指定的 Quote"}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = check_summary(
                summary_text=summary_text,
                quote=quote,
                quantity=quote.quantity,
                unit_price=quote.price,
                total_amount=quote.total_amount,
                supplier_name=quote.supplier.name,
                product_name=quote.product.name,
            )
        except HallucinationCheckError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if result["passed"]:
            quote.ai_summary_text = summary_text
            quote.status = Quote.Status.PENDING_APPROVAL
            quote.save(update_fields=["ai_summary_text", "status"])
            route_quote(quote)
            return Response({"passed": True}, status=status.HTTP_200_OK)

        return Response(
            {"passed": False, "reasons": result["reasons"], "review_id": result["review_id"]},
            status=status.HTTP_200_OK,
        )
