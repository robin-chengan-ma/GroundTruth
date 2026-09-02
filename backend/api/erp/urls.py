from rest_framework.routers import DefaultRouter

from api.erp.views import (
    GoodsReceiptViewSet,
    InspectionVarianceViewSet,
    InventoryBalanceViewSet,
    InventoryMovementViewSet,
    InventoryViewSet,
    ProductCategoryViewSet,
    ProductViewSet,
    PurchaseSuggestionViewSet,
)

router = DefaultRouter()
router.register("product-categories", ProductCategoryViewSet, basename="product-category")
router.register("products", ProductViewSet, basename="product")
router.register("inventory", InventoryViewSet, basename="inventory")
router.register("inventory-balances", InventoryBalanceViewSet, basename="inventory-balance")
router.register("inventory-movements", InventoryMovementViewSet, basename="inventory-movement")
router.register("purchase-suggestions", PurchaseSuggestionViewSet, basename="purchase-suggestion")
router.register("goods-receipts", GoodsReceiptViewSet, basename="goods-receipt")
router.register(
    "inspection-variances", InspectionVarianceViewSet, basename="inspection-variance"
)

urlpatterns = router.urls
