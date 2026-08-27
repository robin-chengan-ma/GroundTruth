from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from lib.authentication import InternalApiKeyAuthentication
from repositories.procurement import ApprovalRepository, QuoteRepository
from schemas.procurement import ApprovalSerializer, QuoteSerializer
from services.inquiry_service import InquiryTriggerError, trigger_inquiry
from services.quote_calculation_service import QuoteCalculationError, calculate_quote


class QuoteViewSet(viewsets.ModelViewSet):
    serializer_class = QuoteSerializer

    def get_queryset(self):
        return QuoteRepository.all()


class ApprovalViewSet(viewsets.ModelViewSet):
    serializer_class = ApprovalSerializer

    def get_queryset(self):
        return ApprovalRepository.all()


class InquiryTriggerView(APIView):
    """FR-1：接收自然語言詢價文字，觸發 n8n Webhook。

    Phase 2 範圍：對外先開放（Vue 前端與 JWT 認證留待 Phase 4），只負責把請求轉給 n8n
    並原樣回傳 n8n 的最終結果。
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw_text = request.data.get("raw_text", "")
        try:
            result = trigger_inquiry(raw_text)
        except InquiryTriggerError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result, status=status.HTTP_200_OK)


class QuoteCalculationView(APIView):
    """FR-4／FR-4a：n8n 查完供應商/產品資料後，呼叫這裡做固定邏輯試算＋歷史均價比對。

    只給 n8n 呼叫，用內部 API Key 驗證（FR-1a），不開放給一般使用者。
    """

    authentication_classes = [InternalApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        product_id = request.data.get("product_id")
        supplier_id = request.data.get("supplier_id")
        quantity = request.data.get("quantity")

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"detail": "quantity 必須是整數"}, status=status.HTTP_400_BAD_REQUEST)

        if product_id is None:
            return Response({"detail": "product_id 為必填"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = calculate_quote(product_id=product_id, quantity=quantity, supplier_id=supplier_id)
        except QuoteCalculationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)
