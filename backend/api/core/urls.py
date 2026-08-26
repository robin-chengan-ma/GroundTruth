from rest_framework.routers import DefaultRouter

from api.core.views import RoleViewSet, UserViewSet

router = DefaultRouter()
router.register("roles", RoleViewSet, basename="role")
router.register("users", UserViewSet, basename="user")

urlpatterns = router.urls
