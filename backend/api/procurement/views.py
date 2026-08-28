from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.procurement.models import Quote
from lib.authentication import InternalApiKeyAuthentication
from lib.jwt_authentication import BusinessJwtAuthentication
from repositories.procurement import ApprovalRepository, QuoteRepository
from schemas.procurement import ApprovalSerializer, QuoteSerializer
from services.approval_routing_service import route_quote
from services.approval_service import (
    ApprovalConflictError,
    ApprovalError,
    claim_approval,
    decide_approval,
    withdraw_quote,
)
from services.hallucination_check_service import HallucinationCheckError, check_summary
from services.inquiry_service import InquiryTriggerError, InquiryValidationError, trigger_inquiry
from services.quote_calculation_service import QuoteCalculationError, create_quote


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
