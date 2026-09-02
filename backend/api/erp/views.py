from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.core.permissions import AuthenticatedReadAdminWrite, HasPermissionCode
from apps.erp.models import ProductCategory
from lib.authentication import InternalApiKeyAuthentication
from lib.jwt_authentication import BusinessJwtAuthentication
from lib.pagination import paginate_response, parse_optional_bool, parse_optional_int
from repositories.erp import (
    InventoryBalanceRepository,
    InventoryMovementQueryRepository,
    InventoryRepository,
    ProductRepository,
    PurchaseSuggestionRepository,
)
from schemas.erp import (
    InventoryBalanceSerializer,
    InventoryMovementSerializer,
    InventorySerializer,
    ProductCategorySerializer,
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
            receipts = list_accessible_goods_receipts(
                request.user,
                search=request.query_params.get("search"),
                status=request.query_params.get("status"),
            )
        except GoodsReceiptError as exc:
            return self._error_response(exc)
        return paginate_response(
            request,
            receipts,
            serialize=lambda page: [serialize_goods_receipt(receipt) for receipt in page],
        )

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
            cases = list_variances(
                request.user,
                search=request.query_params.get("search"),
                status=request.query_params.get("status"),
            )
        except InspectionVarianceError as exc:
            return self._error_response(exc)
        return paginate_response(
            request, cases, serialize=lambda page: [serialize_variance(case) for case in page]
        )

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

class ProductCategoryViewSet(viewsets.ModelViewSet):
    """品項分類與規格定義主檔：僅啟用／停用，不提供實體刪除。"""

    serializer_class = ProductCategorySerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [AuthenticatedReadAdminWrite]

    def get_queryset(self):
        queryset = ProductCategory.objects.all()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        is_active = parse_optional_bool(self.request.query_params.get("is_active"))
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("id")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return paginate_response(
            request, queryset, serialize=lambda page: self.get_serializer(page, many=True).data
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "品項分類主檔不得實體刪除，請改為停用",
                "code": "physical_delete_forbidden",
            },
            status=status.HTTP_409_CONFLICT,
        )


class ProductViewSet(viewsets.ModelViewSet):
    """`?search=` 沿用既有慣例（名稱／料號模糊比對），Phase 2 n8n 依名稱查詢產品
    （只讀 `results[0]`，見 n8n/workflows/inquiry-flow.json）與 Phase 6 品項清單頁共用同一參數。"""

    serializer_class = ProductSerializer
    authentication_classes = [BusinessJwtAuthentication, InternalApiKeyAuthentication]
    permission_classes = [AuthenticatedReadAdminWrite]

    def get_queryset(self):
        category_id, _ = parse_optional_int(self.request.query_params.get("category"), field_name="category")
        return ProductRepository.all(
            search=self.request.query_params.get("search"),
            category_id=category_id,
            is_active=parse_optional_bool(self.request.query_params.get("is_active")),
        )

    def list(self, request, *args, **kwargs):
        _, error = parse_optional_int(request.query_params.get("category"), field_name="category")
        if error:
            return error
        queryset = self.get_queryset()
        return paginate_response(
            request, queryset, serialize=lambda page: self.get_serializer(page, many=True).data
        )

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


class InventoryBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """FR-10a：庫存真相來源查詢——on_hand／reserved／in_transit 查詢快照＋門檻。取代
    Phase 1 舊 InventoryViewSet（stock_qty 已停止由正式收貨驗收流程更新，僅供歷史查閱）。"""

    serializer_class = InventoryBalanceSerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [HasPermissionCode]
    required_permission = "inventory.read"

    def get_queryset(self):
        return InventoryBalanceRepository.all()


class InventoryMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """FR-10a：不可覆寫庫存流水帳唯讀查詢。"""

    serializer_class = InventoryMovementSerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [HasPermissionCode]
    required_permission = "inventory.read"

    def get_queryset(self):
        return InventoryMovementQueryRepository.all()


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
        return PurchaseSuggestionRepository.all(
            search=self.request.query_params.get("search"),
            status=self.request.query_params.get("status"),
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return paginate_response(
            request, queryset, serialize=lambda page: self.get_serializer(page, many=True).data
        )

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
