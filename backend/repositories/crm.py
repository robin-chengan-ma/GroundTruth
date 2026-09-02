from django.db.models import Q

from apps.crm.models import Supplier


class SupplierRepository:
    model = Supplier

    @staticmethod
    def all(*, search=None, status=None, tier=None, is_active=None):
        queryset = Supplier.objects.all()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        if status:
            queryset = queryset.filter(status=status)
        if tier:
            queryset = queryset.filter(tier=tier)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return queryset.order_by("id")

    @staticmethod
    def get(pk):
        return Supplier.objects.get(pk=pk)

    @staticmethod
    def find_by_exact_name(name: str):
        """供 Phase 3 遮罩節點做精確比對用（FR-2）。"""
        return Supplier.objects.filter(name=name).first()
