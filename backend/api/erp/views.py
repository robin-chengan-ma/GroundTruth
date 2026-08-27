from rest_framework import filters, viewsets

from repositories.erp import InventoryRepository, ProductRepository, PurchaseSuggestionRepository
from schemas.erp import InventorySerializer, ProductSerializer, PurchaseSuggestionSerializer


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]  # 供 Phase 2 n8n 依名稱查詢產品用（?search=A產品）

    def get_queryset(self):
        return ProductRepository.all()


class InventoryViewSet(viewsets.ModelViewSet):
    serializer_class = InventorySerializer

    def get_queryset(self):
        return InventoryRepository.all()


class PurchaseSuggestionViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseSuggestionSerializer

    def get_queryset(self):
        return PurchaseSuggestionRepository.all()
