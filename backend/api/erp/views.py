from rest_framework import viewsets

from repositories.erp import InventoryRepository, ProductRepository, PurchaseSuggestionRepository
from schemas.erp import InventorySerializer, ProductSerializer, PurchaseSuggestionSerializer


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer

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
