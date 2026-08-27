from rest_framework import filters, viewsets

from repositories.crm import SupplierRepository
from schemas.crm import SupplierSerializer


class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]  # 供 Phase 2 n8n 依名稱查詢供應商用（?search=優品科技）

    def get_queryset(self):
        return SupplierRepository.all()
