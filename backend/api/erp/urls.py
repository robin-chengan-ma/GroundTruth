from rest_framework.routers import DefaultRouter

from api.erp.views import (
    GoodsReceiptViewSet,
    InspectionVarianceViewSet,
    InventoryViewSet,
    ProductViewSet,
    PurchaseSuggestionViewSet,
)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("inventory", InventoryViewSet, basename="inventory")
router.register("purchase-suggestions", PurchaseSuggestionViewSet, basename="purchase-suggestion")
router.register("goods-receipts", GoodsReceiptViewSet, basename="goods-receipt")
router.register(
    "inspection-variances", InspectionVarianceViewSet, basename="inspection-variance"
)

urlpatterns = router.urls
