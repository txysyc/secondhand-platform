"""项目级 API 路由聚合入口。"""

from django.urls import include, path

from api.views import ApiRootView, AuthenticatedProbeView, StaffProbeView

app_name = "api"

urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path(
        "probes/authenticated/",
        AuthenticatedProbeView.as_view(),
        name="authenticated_probe",
    ),
    path("probes/staff/", StaffProbeView.as_view(), name="staff_probe"),
    path("", include("users.urls")),
    path("", include("catalog.urls")),
    path("", include("interactions.urls")),
    path("", include("orders.urls")),
    path("", include("messaging.urls")),
    path("", include("notifications.urls")),
]
