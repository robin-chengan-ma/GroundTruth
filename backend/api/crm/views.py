from rest_framework import viewsets

from repositories.crm import SupplierRepository
from schemas.crm import SupplierSerializer


class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer

    def get_queryset(self):
        return SupplierRepository.all()
