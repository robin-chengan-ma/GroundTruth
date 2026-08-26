from rest_framework.routers import DefaultRouter

from api.audit.views import AuditLogViewSet, ManualReviewQueueViewSet

router = DefaultRouter()
router.register("manual-review-queue", ManualReviewQueueViewSet, basename="manual-review-queue")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = router.urls
