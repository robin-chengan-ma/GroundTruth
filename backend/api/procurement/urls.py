from django.urls import path
from rest_framework.routers import DefaultRouter

from api.procurement.views import (
    ApprovalCaseViewSet,
    ApprovalStepViewSet,
    ApprovalViewSet,
    AwardDecisionViewSet,
    InquiryCandidateParseView,
    InquiryTriggerView,
    PurchaseOrderViewSet,
    PurchaseRequestDraftViewSet,
    PurchaseRequestViewSet,
    QuoteCalculationView,
    QuoteHallucinationVerifyView,
    QuoteRequirementResultViewSet,
    QuoteViewSet,
    RfqViewSet,
    SupplierProductCoverageView,
    SupplierQuoteViewSet,
)

router = DefaultRouter()
router.register("quotes", QuoteViewSet, basename="quote")
router.register("approvals", ApprovalViewSet, basename="approval")
router.register("approval-cases", ApprovalCaseViewSet, basename="approval-case")
router.register("approval-steps", ApprovalStepViewSet, basename="approval-step")
router.register("award-decisions", AwardDecisionViewSet, basename="award-decision")
router.register("purchase-request-drafts", PurchaseRequestDraftViewSet, basename="purchase-request-draft")
router.register("purchase-requests", PurchaseRequestViewSet, basename="purchase-request")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("rfqs", RfqViewSet, basename="rfq")
router.register("supplier-quotes", SupplierQuoteViewSet, basename="supplier-quote")
router.register(
    "quote-requirement-results",
    QuoteRequirementResultViewSet,
    basename="quote-requirement-result",
)

# 自訂路徑要放在 router.urls 之前：DRF router 的 /quotes/{pk}/ 預設 pk regex 會吃掉
# "calculate"／"verify-hallucination" 這種非數字字串，順序反過來會被 QuoteViewSet 的
# detail route 攔截。
urlpatterns = [
    path("inquiries/parse/", InquiryCandidateParseView.as_view(), name="inquiry-parse"),
    path(
        "supplier-product-coverage/",
        SupplierProductCoverageView.as_view(),
        name="supplier-product-coverage",
    ),
    path("inquiries/trigger/", InquiryTriggerView.as_view(), name="inquiry-trigger"),
    path("quotes/calculate/", QuoteCalculationView.as_view(), name="quote-calculate"),
    path("quotes/verify-hallucination/", QuoteHallucinationVerifyView.as_view(), name="quote-verify-hallucination"),
    *router.urls,
]
