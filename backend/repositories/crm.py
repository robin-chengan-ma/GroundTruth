from apps.crm.models import Supplier


class SupplierRepository:
    model = Supplier

    @staticmethod
    def all():
        return Supplier.objects.order_by("id")

    @staticmethod
    def get(pk):
        return Supplier.objects.get(pk=pk)

    @staticmethod
    def find_by_exact_name(name: str):
        """供 Phase 3 遮罩節點做精確比對用（FR-2）。"""
        return Supplier.objects.filter(name=name).first()
