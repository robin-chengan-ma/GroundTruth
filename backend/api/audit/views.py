from rest_framework import viewsets

from repositories.audit import AuditLogRepository, ManualReviewQueueRepository
from schemas.audit import AuditLogSerializer, ManualReviewQueueSerializer


class ManualReviewQueueViewSet(viewsets.ModelViewSet):
    serializer_class = ManualReviewQueueSerializer

    def get_queryset(self):
        return ManualReviewQueueRepository.all()


class AuditLogViewSet(viewsets.ModelViewSet):
    """稽核 log 依 SPEC 為系統寫入紀錄；Phase 1 先提供完整 CRUD 供測試/管理用，
    後續 Phase 若需限制為唯讀，於 API 層加 http_method_names 即可。"""

    serializer_class = AuditLogSerializer

    def get_queryset(self):
        return AuditLogRepository.all()
