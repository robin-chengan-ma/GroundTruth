from apps.procurement.models import Approval, Quote


class QuoteRepository:
    model = Quote

    @staticmethod
    def all():
        return Quote.objects.select_related("user", "supplier", "product").order_by("id")

    @staticmethod
    def get(pk):
        return Quote.objects.select_related("user", "supplier", "product").get(pk=pk)

    @staticmethod
    def approved_history(supplier_id, product_id):
        """供 FR-4a 歷史均價比對使用。"""
        return Quote.objects.filter(
            supplier_id=supplier_id, product_id=product_id, status=Quote.Status.APPROVED
        )


class ApprovalRepository:
    model = Approval

    @staticmethod
    def all():
        return Approval.objects.select_related("quote", "role", "approver").order_by("id")

    @staticmethod
    def unclaimed_for_role(role_id):
        return Approval.objects.filter(
            role_id=role_id, approver__isnull=True, status=Approval.Status.PENDING
        )
