from rest_framework.routers import DefaultRouter

from api.crm.views import SupplierViewSet

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")

urlpatterns = router.urls
