from django.urls import path
from rest_framework.routers import DefaultRouter

from api.audit.views import (
    AuditDashboardStatsView,
    AuditLogViewSet,
    ManualReviewQueueViewSet,
    MaskAmountsOnlyView,
    MaskTextView,
    UnmaskTextView,
)

router = DefaultRouter()
router.register("manual-review-queue", ManualReviewQueueViewSet, basename="manual-review-queue")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("masking/mask/", MaskTextView.as_view(), name="masking-mask"),
    path("masking/unmask/", UnmaskTextView.as_view(), name="masking-unmask"),
    path("masking/mask-amounts-only/", MaskAmountsOnlyView.as_view(), name="masking-mask-amounts-only"),
    path("audit-dashboard/stats/", AuditDashboardStatsView.as_view(), name="audit-dashboard-stats"),
    *router.urls,
]
