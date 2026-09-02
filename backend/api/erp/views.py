from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.core.permissions import AuthenticatedReadAdminWrite, HasPermissionCode
from lib.authentication import InternalApiKeyAuthentication
from lib.jwt_authentication import BusinessJwtAuthentication
from repositories.erp import (
    InventoryRepository,
    ProductRepository,
    PurchaseSuggestionRepository,
)
from schemas.erp import (
    InventorySerializer,
    ProductSerializer,
    PurchaseSuggestionSerializer,
)
from services.goods_receipt_service import (
    GoodsReceiptConflict,
    GoodsReceiptError,
    GoodsReceiptNotFound,
    GoodsReceiptPermissionDenied,
    create_goods_receipt,
    get_accessible_goods_receipt,
    list_accessible_goods_receipts,
    serialize_goods_receipt,
    submit_goods_receipt,
)
from services.inspection_variance_service import (
    InspectionVarianceConflict,
    InspectionVarianceError,
    InspectionVarianceNotFound,
    InspectionVariancePermissionDenied,
    close_variance,
    complete_variance_line,
    create_variance_draft,
    delete_variance_draft,
    get_variance,
    list_variances,
    serialize_variance,
    submit_variance,
    update_variance_draft,
)
from services.purchase_request_draft_service import DraftError
from services.purchase_suggestion_service import (
    PurchaseSuggestionConflict,
    PurchaseSuggestionError,
    PurchaseSuggestionNotFound,
    PurchaseSuggestionPermissionDenied,
    convert_to_draft,
    dismiss,
)
from services.quality_inspection_service import inspect_goods_receipt


class GoodsReceiptViewSet(viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _error_response(self, exc):
        if isinstance(exc, GoodsReceiptNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, GoodsReceiptPermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, GoodsReceiptConflict):
            response_status = status.HTTP_409_CONFLICT
        elif isinstance(exc, PurchaseSuggestionError):
            response_status = status.HTTP_400_BAD_REQUEST
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc), "code": exc.code}, status=response_status)

    def create(self, request):
        try:
            receipt = create_goods_receipt(request.user, request.data)
        except GoodsReceiptError as exc:
            return self._error_response(exc)
        return Response(serialize_goods_receipt(receipt), status=status.HTTP_201_CREATED)

    def list(self, request):
        try:
            receipts = list_accessible_goods_receipts(request.user)
        except GoodsReceiptError as exc:
            return self._error_response(exc)
        return Response([serialize_goods_receipt(receipt) for receipt in receipts])

    def retrieve(self, request, pk=None):
        try:
            receipt = get_accessible_goods_receipt(request.user, pk)
        except GoodsReceiptError as exc:
            return self._error_response(exc)
        return Response(serialize_goods_receipt(receipt))

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        try:
            receipt = submit_goods_receipt(request.user, pk, request.data.get("version"))
        except GoodsReceiptError as exc:
            return self._error_response(exc)
        return Response(serialize_goods_receipt(receipt))

    @action(detail=True, methods=["post"])
    def inspect(self, request, pk=None):
        try:
            receipt = inspect_goods_receipt(request.user, pk, request.data)
        except GoodsReceiptError as exc:
            return self._error_response(exc)
        return Response(serialize_goods_receipt(receipt))


class InspectionVarianceViewSet(viewsets.ViewSet):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _error_response(exc):
        if isinstance(exc, InspectionVarianceNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, InspectionVariancePermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, InspectionVarianceConflict):
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc), "code": exc.code}, status=response_status)

    def create(self, request):
        try:
            variance_case = create_variance_draft(request.user, request.data)
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return Response(serialize_variance(variance_case), status=status.HTTP_201_CREATED)

    def list(self, request):
        try:
            cases = list_variances(request.user)
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return Response([serialize_variance(case) for case in cases])

    def retrieve(self, request, pk=None):
        try:
            variance_case = get_variance(request.user, pk)
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return Response(serialize_variance(variance_case))

    def update(self, request, pk=None):
        try:
            variance_case = update_variance_draft(request.user, pk, request.data)
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return Response(serialize_variance(variance_case))

    def destroy(self, request, pk=None):
        try:
            delete_variance_draft(request.user, pk, request.data.get("version"))
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        try:
            variance_case = submit_variance(request.user, pk, request.data.get("version"))
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return Response(serialize_variance(variance_case))

    @action(detail=True, methods=["post"], url_path="complete-line")
    def complete_line(self, request, pk=None):
        try:
            variance_case = complete_variance_line(
                request.user,
                pk,
                request.data.get("line_id"),
                request.data.get("version"),
            )
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return Response(serialize_variance(variance_case))

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        try:
            variance_case = close_variance(request.user, pk, request.data.get("version"))
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return Response(serialize_variance(variance_case))

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    authentication_classes = [BusinessJwtAuthentication, InternalApiKeyAuthentication]
    permission_classes = [AuthenticatedReadAdminWrite]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]  # 供 Phase 2 n8n 依名稱查詢產品用（?search=A產品）

    def get_queryset(self):
        return ProductRepository.all()

    def destroy(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "品項主檔不得實體刪除，請改為停用",
                "code": "physical_delete_forbidden",
            },
            status=status.HTTP_409_CONFLICT,
        )


class InventoryViewSet(viewsets.ReadOnlyModelViewSet):
    """唯讀庫存查詢：master_data.read／master_data.manage 不得替代，須有專屬 inventory.read。"""

    serializer_class = InventorySerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [HasPermissionCode]
    required_permission = "inventory.read"

    def get_queryset(self):
        return InventoryRepository.all()


class PurchaseSuggestionViewSet(viewsets.ReadOnlyModelViewSet):
    """FR-10a／FR-10b：低庫存採購建議查詢，list／retrieve 須有專屬 purchase_suggestion.read；
    convert／dismiss 各自的授權已由 service 層依 purchase_request.create／admin 身分把關，
    不套用讀取權限碼，避免混淆「能看」與「能轉單／忽略」兩種不同的能力。"""

    serializer_class = PurchaseSuggestionSerializer
    authentication_classes = [BusinessJwtAuthentication]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            self.required_permission = "purchase_suggestion.read"
            return [HasPermissionCode()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return PurchaseSuggestionRepository.all()

    def _error_response(self, exc):
        if isinstance(exc, PurchaseSuggestionNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, PurchaseSuggestionPermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, PurchaseSuggestionConflict):
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc), "code": exc.code}, status=response_status)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        try:
            suggestion = convert_to_draft(request.user, pk, request.data)
        except (PurchaseSuggestionError, DraftError) as exc:
            return self._error_response(exc)
        return Response(
            {
                "id": suggestion.id,
                "status": suggestion.status,
                "purchase_request_id": suggestion.purchase_request_id,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        try:
            suggestion = dismiss(request.user, pk)
        except PurchaseSuggestionError as exc:
            return self._error_response(exc)
        return Response(self.get_serializer(suggestion).data)
