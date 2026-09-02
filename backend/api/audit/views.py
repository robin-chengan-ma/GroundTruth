from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from api.core.permissions import HasPermissionCode
from lib.authentication import InternalApiKeyAuthentication
from lib.jwt_authentication import BusinessJwtAuthentication
from repositories.audit import AuditLogRepository, ManualReviewQueueRepository
from schemas.audit import AuditLogSerializer, ManualReviewQueueSerializer
from services.audit_dashboard_service import compute_dashboard_stats
from services.manual_review_service import (
    LegacyManualReviewRetiredError,
    ManualReviewConflictError,
    ManualReviewError,
    claim_review,
    decide_review,
    retry_resume,
)
from services.masking_service import (
    MaskingError,
    mask_amounts_only,
    mask_text,
    unmask_text,
)


class ManualReviewQueueViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ManualReviewQueueSerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [HasPermissionCode]

    def get_permissions(self):
        self.required_permission = (
            "manual_review.claim" if self.action == "claim" else "manual_review.decide"
        )
        return super().get_permissions()

    def _resume_conflict_or_error_response(self, exc):
        if isinstance(exc, LegacyManualReviewRetiredError):
            return Response(
                {"detail": str(exc), "code": "legacy_command_retired"},
                status=status.HTTP_410_GONE,
            )
        if isinstance(exc, ManualReviewConflictError):
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def get_queryset(self):
        return ManualReviewQueueRepository.all()

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        """FR-6b：認領案件，避免多位管理員同時處理同一案件（衝突回 409）。"""
        try:
            review = claim_review(pk, request.user.id)
        except ManualReviewError as exc:
            return self._resume_conflict_or_error_response(exc)

        return Response(ManualReviewQueueSerializer(review).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """FR-6a／FR-6c：決議案件（核准/駁回），依 review_type 分流，並寫入稽核 log。

        supplier_fuzzy_match 案件核准後的續傳解析結果（是否自動建立採購需求草稿）落地在
        回應的 resume_status／resume_error_code／created_purchase_request 欄位（2026-09-02
        改版，見 docs/ADR/discuss/main-flow.md）；resume_status=failed 時可呼叫
        retry-resume 重試，不需要整個案件重新走一次核准流程。
        """
        decision = request.data.get("decision")
        supplier_id = request.data.get("supplier_id")

        if decision is None:
            return Response({"detail": "decision 為必填"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            review = decide_review(pk, request.user.id, decision, supplier_id=supplier_id)
        except ManualReviewError as exc:
            return self._resume_conflict_or_error_response(exc)

        return Response(ManualReviewQueueSerializer(review).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="retry-resume")
    def retry(self, request, pk=None):
        """FR-6a 續傳重試（2026-09-02 新增）：只有已核准的 supplier_fuzzy_match 案件、且
        上次續傳結果為 resume_status=failed 時才能重試，狀態不符回 409。"""
        try:
            review = retry_resume(pk, request.user.id)
        except ManualReviewError as exc:
            return self._resume_conflict_or_error_response(exc)

        return Response(ManualReviewQueueSerializer(review).data, status=status.HTTP_200_OK)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """稽核 log 依 SPEC 為系統寫入紀錄；Phase 1 先提供完整 CRUD 供測試/管理用，
    後續 Phase 若需限制為唯讀，於 API 層加 http_method_names 即可。"""

    serializer_class = AuditLogSerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [HasPermissionCode]
    required_permission = "audit.read"

    def get_queryset(self):
        return AuditLogRepository.all()


class AuditDashboardStatsView(APIView):
    """稽核與正確率總覽（SPEC「稽核與正確率總覽」FR-1～5）統計聚合，僅 admin 可存取。"""

    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [HasPermissionCode]
    required_permission = "audit.read"

    def get(self, request):
        stats = compute_dashboard_stats(
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
        )
        return Response(stats, status=status.HTTP_200_OK)


class MaskTextView(APIView):
    """FR-2：n8n Mask 節點呼叫，把使用者原始輸入中的供應商名稱／金額換成 Token。

    只給 n8n 呼叫（需要 X-Internal-Api-Key），不開放給前端使用者。
    對應/遮罩表只在這次回應中回傳給 n8n（於當次 workflow 執行記憶體中保存），
    依 NFR-1 絕不落地寫入 DB。

    user_id：詢價發起人，供應商模糊比對案件會存進 `manual_review_queue.requester`，
    核准後才知道要用誰的身分重新建立 Quote（見 FR-6a 續傳流程）。
    """

    authentication_classes = [InternalApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        raw_text = request.data.get("raw_text", "")
        requester_id = request.data.get("user_id")
        try:
            result = mask_text(raw_text, requester_id=requester_id)
        except MaskingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class UnmaskTextView(APIView):
    """FR-2a：n8n Unmask 節點呼叫，LLM 解析完成後立即用對照表還原真實值。"""

    authentication_classes = [InternalApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        masked_text = request.data.get("masked_text", "")
        mapping = request.data.get("mapping", {})
        result = unmask_text(masked_text, mapping)
        return Response({"text": result}, status=status.HTTP_200_OK)


class MaskAmountsOnlyView(APIView):
    """FR-6a 續傳流程專用：供應商已由人工確認（走 supplier_id，不需要文字比對），
    Mask 節點只需要照常規則遮罩金額。只給 n8n 呼叫。
    """

    authentication_classes = [InternalApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        raw_text = request.data.get("raw_text", "")
        try:
            result = mask_amounts_only(raw_text)
        except MaskingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)
