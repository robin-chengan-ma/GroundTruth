from rest_framework import status, viewsets
from rest_framework.response import Response

from api.core.permissions import AuthenticatedReadAdminWrite
from lib.authentication import InternalApiKeyAuthentication
from lib.jwt_authentication import BusinessJwtAuthentication
from lib.pagination import paginate_response, parse_optional_bool
from repositories.crm import SupplierRepository
from schemas.crm import SupplierSerializer


class SupplierViewSet(viewsets.ModelViewSet):
    """`?search=` 沿用既有慣例（名稱／內部代碼模糊比對），Phase 2 n8n 依名稱查詢供應商
    （只讀 `results[0]`，見 n8n/workflows/inquiry-flow.json）與 Phase 6 供應商清單頁共用同一參數。"""

    serializer_class = SupplierSerializer
    authentication_classes = [BusinessJwtAuthentication, InternalApiKeyAuthentication]
    permission_classes = [AuthenticatedReadAdminWrite]

    def get_queryset(self):
        return SupplierRepository.all(
            search=self.request.query_params.get("search"),
            status=self.request.query_params.get("status"),
            tier=self.request.query_params.get("tier"),
            is_active=parse_optional_bool(self.request.query_params.get("is_active")),
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return paginate_response(
            request, queryset, serialize=lambda page: self.get_serializer(page, many=True).data
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "供應商主檔不得實體刪除，請改為停用",
                "code": "physical_delete_forbidden",
            },
            status=status.HTTP_409_CONFLICT,
        )
