from apps.audit.models import AuditLog, ManualReviewQueue


class ManualReviewQueueRepository:
    model = ManualReviewQueue

    @staticmethod
    def all():
        return ManualReviewQueue.objects.select_related("quote", "supplier", "user").all()

    @staticmethod
    def unclaimed():
        return ManualReviewQueue.objects.filter(status=ManualReviewQueue.Status.UNCLAIMED)


class AuditLogRepository:
    model = AuditLog

    @staticmethod
    def all():
        return AuditLog.objects.select_related("user", "quote").all()

    @staticmethod
    def record(**kwargs):
        return AuditLog.objects.create(**kwargs)
