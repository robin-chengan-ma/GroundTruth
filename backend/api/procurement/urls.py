from django.urls import path
from rest_framework.routers import DefaultRouter

from api.procurement.views import (
    ApprovalViewSet,
    InquiryTriggerView,
    QuoteCalculationView,
    QuoteViewSet,
)

router = DefaultRouter()
router.register("quotes", QuoteViewSet, basename="quote")
router.register("approvals", ApprovalViewSet, basename="approval")

# 自訂路徑要放在 router.urls 之前：DRF router 的 /quotes/{pk}/ 預設 pk regex 會吃掉
# "calculate" 這種非數字字串，順序反過來會被 QuoteViewSet 的 detail route 攔截。
urlpatterns = [
    path("inquiries/trigger/", InquiryTriggerView.as_view(), name="inquiry-trigger"),
    path("quotes/calculate/", QuoteCalculationView.as_view(), name="quote-calculate"),
] + router.urls
