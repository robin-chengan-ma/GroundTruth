from rest_framework.routers import DefaultRouter

from api.procurement.views import ApprovalViewSet, QuoteViewSet

router = DefaultRouter()
router.register("quotes", QuoteViewSet, basename="quote")
router.register("approvals", ApprovalViewSet, basename="approval")

urlpatterns = router.urls
