"""项目级 API 路由聚合入口。"""

from django.urls import include, path

from config.api.views import ApiRootView, AuthenticatedProbeView, StaffProbeView

app_name = "api"

urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path(
        "probes/authenticated/",
        AuthenticatedProbeView.as_view(),
        name="authenticated_probe",
    ),
    path("probes/staff/", StaffProbeView.as_view(), name="staff_probe"),
    path("", include("users.api.urls")),
    path("", include("catalog.api.urls")),
    path("", include("interactions.api.urls")),
    path("", include("orders.api.urls")),
    path("", include("messaging.api.urls")),
]
