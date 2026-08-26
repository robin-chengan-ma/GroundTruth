from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.core.urls")),
    path("api/v1/", include("api.crm.urls")),
    path("api/v1/", include("api.erp.urls")),
    path("api/v1/", include("api.procurement.urls")),
    path("api/v1/", include("api.audit.urls")),
]
