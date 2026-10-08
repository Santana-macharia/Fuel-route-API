from django.urls import path, re_path

from . import views

urlpatterns = [
    re_path(r"^route/?$", views.route_plan, name="route-plan"),
    path("map/<str:map_id>/", views.route_map, name="route-map"),
]
