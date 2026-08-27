from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.procurement.models import Quote
from lib.authentication import InternalApiKeyAuthentication
from repositories.procurement import ApprovalRepository, QuoteRepository
from schemas.procurement import ApprovalSerializer, QuoteSerializer
from services.hallucination_check_service import HallucinationCheckError, check_summary
from services.inquiry_service import InquiryTriggerError, trigger_inquiry
from services.quote_calculation_service import QuoteCalculationError, create_quote


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
        user_id = request.data.get("user_id")
        if user_id is None:
            return Response({"detail": "user_id 為必填"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = trigger_inquiry(raw_text, user_id=user_id)
        except InquiryTriggerError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result, status=status.HTTP_200_OK)


class QuoteCalculationView(APIView):
    """FR-4／FR-4a：n8n 查完供應商/產品資料後，呼叫這裡做固定邏輯試算＋歷史均價比對，
    並正式建立 Quote 資料列（Phase 3：幻覺驗證需要一個真實存在的 quote_id 才能運作）。

    只給 n8n 呼叫，用內部 API Key 驗證（FR-1a），不開放給一般使用者。

    user_id：詢價發起人。Vue＋JWT 使用者驗證留待 Phase 4，這裡先比照
    manual-review-queue 的 claim/decide，要求呼叫端明確帶 user_id（見
    docs/ADR/discuss/main-flow.md 對應決策）；Phase 4 接上 JWT 後，n8n 端改成
    從 inquiries/trigger/ 收到的 user_id（由 Vue 帶 JWT 解出）原樣往下傳即可。
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
            return Response({"passed": True}, status=status.HTTP_200_OK)

        return Response(
            {"passed": False, "reasons": result["reasons"], "review_id": result["review_id"]},
            status=status.HTTP_200_OK,
        )
