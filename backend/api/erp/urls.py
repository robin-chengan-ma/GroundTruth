from rest_framework.routers import DefaultRouter

from api.erp.views import InventoryViewSet, ProductViewSet, PurchaseSuggestionViewSet

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("inventory", InventoryViewSet, basename="inventory")
router.register("purchase-suggestions", PurchaseSuggestionViewSet, basename="purchase-suggestion")

urlpatterns = router.urls
